# Configuration reference

The guided CLI writes native LiteLLM resources through the management API. The model catalog lives in [`_engine/catalog.json`](../_engine/catalog.json); the installer logic lives in [`admin.py`](../_engine/admin.py) and [`developer.py`](../_engine/developer.py).

## Existing gateway configuration

The customer owns the LiteLLM deployment and database. Merge this prerequisite into its existing configuration using the customer’s deployment process:

```yaml
general_settings:
  store_model_in_db: true
```

This is a prerequisite fragment, **not a complete deployment file**. Keep the existing master key, database connection, TLS, monitoring and secret management. The onboarding CLI registers models and credentials in the database; it does not replace `config.yaml` or require a custom container image.

## Resources created by Prepare

| Resource | Configuration |
|---|---|
| Primary model route | `model_name: anthropic/*`, `litellm_params.model: anthropic/*` |
| Copilot credential definition | `github-copilot-user`, provider `github_copilot`, `github_copilot_auth_type: per_user_oauth` |
| Backup routes | Explicit `claude-copilot-*` aliases mapped to provider model names in the catalog |
| Route behavior | `max_retries: 0`; `model_info.cooldown_time: 0` |

Prepare creates one credential definition and five routes by default: the primary wildcard plus four Copilot models. Optional Copilot Opus adds a sixth route. The credential definition is not a shared provider token. Each developer connects their own GitHub account during Join.

Preparation first checks existing resources. Identical routes are reused; conflicting routes stop the operation for review. Infrastructure and unrelated models are preserved. Multi-step API writes are not a database transaction: if a request fails partway through, rerun preparation to reconcile the matching resources.

## User, key and invitation

Invite creates an `internal_user` linked to the normalized work email and expected GitHub username. The user ID is a stable UUID derived from the gateway origin and email. Changing the email creates a different identity. The address is neither a mailbox verification nor a Claude/GitHub sign-in.

A personal key is generated with:

- A 90-day duration and allowed models from the selected catalog.
- Routes limited to inference, token counting, model/key/user inspection and that credential’s per-user connection flow. The exact allowlist is in `admin.enroll()`.
- Per-key fallback mappings, `num_retries: 0` and `context_window_fallbacks: []`.
- `send_invite_email: false` on both user and key creation.

The `.invite.json` contains the gateway URL, personal key, user ID, expected GitHub username, credential name, allowed models, expiry and fallback policy. It is saved with owner-only permissions. Share it privately; it is an access credential. SMTP is not part of this flow.

Reusing the same valid invitation filename reuses the existing key after checking ownership and policy. A new filename issues a new key for the existing user. Changing policy does not silently revoke previous keys; the administrator must revoke those as appropriate.

## Fallback policy

The default mapping covers Sonnet 5.5 → Copilot Sonnet 5.5, Opus 5.5 → Copilot Sonnet 5.5, Haiku 5.5 → Copilot Haiku 5.5, and the matching legacy Sonnet 5 / Haiku 4.5 models. Catalog entries include the supported model-name spellings with and without the `anthropic/` prefix.

During invitation creation, administrators can choose a different offered backup for each current primary family. Direct Copilot aliases have empty fallback lists. Optional Copilot Opus is only offered after explicit enablement.

The mappings are attached to each key rather than one shared global fallback rule. Existing global policies still require customer review, particularly content-policy handling and other router overrides. A new model exposed through the primary wildcard does not automatically receive a mapping.

## Claude Code settings written by Join

This illustrative fragment shows the fields managed by the installer. **Do not copy the placeholder key.** Use Join to validate accounts, back up existing settings and write the actual personal key:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://litellm.customer.example",
    "ANTHROPIC_CUSTOM_HEADERS": "x-litellm-api-key: Bearer <personal-gateway-key>",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5-5",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5-5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-5-5",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
    "CLAUDE_CODE_AUTO_MODE_SERVER": "0"
  },
  "model": "sonnet"
}
```

The installer removes a conflicting `apiKeyHelper` and provider-specific credentials/settings from the user settings it manages. The exact list is `CONFLICTS` in `developer.py`. This allows Claude Code to use its subscription login while authenticating separately to LiteLLM. Other custom headers, permissions and unrelated settings are preserved.

Shell overrides, project settings and managed policies remain separate. Join/Doctor catch several shell conflicts, but the customer should inspect all applicable configuration layers if observed routing differs. This installer targets the standard Claude profile; a custom `CLAUDE_CONFIG_DIR` stops onboarding for review.

## Where state lives

| Location | State |
|---|---|
| Customer LiteLLM database | Model routes, credential definition, users, personal keys and provider connections |
| Developer `~/.claude/settings.json` | Gateway URL, personal gateway key header and model defaults |
| Developer `~/.claude/gateway-onboarding.json` | Onboarding identity, backup location and installed-settings hash |
| Developer `~/.claude/backups/gateway-…/settings.json` | Private previous settings for restore |
| Claude Code account storage | Developer’s Claude subscription sign-in, managed by Claude Code |
| Private invitation file | Personal gateway access and handoff metadata |

LiteLLM’s encryption, database protection and backup configuration remain the customer operator’s responsibility. The repository contains no live credentials or invitations.

## Inspect and troubleshoot

In LiteLLM, review **Models + Endpoints**, **LLM Credentials**, **Virtual Keys → Router Settings**, and **Logs**. UI labels can vary by version.

For actual fallback evidence, record the request ID, requested model group, actual provider/model, status, `used_client_oauth_token` and `attempted_fallbacks`. A direct Copilot success alone does not prove fallback. A 429 alone does not prove five-hour subscription quota exhaustion; it may be a shorter rate limit.

Native WebSearch previously failed on the Copilot route. The optional search helper is separate from model routing and requires its own customer acceptance; Join never silently enables it. Verify required tools and model context behavior in the pilot.

See the [onboarding guide](../START-HERE.html), [README](../README.md) and [deployment validation](VALIDATION.md).
