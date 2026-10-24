# Managed desktop agent

The desktop starts one Codex app-server inside a Linux namespace.
The host uses generated API tools with a campaign-scoped credential.
The model receives no Delta credential, database socket, observation mount, or artifact mount.

The pinned runtime is Codex 0.164.0.
The supported model is `gpt-5.4`, with direct function calls.
The account must offer this model.
Other models require a separate tool-exposure check before support.
Shell tools, code execution, collaboration, plugins, browser access, and bundled skills remain disabled.
The namespace exposes operating-system libraries and a separate provider profile.
It does not expose the user's home directory or Delta workspace.

The desktop controller provides these operations:

- Prepare a connection for an approved investigation.
- Sign in through the provider's device page or an API key.
- Use memory-only credentials or the operating-system credential store.
- Create or reconnect a consented session.
- Send instructions, pause a turn, disconnect, or sign out.

The owner must consent before the host sends permitted investigation evidence to the model provider.
This connection does not authorize archive uploads or external candidate submissions.
The API enforces the approved observation selection, blinding, revision approval, and execution limits.
A proposed revision requires the owner's approval.
A provider call identifier supplies the execution request key, which prevents duplicate jobs on retransmission.

The API stores session state, instructions, responses, and measured use.
The provider stores its conversation in the separate profile.
Token notifications can arrive after use.
The token limit stops further work after measurement. It does not guarantee a provider spending cap.
Manual execution remains available when login or the provider fails.

Run the local checks from this repository:

```bash
python3 -m unittest discover -s managed/tests -t .
python3 scripts/check_managed_isolation.py --runtime <directory-containing-codex>
```

The isolation check uses a local fake provider without account credentials or model requests.
It checks a complete direct tool call and inaccessible host paths.
It also checks that the model sees only the supplied API tool.
Provider account eligibility and interactive login require an account-specific check.
