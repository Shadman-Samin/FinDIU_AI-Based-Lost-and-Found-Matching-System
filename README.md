# FinDIU

Campus lost-and-found matching with private evidence and an admin-mediated return.
Similarity identifies a candidate; it never establishes ownership.

## Local Setup

Requires Python 3.10+ and PostgreSQL. Install with `pip install -e ".[dev]"`.
Set the variables in `.env.example` in a local `.env`, never in frontend code.

For an offline demo, set `MATCHING_MODE=local`, `EMBEDDING_PROVIDER=local` and
`STORAGE_PROVIDER=local`. Matching uses bilingual lexical comparisons, perceptual
hashes, colour histograms and structured clues. No Gemini key or new dependencies
are needed. The old hashed-vector provider is an evaluation baseline only.

Optional `MATCHING_MODE=hybrid` with `EMBEDDING_PROVIDER=gemini` and a Gemini key
adds compatible semantic evidence. Missing/failed embeddings never block local
matching. Only reports whose owners explicitly granted `semantic_consent` may
be sent to Gemini; enabling a key cannot opt in earlier local-only reports.

Run migrations from the project root:

```powershell
python -m alembic -c backend/alembic.ini upgrade head
python -m scripts.backfill_local_features
python -m scripts.backfill_local_features --apply
python -m uvicorn backend.app.main:create_app --factory --port 8000
```

In another terminal, run `python -m http.server 5500 --directory frontend`.
Open `http://localhost:5500`. The frontend API address is in
`frontend/js/config.js`; it must match the deployed backend.

For the offline local demo only, run `python -m scripts.local_worker --watch` in
another terminal. It processes queued reports every ten seconds, refuses remote
databases/providers, and sends no email. Production uses the authenticated cron
tick instead.

Set `ADMIN_EMAIL` and a strong `ADMIN_PASSWORD` in the process environment, then
run `python -m backend.seed_admin`. This is an explicit operation, never an API.

## Verification

Use a separate PostgreSQL database ending in `_test`:

```powershell
$env:TEST_DATABASE_URL="postgresql://user:password@localhost/findiu_test"
python -m pytest -q
python -m ruff check backend tests scripts
python -m ruff format --check backend tests scripts
```

Tests refuse the configured application database. There is no SQLite substitute
for the PostgreSQL lifecycle, lease and locking tests.

## Deployment

Use a private Supabase bucket and the non-exposed `findiu` database schema.
Run migrations before starting Render with
`uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port $PORT`.
Configure private Supabase service credentials, Brevo sender, a random JWT secret,
a separate random tick token, HTTPS frontend URL and explicit CORS origins.
Never deploy the development secrets or local storage on ephemeral Render disks.
Gemini is optional; enable hybrid mode only after explicit owner consent and live
provider checks. The same local algorithms can run in a hosted API; "local" means
on the server, not in the browser or a guarantee that database/storage is on-site.

Publish `frontend/` as the static site after setting its API URL. Configure one
cron job every ten minutes to POST `/internal/tick`, with the tick secret in an
Authorization bearer header. Do not place that token in a URL.

Before submission, verify private signed image URLs,
one delivered notification, scheduled ticks and an entire claim/handover flow.
These checks require the team's service accounts; unit tests do not replace them.
Live text/image embeddings are an additional gate if hybrid mode is enabled.

## Evaluation And Limits

The threshold 0.75 was retained by synthetic development calibration and remains
provisional for real reports. Collect independently labelled lost/found pairs
including Bangla, English, mixed-language descriptions, absent photos and visually
similar unrelated objects. Split training/tuning and final test examples before
threshold selection. Report precision, recall, F1, recall@5, latency, provider and
dimension; include false positives and false negatives. Do not report the local
demo's matching rate as production AI accuracy.

The UI supports English/Bangla fixed copy, metadata labels, status and error
messages; user-entered evidence is preserved in its original language. Language
switching preserves the current form and admin review notes. A recorded student usability
study and a native-language copy review remain release gates. Free hosting can sleep or
pause; in-memory throttles reset on restart. Email is at least once under ambiguous
provider timeouts. Signed image URLs are bearer capabilities for five minutes.
Uploads orphaned by a crash require an admin comparison of storage object names
against database image references; do not remove objects referenced by any report.

## Evaluation Runner

The 66-report development corpus is reproducible and explicitly synthetic:

```powershell
python -m scripts.build_dev_corpus
python -m scripts.evaluate data/evaluation/synthetic-v1/reports.jsonl --engine local --split tune --output reports/synthetic-v1-tune.json
python -m scripts.evaluate data/evaluation/synthetic-v1/reports.jsonl --engine local --split test --threshold 0.75 --output reports/synthetic-v1-heldout.json
```

Use a different directory for later consented real items. Select/freeze their
threshold on their tune split before inspecting their final test split. Local
evaluation needs no cache or account; its hashed baseline is not Gemini evidence.
For genuine cached vectors, use `--engine hybrid --cache ... --model ...
--dimensions ...`. Missing vectors fail offline. `--allow-api` additionally
requires explicit `consent_for_external_ai: true` on every report; local consent
alone cannot authorize network processing. See `reports/evaluation.md` and
`docs/matching-algorithms.md` for ablations, limitations and exact algorithms.

User/admin instructions: `docs/user-guide.md`. Operations and deployment:
`docs/deployment.md`. Rehearsal: `docs/demo.md`. Human study protocol:
`reports/usability.md`. Current locally observed evidence: `docs/verification.md`.
