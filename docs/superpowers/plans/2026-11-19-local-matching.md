# Local-first matching implementation

Approved in conversation on 2026-11-19: implement the recommended local-first
matcher, optional Gemini evidence, and a small labelled synthetic development
corpus. Real consented reports will be supplied later. No new dependencies,
cloud writes, commits, or production accuracy claims are authorized.

## Contract

- Local matching uses public titles/descriptions, bilingual normalization,
  token Jaccard, character-trigram Dice, containment, perceptual hashes, HSV
  histogram intersection, and structured attributes.
- Gemini embeddings are optional, comparable only at matching model/dimensions
  and current content revisions. Missing or failed embeddings never block local
  matching. Evidence identifies the signals actually used.
- Keep opposite report types, different owners, active status, equal category,
  and the directional 30-day date window as hard eligibility rules.
- Keep existing outer weights initially: 0.45 text / 0.25 image / 0.30 attributes,
  or 0.60 text / 0.40 attributes without paired images. Calibrate a conservative
  threshold on synthetic development data only, never on held-out real data.
- Image features are computed from validated, re-encoded images on upload/edit.
  Add nullable versioned feature/evidence storage and an idempotent local
  backfill command. Never delete matches or claims during an upgrade.
- Preserve score/evidence snapshots for matches with claims. Reviewed ownership
  evidence must not be rewritten or made unreviewable by background re-scoring.
- Private verification details, claim answers, owners, and labels are never
  matching inputs. Corpus records contain synthetic public evidence only.
- Compare local, historical hashed-vector, and attribute baselines honestly.
  Hosted semantic comparisons remain unmeasured until actual vectors exist.

## Tasks

1. Verify current full tests and Firefox desktop/mobile baseline.
2. RED/GREEN: bilingual text, image and structured attribute features.
3. RED/GREEN: migration, uploads/edits, local/hybrid worker, claim-safe backfill.
4. RED/GREEN: deterministic labelled corpus, offline ablations, calibration,
   query bootstrap intervals and performance measurements.
5. RED/GREEN: API evidence and source/threshold snapshots; shared archival UI
   evidence and accurate local/optional semantic processing copy; documentation.
6. Full tests, lint, migration upgrade/downgrade on the dedicated test database,
   Firefox desktop 1440x900/mobile 390x844 screenshots and workflow verification,
   fresh-context review, and cleanup of only processes started for this work.

## Progress and rulings

- Baseline: `TEST_DATABASE_URL=postgresql://findiu_dev@127.0.0.1:55432/findiu_test`
  with `.venv/Scripts/python.exe -m pytest`: 99 passed, two existing upstream/test
  warnings. No Git repository is present; work stays in the shared workspace.
- Task 1 complete: Firefox screenshots of home, dashboard, report and admin at
  1440x900 and 390x844; zero script errors/overflow. Desktop dashboard/admin and
  mobile dashboard/report screenshots inspected. Existing servers were already
  running and will be left untouched.
- Ruling: use only stdlib and Pillow; Jaro-Winkler is small enough to implement
  directly. pHash, local neural models and ANN are deferred; no installation
  or packaging changes are needed.
- Task 2 complete: 16 new local-feature tests observed RED then GREEN; full suite
  115 passed. Uniform hashes are excluded from structural image evidence.
  New code introduces no Pillow deprecation warnings.
- Ruling: store hashes and a 48-bin HSV histogram in one nullable `image_features`
  JSONB column plus `feature_version`, rather than three separate feature columns.
  Value bins distinguish black/white, and the single feature document keeps the
  additive migration and invalidation atomic with less schema machinery.
- Ruling: colour families mean close shade aliases, not blanket warm/cool/neutral
  agreements. Otherwise a white/black or red/yellow mismatch gets misleading
  credit. Location-zone credit is a documented conservative heuristic.
- Ruling: preserve historical match evidence when a claim exists, not merely its
  foreign key. Re-scoring a pending claim below threshold would otherwise prevent
  the administrator from reviewing ownership evidence already submitted.
- Ruling: local text is scored even when embeddings are missing, stale or from
  different models; only the optional semantic component is excluded. Existing
  tests that treated model/revision mismatch as overall ineligibility will be
  replaced with tests of this explicitly approved behaviour.
- Integration RED/GREEN: local/hybrid fusion and no-key/provider-failure tests,
  upload/removal, claim snapshot preservation, and fenced idempotent backfill:
  19 targeted tests passed. Seven old suite expectations intentionally described
  the superseded embedding-gated behaviour and are being updated, not restored.
- Ruling: a historical match without stored evidence returns `threshold: null`.
  Displaying today's configuration as an old decision threshold would invent
  provenance. The UI will label these snapshots as historical/threshold unrecorded.
- Task 3 complete: full suite 132 passed; migration applied on the dedicated test
  database. Local matching works with no key and permanent semantic failures;
  claim snapshots, notification deduplication, image removal and backfill fencing
  are covered. Backfill CLI defaults to preview and refuses unapproved remote writes.
- Corpus/evaluation RED/GREEN: 34 targeted tests pass. Dataset generation is
  deterministic and refuses foreign/real data; physical groups are split first.
  Local evaluation needs no cache/API, retains model-versioned semantic opt-in,
  includes query-bootstrap intervals and rank-only BM25, and precision-constrained
  threshold selection never runs on the held-out split.
- Ruling: include one held-out negative with indistinguishable public clues.
  It demonstrates why similarity cannot establish ownership instead of hiding
  an irreducible failure behind artificially separable synthetic fixtures.
- Task 4 complete: full suite 141 passed. Generated 66 reports and deterministic
  illustrations; tuning selected 0.75. Frozen held-out local score: 8 TP / 1 FP /
  0 FN, precision 0.889, recall 1.0, F1 0.941. These are synthetic development
  checks only; semantic/hybrid provider metrics are explicitly unavailable.
- Ruling: per-report `semantic_consent` is required before any external embedding
  request. A global mode/key switch cannot authorize earlier local-only reports.
  The flag defaults false, is sent explicitly by the form/API, and is rechecked
  before image processing and worker writes. Unknown historical scope stays local.
  Root cause reproduced by tests: the old queue checked configuration/status but
  had no report-scoped external-processing permission.
- External consent follow-up complete: full suite 148 passed, including owner-only
  grant, stopping image requests after revocation, and evaluation-level permission
  checks. A reproduced all-black legacy grid failure is now reported as missing
  baseline evidence instead of blocking valid local evaluation.
- Final fresh-context review found four issues; each reproduced RED then GREEN:
  (1) text transmission lacked the consent/lease recheck used for images;
  (2) a non-owner edit silently reset the owner's external consent;
  (3) consented reports created before hybrid activation were marked done and
  never embedded; (4) two solid-colour photos produced full image agreement from
  a degenerate histogram. Fixed in `processing.py`, `items.py` and
  `image_features.py`; 152 tests pass.
- UI RED/GREEN: Firefox local/hybrid/historical evidence and both consent-form
  payloads pass. Technical label tests include their nested weight text; raw clue
  strings never become HTML. Updated runbooks distinguish local execution,
  optional providers, saved evidence and synthetic-only evaluation.
- Ruling: the demo was still at the initial schema and its earlier claimed image
  cosine was 1.0000000000000002. The unreleased constraint migration now permits
  1e-9 rounding tolerance; no numerical history/claim rows are rewritten. A
  dedicated test downgrade/upgrade reproduces the legacy failure, retains its
  exact component and score/claim IDs, and rejects materially invalid 1.01 values.
- Final review: fresh-context reviewer findings graded Important (consent TOCTOU
  before text transmission, non-owner consent overwrite) and Minor (deferred
  embedding of consented reports, flat-image histogram agreement). All four fixed
  RED→GREEN; final suite 152 passed, lint/format clean, final Firefox run
  `mwnz365s` passed with zero page errors/overflow. No deferred minors.
