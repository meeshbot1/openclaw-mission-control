# Change Report: agent creation loading indicator

Date: 2026-05-07
Branch: detached worker-2 worktree
Commit scope: Add a visible initial-load state to the agent creation form and cover it with a focused regression test.

## High-Level Changes
- Added an explicit loading notice to the new agent form so admins can see that board options are still loading instead of seeing a disabled form with no explanation.
- Split initial board-loading and create-mutation states so the primary action label shows `Loading boards…` during fetches and `Creating…` only during the actual mutation.
- Disabled the board selector while the initial board query is still pending to avoid opening an empty control.

## File And Section References
- `frontend/src/app/agents/new/page.tsx`: initial loading state computation, board selector disable behavior, inline loading notice, submit button label.
- `frontend/src/app/agents/new/page.test.tsx`: focused regression test for the new board-loading notice and button label.

## Verification
- `./node_modules/.bin/vitest run src/app/agents/new/page.test.tsx`
- `./node_modules/.bin/eslint src/app/agents/new/page.tsx src/app/agents/new/page.test.tsx`
- `./node_modules/.bin/tsc --noEmit`
- `lsp_diagnostics` on modified TSX files returned zero errors.

## Risks And Follow-Ups
- None known for this slice; other edit/create forms may still need similar loading-state treatment elsewhere in the feature branch.
