# CampusFind Reference Rebuild

Approved direction: use the CampusFind HTML prototype and four reference screenshots as the structural/visual baseline, retaining FinDIU branding and the existing vanilla stack. No new approval, dependencies, backend changes, commits or pushes.

## Implementation
1. Replace global CSS with extracted cobalt/white/slate tokens, 1px borders, 8px controls, 12px cards, Inter/Hind Siliguri, compact 64px header and responsive layouts. Create matching geometric SVG favicon and header mark.
2. Add and use ItemCard, SearchFilterBar, MatchComparisonCard, LiveMatchSidebar, VerificationModal and StatusStepper in existing controllers. Public item components copy only allowlisted public fields; never retain secret proof. Exact Boolean is_sensitive controls preview blur, with safe alt text and an honest preview-only note.
3. Rebuild all seven HTML routes. Home is a task chooser and private-access gate. Authentication retains constraints and safe next URLs. Dashboard is a real owner-only 3/2/1 report grid with search/type/category/location/status/reset and actual claims. Report uses prototype split form, metadata vocabulary, upload, private proof and real consent. Match uses compact comparison, actual evidence and native ownership dialog. Admin preserves authorised reveal/removal, review notes and real decisions, with accurate lifecycle steps.
4. Extend EN/BN copy; language switching must preserve form values, claim answers, expanded evidence and reviewer notes. Skeleton pulse and reduced-motion handling; safe inline errors and toasts; native dialog Escape/focus/cancel.

## API Boundaries
- Existing routes, schemas, enums, permissions and URLs remain unchanged. Search q is capped at 80. All lists are owner-only, not public feeds.
- No draft-match endpoint or fake NLP. New reports say matching starts after publishing. Active saved edits may retrieve /api/v1/items/{id}/matches, labelled saved candidates independent of current edits. Actual matching requires worker/queue processing.
- Claims use existing endpoint only when can_claim. Evidence preserves local/hybrid/historical modes, exact supplied scores and null threshold as Not recorded. Approval is not handover; rejected never appears returned.
- Private proof is not included in item/comparison DOM, attributes or component state. Authorised admin proof exists in DOM only while explicitly revealed; close removes it. No contact copying, fake delivery/encryption or redaction guarantees.

## Verification
- Run scripts/verify_frontend.cjs and .venv/Scripts/python.exe -m pytest tests/test_frontend.py. Extend runnable component checks for allowlist/privacy, exact Boolean sensitive previews, malicious text, reset and shared components.
- Run scripts/verify_frontend_flow.cjs against isolated new local PostgreSQL database ending _dev, API 8001 and static frontend 5500. Adapt selectors only for intentional modal UX; retain registration, consent, evidence, owner denial, claim, note preservation, approval, handover/idempotency, edit/archive and retry assertions.
- Firefox desktop 1440x900/mobile 390x844 EN/BN screenshots plus 375/tablet/landscape overflow checks. Inspect screenshot images, correct defects and recapture. Check all seven favicons, mobile navigation, empty/loading/error states, modal keyboard dismissal and validation, saved-only sidebar.
- Keep reference folders and .env untouched. Clean up only processes started for this work; leave existing static server running. Report actual checks, screenshot paths and limitations.

## Verification Record (2026-11-22)
- `node scripts/verify_frontend.cjs`: local, hybrid and historical evidence plus explicit local/hybrid consent forms all pass.
- `python -m pytest -q`: 89 passed, 63 PostgreSQL-only tests skipped (no `_test` URL supplied), 2 dependency warnings.
- `node scripts/verify_frontend_flow.cjs` run `mwqrj5rz` against fresh `findiu_campusfind_20261121_dev` and loopback API 8001: all 14 workflow assertions pass; 22 desktop/mobile screenshots captured in `E:\Temp_User\opencode\findiu-hybrid-qa-mwqrj5rz-*`; no horizontal overflow.
- Firefox regression checks pass: filter changes immediately invalidate pagination, report sidebar failures keep a working retry without overwriting the form, EN/BN admin switching preserves expanded evidence, and preview blur applies only when `is_sensitive === true`.
- Reviewed screenshots: home, dashboard, report, match EN, admin EN/BN and auth at 1440x900 and 390x844. Layout matches the cobalt/white reference direction with no clipping or overflow.
- Hosted backend/provider/email flows remain unverified: `frontend/js/config.js` still targets localhost and no live backend URL or provider credentials were supplied. Synthetic QA data is not a real-world accuracy claim.
