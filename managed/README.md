# Managed desktop agent

The desktop runs Codex app-server or unmodified Claude Code inside a Linux namespace.
The host uses generated API tools with a campaign-scoped credential.
The model receives no Delta credential, database socket, observation mount, or artifact mount.

The pinned runtimes are Codex 0.164.0 and Claude Code 2.1.305.
Codex uses the checked `gpt-5.4` model with direct function calls.
Claude Code supports its `sonnet`, `opus`, and `haiku` model selectors.
The selected account must offer the selected model.
The isolated Claude Code check verifies the complete MCP tool exchange.
The API records provider identity and session consent.
Shell tools, code execution, collaboration, plugins, browser access, and bundled skills remain disabled.
The namespace exposes operating-system libraries and a separate provider profile.
It does not expose the user's home directory or Delta workspace.

The desktop controller provides these operations:

- Prepare a provider connection before creating an investigation.
- Sign in to OpenAI through ChatGPT, a device code, or an API key.
- Sign in to Anthropic through its subscription, Console, or organization SSO page.
- Enter the authorization code when the Anthropic page requests a manual return.
- Cancel a pending login or inspect the current account.
- Use memory-only credentials for either provider.
- Store OpenAI credentials in the operating-system credential store.
- Store Anthropic credentials in the private Claude Code profile.
- Create or reconnect a consented session.
- Send instructions, pause a turn, disconnect, or sign out.

Provider login does not create a scientific session or send investigation evidence.
The provider connection remains available during navigation between application views.
Disconnecting an investigation preserves the provider account.
Provider sign-out pauses the agent, disconnects its session, and removes the provider login.
Closing the desktop removes memory-only credentials.

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
python3 -B -m unittest discover -s managed/tests -t .
python3 -B scripts/check_managed_isolation.py --runtime <directory-containing-codex>
python3 -B scripts/check_claude_isolation.py --runtime <directory-containing-claude>
```

The isolation check uses a local fake provider without account credentials or model requests.
It checks a complete direct tool call and inaccessible host paths.
It also checks that the model sees only the supplied API tool.
A local protocol fixture checks login, cancellation, account updates, sign-out, and isolation between investigation messages.
Provider account eligibility and interactive login require an account-specific check.
The [Codex authentication protocol](https://learn.chatgpt.com/docs/app-server#auth-endpoints) defines the provider operations.

## Anthropic authentication

Claude Code owns authorization, callback validation, token refresh, and credential storage.
Delta does not implement Anthropic OAuth or read its OAuth tokens.
The native binary remains unchanged. Its authentication methods remain part of the published application.
The selected profile is separate from any personal Claude Code installation.
Memory-only profiles use a private directory in `/dev/shm` and disappear after orderly shutdown.
Persistent profiles use `agent-profiles/claude` with owner-only directory permissions.
Workspace backups and evidence exports exclude provider profiles.

The host runs the documented `claude auth` and `claude --print` interfaces.
It supplies an authenticated local MCP endpoint with the same scoped tools as Codex.
Each request checks the approved investigation and its current execution state.
A paused turn cannot call tools. The model receives no Delta credential.

Anthropic permits products to run its unmodified application under its published [hosting conditions](https://code.claude.com/docs/en/legal-and-compliance#can-customers-offer-claude-code-in-their-products).
Each user authenticates with their own account and pays the provider directly.
The [CLI reference](https://code.claude.com/docs/en/cli-reference) defines native authentication commands.
The [programmatic interface](https://code.claude.com/docs/en/headless) defines execution and session continuation.
