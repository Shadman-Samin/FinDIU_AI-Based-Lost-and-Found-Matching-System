# Local Verification

Current status (2026-11-19): local-first hybrid matching, per-report external-AI
consent, evidence snapshots, synthetic evaluation and archival evidence UI are in
place. Services restarted on current code: API 8000, static frontend 5500, QA API
8001, PostgreSQL 55432. No provider API keys were used.

## Automated checks

With a dedicated PostgreSQL `_test` database:
`TEST_DATABASE_URL=postgresql://findiu_dev@127.0.0.1:55432/findiu_test`.

- `python -m pytest -q`: **152 passed**, 2 pre-existing dependency/test warnings.
- `python -m ruff check .`: clean after import ordering fixes.
- `python -m ruff format --check backend scripts tests`: clean on touched files.
- `node --check` on the seven changed frontend scripts: clean.
- A dedicated downgrade/upgrade test reproduces a legacy claimed match with
  `image_sim = 1.0000000000000002`, preserves its exact score/claim ID through
  the new 1e-9 constraint, and rejects a materially invalid `1.01` value.

## Synthetic evaluation

The 66-report fixture corpus is deterministic and labelled synthetic; see
`data/evaluation/synthetic-v1/README.md`, `reports/evaluation.md` and
`docs/matching-algorithms.md`. Tune retained threshold **0.75** (18 queries,
61 eligible pairs, 16 TP / 0 FP / 0 FN). With that value fixed before inspection,
the held-out synthetic split produced 8 TP / 1 FP / 0 FN, precision 0.889,
recall 1.0, F1 0.941 (8 queries, 12 eligible pairs). The single false positive is
a deliberately indistinguishable second student-card sleeve. These are development
checks only, not real-world accuracy or hosted-provider evidence.

Ablations: synonyms improved synthetic recall 0.563 -> 1.0; attribute-only
precision was 0.571; hash-only precision was 0.400. Image, colour-histogram and
location-zone ablations changed no accepted pair on this small corpus, so no gain
is claimed for them here. Genuine semantic/hybrid metrics remain unmeasured.

## Firefox end-to-end

Playwright/Firefox, desktop 1440x900 and mobile 390x844, against the isolated QA
API and labelled synthetic accounts/reports only. Final run after review fixes:
`mwnz365s`.

Verified: registration/login, report form and photo preview/removal, explicit
local-only consent, local candidate generation and evidence, English/Bangla
evidence ledger, shared clue terms rendered as text, privacy denial to a stranger,
claim submission, admin review-note preservation across language switching,
approval, idempotent physical handover, no-candidate state, edit/archive, search,
and temporary server-error retry. Zero page errors, zero horizontal overflow.

Screenshots (22) under `E:/Temp_User/opencode/findiu-hybrid-qa-mwnz365s-*.png`
were inspected for home, auth, register, report, dashboard, match (English and
Bengali), admin (English and Bengali), no-candidate and error states. Independent
component checks also covered hybrid/historical evidence and both consent-form
payloads.

Visual audit: warm archival system, claim-slip perforation and stamped score,
clear hierarchy within two seconds, mono metadata, responsive cards and readable
Bengali Tiro Bangla/Noto Sans Bengali. Detailed evidence stays collapsed until
requested; the saved score remains primary. No generic gradient/glass styling.

## Consent and privacy checks

- `semantic_consent` defaults false; the form/API sends it explicitly.
- Enabling a Gemini key/mode never opts in prior local-only reports.
- Only the report owner may grant external permission; admin grant returns 403.
- Revoking consent stops remaining image requests; a recheck occurs before writes.
- Evaluation `--allow-api` requires explicit per-record `consent_for_external_ai`.
- Private proof/claim answers never enter features, evidence, logs or public API.

## Not demonstrated

Live Gemini quality/latency, Supabase bucket policy, delivered Brevo email, cloud
uptime, native-language copy review, real labelled evaluation metrics and student
usability results. No production accuracy or cloud-readiness claim is made.
Free hosting may sleep; throttles reset; email can duplicate after ambiguous
provider timeouts; signed image URLs are five-minute bearer capabilities.
