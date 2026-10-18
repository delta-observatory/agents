"""Build agent tools from the Delta Observatory API description (OpenAPI 3).

Each API operation becomes one tool. The tool holds the HTTP method and path, and an input
schema with the path parameters, the query parameters, and the JSON request body.
The generator copies names, texts, and schemas from the API description. It adds no logic.

Usage: python -m adapter.generate --openapi <url|file> --print
"""
import argparse
import copy
import json
import re
import sys
import urllib.request

NAME_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
BODY = 'body'


def load(source: str, timeout: float = 30) -> dict:
    """Read an OpenAPI document from a URL or a file."""
    if source.startswith(('http://', 'https://')):
        with urllib.request.urlopen(source, timeout=timeout) as response:
            return json.loads(response.read())
    with open(source, encoding='utf-8') as stream:
        return json.load(stream)


def resolve(node, document: dict, seen: tuple = ()):
    """Replace each local $ref with a copy of its target. A cyclic reference becomes an empty schema."""
    if isinstance(node, list):
        return [resolve(item, document, seen) for item in node]
    if not isinstance(node, dict):
        return node
    if '$ref' in node:
        ref = node['$ref']
        if not ref.startswith('#/') or ref in seen:
            return {}
        target = document
        for part in ref[2:].split('/'):
            target = target[part.replace('~1', '/').replace('~0', '~')]
        extra = {k: v for k, v in node.items() if k != '$ref'}
        return {**resolve(copy.deepcopy(target), document, seen + (ref,)), **resolve(extra, document, seen)}
    return {k: resolve(v, document, seen) for k, v in node.items()}


def sanitize(text: str) -> str:
    return re.sub(r'_+', '_', re.sub(r'[^A-Za-z0-9_-]', '_', text)).strip('_')[:64] or 'operation'


def short_name(operation_id: str, path: str, method: str) -> str:
    """FastAPI operation IDs end with the path and the method, for example get_run_api_runs__run_id__get.
    Return the part before that suffix."""
    suffix = '_' + re.sub(r'\W', '_', path.lstrip('/')) + '_' + method
    return operation_id[:-len(suffix)] if operation_id.endswith(suffix) and len(operation_id) > len(suffix) else operation_id


def tools(document: dict) -> list[dict]:
    """One tool for each operation, in path order. Names are unique and stable for one API description."""
    operations = []
    for path, item in document.get('paths', {}).items():
        shared = item.get('parameters', [])
        for method in ('get', 'post', 'put', 'patch', 'delete'):
            if method in item:
                operations.append((path, method, item[method], shared))
    shorts = [sanitize(short_name(op.get('operationId') or f'{m}_{p}', p, m)) for p, m, op, _ in operations]
    out = []
    for (path, method, operation, shared), short in zip(operations, shorts):
        full = sanitize(operation.get('operationId') or f'{method}_{path}')
        name = short if shorts.count(short) == 1 else full
        properties, required, path_params, query_params = {}, [], [], []
        for parameter in resolve(shared + operation.get('parameters', []), document):
            where, pname = parameter.get('in'), parameter['name']
            if where not in ('path', 'query'):
                continue  # Header parameters: the adapter sends the token itself.
            schema = dict(parameter.get('schema') or {})
            if parameter.get('description'):
                schema['description'] = parameter['description']
            properties[pname] = schema
            (path_params if where == 'path' else query_params).append(pname)
            if parameter.get('required') or where == 'path':
                required.append(pname)
        body = False
        content = resolve(operation.get('requestBody', {}), document).get('content', {})
        if 'application/json' in content:
            body = True
            schema = dict(content['application/json'].get('schema') or {})
            schema.setdefault('description', 'The JSON request body.')
            properties[BODY] = schema
            if operation.get('requestBody', {}).get('required'):
                required.append(BODY)
        texts = [operation.get('summary'), operation.get('description'), f'HTTP: {method.upper()} {path}']
        out.append({
            'name': name,
            'description': '\n\n'.join(t.strip() for t in texts if t),
            'inputSchema': {'type': 'object', 'properties': properties, 'required': required,
                            'additionalProperties': False},
            'http': {'method': method.upper(), 'path': path, 'path_params': path_params,
                     'query_params': query_params, 'body': body},
        })
    names = [t['name'] for t in out]
    bad = [n for n in names if not NAME_PATTERN.match(n) or names.count(n) > 1]
    if bad:
        raise ValueError(f'tool names are not unique or not valid: {sorted(set(bad))}')
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--openapi', required=True, help='URL or file of the OpenAPI document')
    parser.add_argument('--print', action='store_true', help='print the tools as JSON')
    args = parser.parse_args(argv)
    result = tools(load(args.openapi))
    if args.print:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write('\n')
    else:
        for tool in result:
            print(f"{tool['name']:40} {tool['http']['method']:6} {tool['http']['path']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
