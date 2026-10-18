# Agent adapter

The adapter gives the API operations to an agent as MCP tools over stdio.
It reads the API description (`/api/openapi.json`) at startup and makes one tool for each operation.
A tool call sends exactly one HTTP request with the client token. The result has the HTTP status and the response.
The adapter contains no scientific or policy logic. The API applies permissions, campaign rules, blinding, budgets, and the cohort guard.
A new API operation becomes a tool at the next adapter start. No adapter change is necessary.

The adapter uses the Python 3.12 standard library only.

## Run

```bash
cd agents
DELTA_TOKEN_FILE=<token file> python3 -m adapter.server
```

An MCP client starts the server as a command. Example client entry:

```json
{
  "mcpServers": {
    "delta-observatory": {
      "command": "python3",
      "args": ["-m", "adapter.server"],
      "env": {
        "PYTHONPATH": "<path to the agents repository>",
        "DELTA_API_URL": "http://localhost:30870/api",
        "DELTA_TOKEN_FILE": "<token file of the agent client>"
      }
    }
  }
}
```

Give each agent the token file of its own client. Do not give an agent Richard's token.

| Setting | Default | Meaning |
|---|---|---|
| `DELTA_API_URL` | `http://localhost:30870/api` | API address. |
| `DELTA_TOKEN_FILE` | none | File with the client token. Without it, requests carry no token, and the API gives 401. |
| `DELTA_OPENAPI` | `<DELTA_API_URL>/openapi.json` | File or URL of the API description. |
| `DELTA_ADAPTER_DOWNLOADS` | `~/.cache/delta-adapter/downloads` | Directory for responses that are not inline JSON. Keep it outside the workspace. |
| `DELTA_ADAPTER_INLINE_BYTES` | `1000000` | Largest JSON response that a result holds as text. |
| `DELTA_ADAPTER_TIMEOUT` | `120` | Request timeout in seconds. |

List the tools without a server:

```bash
python3 -m adapter.generate --openapi http://localhost:30870/api/openapi.json
python3 -m adapter.generate --openapi http://localhost:30870/api/openapi.json --print
```

## Tools

| Item | Rule |
|---|---|
| Name | The FastAPI operation ID without its path and method suffix, for example `get_run` from `get_run_api_runs__run_id__get`. When two names are equal, both tools keep the full sanitized operation ID. |
| Description | The summary and description of the operation, and its HTTP method and path. |
| Input | One property for each path and query parameter, and `body` for a JSON request body. References are resolved. Header parameters are left out, because the adapter sends the token. |
| Result | Text with `status`, and `body` for a JSON response. `isError` is true for a status of 400 or more. |
| Download | A response that is not JSON, has a `Content-Encoding`, or is larger than the inline limit goes to a file. The result gives `path`, `bytes`, `sha256`, `media_type`, and `content_encoding`. The file holds the response bytes without decoding, so its SHA-256 can be compared with a stored artifact checksum or an export manifest. |

The token never appears in a result or in the log. The server writes one log line for each tool call to stderr: the tool name and `ok` or `error`.

## Tests

```bash
python3 -m unittest discover -s adapter/tests -t .
```

The tests use `tests/openapi.fixture.json` and a stub HTTP server.
The fixture is the API description of backend commit `1296e66`.
They check tool generation, stable names, parameter placement, status pass-through, downloads, the stdio session, and the absence of the token in output.
