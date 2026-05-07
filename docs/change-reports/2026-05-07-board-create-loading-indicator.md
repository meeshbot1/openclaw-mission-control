# Change Report: board creation loading indicator

Date: 2026-05-07
Branch: detached worker-2 worktree
Commit scope: Add a visible initial-load state to the new board form and cover it with a focused regression test.

## High-Level Changes
- Added an explicit loading notice to the new board form so users can see that gateway and group options are still loading instead of encountering a disabled form with no explanation.
- Split initial setup-loading and create-mutation states so the primary action label shows `Loading board setup…` during fetches and `Creating…` only during submission.
- Disabled the gateway selector during the initial loading phase to avoid interacting with an empty option list.

## File And Section References
- `frontend/src/app/boards/new/page.tsx`: initial loading state computation, selector disable behavior, inline loading notice, submit button label.
- `frontend/src/app/boards/new/page.test.tsx`: focused regression test for the setup-loading notice and button label.

## Verification
- `./node_modules/.bin/vitest run src/app/boards/new/page.test.tsx`
- `./node_modules/.bin/eslint src/app/boards/new/page.tsx src/app/boards/new/page.test.tsx`
- `./node_modules/.bin/tsc --noEmit`
- `lsp_diagnostics` on modified TSX files returned zero errors.

## Risks And Follow-Ups
- None known for this slice; other create/edit forms may still need similar loading-state treatment elsewhere in the branch.
