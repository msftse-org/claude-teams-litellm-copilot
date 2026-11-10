CLAUDE GATEWAY · CUSTOMER ONBOARDING
==================================

START HERE
Open https://msftse-org.github.io/claude-teams-litellm-copilot/
or open START-HERE.html offline in your browser. It contains the complete onboarding
journeys, copyable commands, architecture PNGs, troubleshooting and test scope.
It is self-contained and can be shared as one file. No role is selected by
default: choose Administrator or Developer for your separate four-step journey.

Repository: https://github.com/msftse-org/claude-teams-litellm-copilot
See README.md for the complete overview and download links.

RUN THE GUIDED CLI
Open this extracted folder in Terminal or iTerm:

    ./setup

ADMINISTRATOR
Prepare the existing customer gateway once, then invite each developer.
Choose recommended or custom fallback targets. Deliver each invitation privately.
The invitation contains a personal 90-day gateway key, never the master key.
No email is sent. Work email identifies the LiteLLM user and supports repeat
enrollment; it is not mailbox verification. Deliver the invitation yourself
through an approved private channel. Use HANDOFF-TEMPLATE.txt for instructions.

DEVELOPER
Choose Developer → Join with my invitation. Connect your own accounts, wait for
the checks, restart open sessions, then run claude normally.

SHORTCUTS
    ./setup admin
    ./setup developer
    ./setup doctor
    ./setup models

PREREQUISITES
Python 3.10+; Claude Code for developers; an existing HTTPS LiteLLM gateway with
PostgreSQL and store_model_in_db enabled; eligible Claude and Copilot accounts.
Validated on macOS, LiteLLM 1.108.0, Claude Code 2.1.317 and Python 3.14.7.

DEFAULT POLICY
Teams Sonnet 5.5 → Copilot Sonnet 5.5
Teams Opus 5.5   → Copilot Sonnet 5.5
Teams Haiku 5.5  → Copilot Haiku 5.5
Legacy Sonnet 5 and Haiku 4.5 map to their matching Copilot versions.
The administrator can choose other offered backups during invitation creation.
Optional Copilot Opus requires separately verified entitlement and was not tested.

VERIFIED ON 10 NOVEMBER 2026
17 automated tests passed. Fresh administrator and developer onboarding passed.
Three primary and four direct Copilot model selections responded successfully.
After real subscription usage reached 100%, all three primary selections fell
back to Copilot with attempted_fallbacks=1. A primary-only diagnostic returned
real Anthropic HTTP 429. A Read tool call and follow-up succeeded through fallback.
No provider error was simulated. Aggregate results: VALIDATION.json. Deployment checks: docs/VALIDATION.md.

DEPLOYMENT REQUIREMENTS
Verify your organization's accounts, gateway version, network, policies and
required tools as part of setup. Read-tool success does
not imply native WebSearch parity. The optional MCP search script is separate.
The wildcard primary route may advertise additional models without tested fallback.
Use the documented mappings and inspect LiteLLM Logs for the actual provider.

CONTENTS
START-HERE.html        Complete standalone guide
setup                 Executable terminal entry point
_engine/              Python implementation and explicit model catalog
diagrams/             Three standalone architecture PNGs
VALIDATION.json      Aggregate compatibility and validation results
docs/VALIDATION.md   Commands, expected results and deployment checks
HANDOFF-TEMPLATE.txt  Suggested private handoff message; no secrets included
IMAGE-PROMPTS.txt     Final image-generation prompts and correction
tests/                Offline automated checks

To run the offline tests from this folder:
    python3 -m unittest discover -s tests

Private invitations and live credentials are never included in this package.
