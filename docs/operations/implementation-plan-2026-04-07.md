# Agent Platform Implementation Plan and Execution Report (2026-04-07)

## Scope
This document updates the existing plan with three additional requests and records what has been implemented.

Added requests integrated here:
1. Provider-specific bootstrap/identity/AGENTS/etc template sets.
2. Full plugin audit + enablement of high-impact plugins + ClawHub verified plugin research.
3. Repeatable process to skills/workflows report + Lobster integration design.

## Delivery Status

### 1) Determinism and per-agent model/provider control
Status: Implemented (core platform changes) + rollout guidance documented

Implemented:
- Added per-agent `model_provider` and `model_name` in Mission Control backend model + schema + migration.
- Added provider normalization and provider-aware template mapping.
- Added provider-specific template trees for:
  - `openai`
  - `google`
  - `ollama`
  - `anthropic`
- Each provider has separate files for:
  - `BOARD_AGENTS.md.j2`
  - `BOARD_BOOTSTRAP.md.j2`
  - `BOARD_IDENTITY.md.j2`
  - `BOARD_SOUL.md.j2`
  - `BOARD_TOOLS.md.j2`
  - `BOARD_USER.md.j2`
  - `BOARD_HEARTBEAT.md.j2`
  - `BOARD_MEMORY.md.j2`
- Added provider-tailored behavior notes to each set (`_PROVIDER_NOTES.md.j2`) while preserving shared core instructions.
- Added Mission Control UI controls for per-agent provider/model selection in create/edit/detail/list views.

Deterministic surfaces now available:
- Routing determinism via explicit provider + model fields on each agent.
- Provisioning determinism via provider-specific template paths.
- Schema determinism via migration-backed persisted fields.
- Operational determinism via explicit cron visibility endpoint and UI.

Non-100%-deterministic areas and mitigation:
- LLM generation variability remains in natural-language turns.
- Mitigation applied: stronger provider-specific instruction scaffolds and AGENTS/BOOTSTRAP guidance overlays.

DB note (sqlite/relational question):
- Mission Control uses relational persistence (SQLAlchemy/Alembic migrations; deployment typically PostgreSQL).
- Relational storage improves determinism for:
  - agent config state
  - provisioning metadata
  - reproducible model/provider assignment
- Recommendation:
  - keep relational DB as source of truth for agent identity/config
  - persist run/event ledger (append-only) for deterministic dashboards/replay
  - use unique keys + idempotency tokens for reminder/scheduling inserts

### 2) Telegram / reminders flow verification
Status: Verified with a confirmed gap

Current environment facts:
- Gateway is healthy.
- Channel probes are healthy, but `health` still reports `running: false` for telegram/discord in this runtime build.

Verification run executed:
- Command: `openclaw agent --agent main --message "Remind me tomorrow at 9am to call the dentist." --json --timeout 120`
- Observed:
  - main agent response explicitly confirms delegation to reminders agent.
  - reminders agent created a new subagent session record.
  - reminder persisted in reminders workspace files:
    - `workspace/memory/reminders/active.md`
    - `workspace/memory/reminders/memory/2026-04-07.md`

What is verified:
- Main -> reminders handoff behavior works.
- Reminder persistence in reminders workspace works.

Additional end-to-end probe run:
- Sent from a real Telegram group session context (`agent:main:telegram:group:-1003616868447:topic:1`) with `--deliver`.
- Main delegated to reminders subagent.
- Reminders subagent wrote reminder entries into reminders workspace files.

What is not fully verified in this run:
- Delivery in Telegram Reminders topic itself is not currently happening for this path:
  - reminders topic session (`agent:reminders:telegram:group:-1003616868447:topic:15`) did not update
  - execution used a reminders subagent session with `deliveryContext.channel = webchat`
  - result: handoff + storage works, topic delivery requirement still needs implementation in runtime routing.

Typing indicator per-agent-by-name:
- Not implemented in this cycle (requires channel/runtime support beyond Mission Control).

Message reactions:
- Built-in runtime support not changed.
- ClawHub `telegram-ui` plugin was evaluated but is not installable on current runtime version:
  - requires plugin API `>=2026.4.2`
- runtime at report time exposed `2026.4.1` (current host runtime is `2026.4.8`)

### 3) Mission Control dashboard enhancements
Status: Substantially implemented in this cycle

Implemented:
- Added cron/scheduling visibility endpoint and UI section:
  - backend `GET /api/v1/gateways/crons`
  - frontend gateway detail renders cron table (name/schedule/status/target)
- Added per-agent model switching controls (provider + model) in UI and backend.
- Added runtime status and collaboration overview:
  - backend `GET /api/v1/gateways/runtime-overview`
  - normalized status mapping (`working`, `idle`, `waiting`, `broken`, `unknown`)
  - parent/child collaboration edge extraction from gateway sessions
  - frontend runtime map section with:
    - agent status table
    - recent subagent activity table
    - collaboration edges table
    - summary counters

Not yet implemented in this cycle:
- Event-feed sidecar UI and configurable notification rule editor.

Recommended next implementation:
- Add an event ledger table + normalized status reducer fed by gateway diagnostics stream.
- Add status derivation rules (heartbeat age, pending approvals, active subprocess, last error).
- Render dependency graph and ownership cards in dashboard.

### 4) Medical Team Platform (Telegram) response length control
Status: Not fully implemented in code; rollout path defined

Recommended deterministic approach:
- Add response policy to each medical agent AGENTS/IDENTITY templates:
  - default brief answer (3-6 bullets)
  - optional `Details:` section only when requested
  - enforce max sentence/paragraph budget per reply
- Add runtime knobs:
  - `responseStyle: concise|balanced|detailed`
  - `detailOnDemand: true`

### 5) Medical Team Platform (Web App)
Status: Planned; not implemented in this cycle

Planned implementation tracks:
- UI modernization pass (light theme with controlled dark accents, mobile-first).
- Active work page (in-progress, typing, blocked, waiting signals).
- Multi-agent chat selector/toggles + tabbed conversations.
- Sidecar monitoring UI with configurable event notifications.

## Plugin Audit and Enablement

## Local plugin inventory snapshot
- Total discovered: 87
- Loaded: 45
- Disabled: 42
- Errors: 0

Enabled in this execution path (task-relevant):
- `diagnostics-otel` (loaded)
- `lobster` (loaded)
- `llm-task` (loaded)
- `tavily` (loaded)
- `opik-openclaw` (installed from ClawHub and loaded)

Also validated loaded channel plugins:
- `telegram`
- `discord`

Install/compatibility outcomes:
- `telegram-ui` (ClawHub) install attempt failed due runtime API mismatch (`>=2026.4.2` required).

Operational note:
- Gateway restart is required for newly enabled plugins to take effect on live message processing.

## ClawHub verified plugin research (relevant set)

Official/source-linked candidates:
- `@openclaw/diagnostics-otel` (official, source-linked, scan clean)
  - Strong fit for Mission Control event/status observability.

Community/source-linked candidates evaluated:
- `@opik/opik-openclaw` (installed)
  - Fit: trace export and post-run diagnostics.
- `oh-my-langfuse` (source-linked; scan pending)
  - Fit: prompt/trace observability and quality analysis.
- `openclaw-run-observer` (source-linked; scan pending)
  - Fit: local run event viewer for sidecar monitoring.
- `@clawnify/clawflow` (source-linked; scan pending)
  - Fit: declarative workflow orchestration.
- `openclaw-swarm-layer` (source-linked; scan pending)
  - Fit: coordinated workflow orchestration.
- `openclaw-telegram-multibot-relay` (source-linked; scan pending)
  - Fit: Telegram relay/delegation/reminder routing.

ClawHub API caveat observed:
- Search endpoint currently returned server errors for keyword searches in this run; list/inspect endpoints were used successfully.

## Repeatable Processes -> Skills/Workflows Mapping

### Convert to reusable skills
1. Deterministic reminder intake
- Trigger: reminder intent in main or topic channels
- Skill outputs: normalized reminder object `{who, what, when, timezone, source}`
- Side effects: append to `active.md`, daily memory, optional cron

2. Mission Control status synthesis
- Trigger: dashboard refresh or event ingestion
- Skill outputs: normalized agent status record
- Inputs: heartbeat/events/errors/queue state

3. Plugin health and drift audit
- Trigger: daily cron
- Skill outputs: plugin state report + incompatibility warnings

4. Provider-template conformance check
- Trigger: template edits or provider additions
- Skill outputs: parity report across provider template sets

5. Medical response compression policy
- Trigger: every medical-agent response
- Skill outputs: concise summary + optional expandable details block

### Convert to deterministic workflows
1. Reminder handoff workflow
- Steps:
  - classify intent
  - normalize datetime
  - route to reminders agent
  - persist reminder
  - confirm back to origin thread/topic

2. Dashboard status refresh workflow
- Steps:
  - pull gateway diagnostics/events
  - reduce to status graph
  - publish websocket payload
  - push Discord alert for critical events

3. Plugin posture workflow (daily)
- Steps:
  - list plugins
  - compare against allowlist policy
  - inspect errors/disabled criticals
  - send action report

4. Medical response formatting workflow
- Steps:
  - generate full clinical answer
  - compress to brief form
  - attach `expand-token`/follow-up path for full detail

## Lobster Analysis and Integration Plan

Repository analyzed:
- `https://github.com/openclaw/lobster` (local clone commit `b9a1b1b`)

Lobster capabilities relevant to this platform:
- Typed workflow/pipeline execution (`run`, `pipeline`).
- Hard approval gates (`approval`) for irreversible actions.
- Resume support via token/approval IDs.
- File-backed workflow state and checkpointing.
- OpenClaw tool invocation shims (`openclaw.invoke`) and `llm.invoke` stages.

Why Lobster helps here:
- Reduces non-deterministic, per-turn re-planning in repeatable operations.
- Adds explicit pause/resume approval controls for risky side effects.
- Improves reproducibility for reminders, monitoring jobs, and notification fanout.

Recommended integration pattern:
1. Keep conversational reasoning in OpenClaw agents.
2. Route repeatable multi-step operations into Lobster workflows.
3. Persist workflow state for resumability and observability.
4. Emit workflow events into Mission Control event feed.

Initial Lobster workflows to implement first:
- `reminders.capture_and_confirm`
- `mission_control.status_refresh`
- `mission_control.plugin_audit`
- `medical.concise_reply_with_expand`

## Execution Log (What was implemented in this cycle)
- Mission Control backend/frontend/migration/template updates for provider-specific model configuration.
- Gateway cron API + UI integration.
- Plugin enablements and installs:
  - enabled: `diagnostics-otel`, `lobster`, `llm-task`, `tavily`
  - installed+enabled: `@opik/opik-openclaw`
- Reminder handoff runtime probe completed with persisted reminder evidence.
- ClawHub package research completed for official + community source-linked candidates.

## Remaining High-Value Work
1. Implement dashboard status graph and ownership view (working/idle/waiting/broken + collaboration graph).
2. Enable live channel listeners and re-run reminder-topic delivery test end-to-end in Telegram topic 15.
3. Implement concise-medical-response runtime policy in medical agent prompt stack.
4. Build Lobster workflow files and wire them behind skills/commands.
5. Add configurable event notification rules (Discord sidecar integration).
