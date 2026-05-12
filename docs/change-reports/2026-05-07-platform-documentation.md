# Change Report: Platform Documentation

Date: 2026-05-07
Branch: amish/mission-control-live-ops-20260506
Commit scope: Add a complete current-state platform manual for Mission Control.

## High-Level Changes
- Added a canonical Mission Control platform manual covering product purpose,
  repository structure, runtime architecture, data model, API surfaces, frontend
  pages, authentication, gateway/runtime integration, runtime visibility setup,
  development, deployment, readiness checks, testing, troubleshooting, known
  limitations, and change discipline.
- Updated the docs index so operators and contributors can start from the new
  manual.
- Updated the architecture page from a placeholder into a concise map that links
  to the platform manual and names the main architectural flows.

## File And Section References
- `docs/platform/README.md`: complete platform manual.
- `docs/README.md`: docs navigation updated with the platform manual and
  architecture links.
- `docs/architecture/README.md`: architecture summary and references.

## Verification
- Documentation was grounded in current repo structure, route wiring, model files,
  service files, and frontend route files.
- Pending verification: markdown lint.

## Risks And Follow-Ups
- The manual is current-state documentation as of 2026-05-07 and should be
  updated when API routes, frontend pages, runtime sync, or deployment units
  change.
- Full generated OpenAPI endpoint-by-endpoint reference remains in the backend
  OpenAPI output and generated client; the manual intentionally summarizes by
  domain.
