# Change Report: board-group edit loading indicator

Date: 2026-05-07
Branch: detached worker-2 worktree
Commit scope: Add a visible initial-load state to the board-group edit form and cover it with a focused regression test.

## High-Level Changes
- Added an explicit loading notice to the board-group edit form so the page no longer looks like it is already saving while group details and board assignments are still loading.
- Split initial setup-loading and save states so the primary action label shows `Loading group setup…` during fetches and `Saving…` only during real mutation work.
- Preserved the existing list-level board loading copy while making the page-level action state consistent.

## File And Section References
- `frontend/src/app/board-groups/[groupId]/edit/page.tsx`: initial loading state computation, inline loading notice, submit button label.
- `frontend/src/app/board-groups/[groupId]/edit/page.test.tsx`: focused regression test for the setup-loading notice and button label.

## Verification
- `./node_modules/.bin/vitest run src/app/board-groups/[groupId]/edit/page.test.tsx`
- `./node_modules/.bin/eslint src/app/board-groups/[groupId]/edit/page.tsx src/app/board-groups/[groupId]/edit/page.test.tsx`
- `./node_modules/.bin/tsc --noEmit`
- `lsp_diagnostics` on modified TSX files returned zero errors.

## Risks And Follow-Ups
- None known for this slice; broader edit-form loading polish may still be needed elsewhere in the branch.
