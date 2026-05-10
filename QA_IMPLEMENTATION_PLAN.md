# QA Review Implementation Plan

Date: 2026-05-10
Source: QA_REVIEW.md

## Goal

Reduce long-term maintenance risk by decomposing large backend/frontend modules, removing import-time side effects, tightening engineering quality gates, and improving scalability.

## Current Status Snapshot

Verified complete:
- Phase 1 tooling and guardrails.
- Most of Phase 0 safety work.
- Phase 2 backend app boundary split (including dedicated duplicates blueprint registration).
- Phase 6 CSS ownership cleanup for action menus/load-more/button focus selectors.
- Phase 7 background duplicate task architecture (task lifecycle, status, cancellation, frontend task-aware flow).
- Cross-cutting Vue dependency hardening (vendored local Vue ESM build).

Partially complete:
- Phase 3: composables were split out, but `frontend/vue/useAssetViewer.js` still owns a large watcher-driven orchestration layer.
- Phase 4: backend services were extracted, but broad catch-all handling and service-level test granularity still need cleanup.
- Phase 5: view components were split, but several views are still mostly prop-forwarding shells.

Still pending:
- Additional decomposition work in Phase 3 through Phase 5.

## Estimation Model

- Unit: engineering days (1 engineer, focused implementation)
- Ranges include coding, tests, and light documentation
- Total calendar time depends on interruptions and review cycles

## Recommended Execution Order

## Phase 0 - Safety Baseline (Quick Wins)

Why first:
- Low-risk changes that reduce immediate operational and debugging risk.
- Improves confidence before larger refactors.

Scope:
- Move `ensure_tag_list()` out of import path and into app startup or lazy path.
- Replace `print()` usage in backend with module loggers.
- Add constants for repeated metadata mode strings and badge keys.
- Remove obvious CSS duplication hotspots (especially button style overlap) without broad renaming yet.
- Add test coverage for concurrent-like settings updates during active asset requests.

Estimate:
- 2 to 4 days

Exit criteria:
- No import-time network/file side effects in server import path.
- Logging is structured and level-based in backend hotspots.
- New regression tests pass in CI/local.

## Phase 1 - Guardrails And Tooling

Why now:
- Prevents quality regression while code is being split.
- Gives immediate signal on style, typing, and basic correctness.

Scope:
- Add `ruff` to `pyproject.toml` with baseline rules.
- Add pragmatic type checking (`mypy` or pyright-lite) focused on:
  - request/response models
  - settings models
  - service/API boundaries
  Avoid full-repo typing theater at this stage.
- Add frontend formatter/linter setup (consistent with current stack).
- Add commands/doc updates so contributors can run checks quickly.

Estimate:
- 1 to 2 days

Exit criteria:
- One command (or short command set) runs lint + type checks + tests.
- Baseline checks are documented and reproducible.

## Phase 2 - Backend App Boundary Refactor

Why before deeper service splits:
- Creates clear architecture seams needed for all backend changes.
- Reduces coupling risk in `backend/server.py` first.

Scope:
- Introduce Flask app factory (`create_app`) and configuration boundary.
- Add blueprint separation (`assets`, `tags`, `settings`, `duplicates`).
- Remove mutable module-level global dependency patterns where possible.
- Preserve existing API contracts.
- Keep module count practical; prefer clear ownership over many tiny layers.

Estimate:
- 4 to 7 days

Exit criteria:
- `backend/server.py` becomes thin entrypoint/bootstrap.
- Routes are grouped by domain via blueprints.
- Existing API tests pass without behavior regressions.

## Phase 3 - Frontend State Decomposition (Pulled Earlier)

Why now:
- This is the largest near-term maintainability risk and likely the first source of feature velocity loss.
- Decomposition here reduces future churn in selection, keyboard, modal, and async orchestration.

Scope:
- Decompose `frontend/vue/useAssetViewer.js` into domain composables:
  - `useAssets`
  - `useTags`
  - `useDuplicates`
  - `useSettings`
  - `useSelection`
  - `useKeyboardShortcuts`
- Reduce watcher-driven orchestration in favor of explicit actions/events.

Estimate:
- 5 to 8 days

Exit criteria:
- Main composable is orchestration shell, not monolith.
- Core flows (browse, tags, duplicates, settings, upload/delete) remain stable.

## Phase 4 - Backend Service Decomposition

Why after app factory and frontend state split:
- App boundaries are stable, and frontend-side complexity has been reduced first.
- Service extraction is now safer and easier to validate.

Scope:
- Split `backend/asset_viewer.py` into focused services:
  - roots/service
  - scanning/filtering
  - metadata parsing
  - thumbnails
  - duplicates
  - trash/delete safety
- Narrow broad `except Exception` blocks in internal logic.
- Add/expand tests per service module.
- Avoid over-engineering layers; optimize for clear module ownership.

Estimate:
- 6 to 10 days

Exit criteria:
- `scan_assets()` and `scan_duplicate_assets()` responsibilities are split.
- Service modules have focused tests and cleaner error handling.

## Phase 5 - Frontend View Component Split

Why after composables:
- UI componentization is cleaner when state ownership is already separated.

Scope:
- Split large inline template in `frontend/asset_viewer_vue.js` into view components:
  - `AssetsView`
  - `TagsView`
  - `DuplicatesView`
  - `StatsView`
  - `SettingsView`
  - modal components as needed
- Ensure each view owns local UI state where appropriate.

Estimate:
- 4 to 7 days

Exit criteria:
- App shell remains readable and thin.
- Views are independently testable and easier to iterate.

## Phase 6 - CSS Ownership And Design System Cleanup

Why after component split:
- CSS scopes can align with stable component boundaries.

Scope:
- Consolidate button system (`.btn`/`.button`) into one pattern.
- Define a small design-system layer (buttons, fields, panels, badges).
- Replace generic global selectors with feature-prefixed classes (`assets-*`, `duplicates-*`, `settings-*`).
- Reduce hard-coded style values using tokens.

Estimate:
- 3 to 5 days

Exit criteria:
- Clear style ownership by feature/component.
- Lower risk of cross-feature style regressions.

## Phase 7 - Background Duplicate Task Architecture

Why this is architectural (not just performance):
- Long-running duplicate work changes API semantics, cancellation, progress, and state ownership.
- Defining task boundaries here reduces backend/frontend coupling long-term.

Scope:
- Introduce task abstraction for duplicate scanning jobs.
- Add progress endpoints and cancellation endpoints.
- Move duplicate scans to detached/background execution path.
- Align frontend orchestration with explicit task lifecycle states.

Estimate:
- 5 to 9 days

Exit criteria:
- Duplicate scans run outside request-response blocking path.
- Progress and cancellation are first-class, documented API behaviors.
- UI uses explicit task states instead of implicit watcher coupling.

## Cross-Cutting Item: Vue Dependency Hardening

Recommended timing:
- Complete in Phase 1 or Phase 4 (whenever frontend checks are introduced).

Scope:
- Replace CDN Vue with vendored or package-managed dependency.

Estimate:
- 1 to 2 days

## Total Effort

- Core refactor plan (Phases 0-7): 30 to 52 engineering days
- With contingency (15%): 35 to 60 engineering days

Approximate schedule examples:
- 1 engineer: 7 to 12 weeks
- 2 engineers (parallelizable phases): 4 to 7 weeks

## Parallelization Guidance

Safe parallel workstreams after Phase 3:
- Backend service split (Phase 4) can run alongside frontend component split (Phase 5)
- CSS cleanup (Phase 6) should follow most of Phase 5 to avoid rework
- Background task work (Phase 7) can begin API design while late Phase 4 is finishing

## Suggested Milestones

1. Milestone A (Week 1): Phases 0-1 complete.
2. Milestone B (Weeks 2-3): Phase 2 complete (app factory + blueprints).
3. Milestone C (Weeks 4-5): Phase 3 complete (composable decomposition).
4. Milestone D (Weeks 6-8): Phases 4-5 complete.
5. Milestone E (Weeks 8-10): Phases 6-7 complete + stabilization.

## Risk Notes

- Highest regression risk: backend route migration and frontend state decomposition.
- Highest schedule risk: duplicate scan architecture and cancellation semantics.
- Risk control: ship phase-by-phase behind stable API contracts and expand test coverage at each phase boundary.

## Practical Guardrails

- Prefer explicit modules and ownership over abstract enterprise layering.
- Do not explode into many tiny service files unless complexity demands it.
- Keep typing focused on boundaries and data contracts first.
