# FinDIU Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify the complete bilingual lost-and-found demonstration, including real text/image matching, private reports, notifications, claims, and admin-mediated return.

**Architecture:** One static frontend calls one FastAPI application. PostgreSQL stores four application tables and durable work state; Supabase stores private images. Scheduled backend processing generates embeddings, matches reports, and sends Brevo email without a separate queue service.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, Pydantic settings, SQLAlchemy 2, psycopg 3, Alembic, PyJWT, argon2-cffi, Pillow, HTTPX, google-genai, pytest, plain HTML/CSS/JavaScript, Pico.css.

**Spec:** `docs/superpowers/specs/2026-11-16-findiu-design.md`

## Global Constraints

- Preserve all features in the original Bengali plan.
- Runtime must use free cloud services without depending on a local computer.
- Similarity identifies candidates, never ownership.
- Database credentials, storage service keys, Gemini keys, and Brevo keys stay on the backend.
- Signed JWTs expire after one hour.
- List endpoints are paginated, default 20 and maximum 100 records.
- Accept at most one JPEG or PNG image, up to 5 MiB and 20 megapixels.
- Signed URLs expire after five minutes and are generated only after authorization.
- Model: gemini-embedding-2, requested output dimensionality 768.
- Use real PostgreSQL integration tests; never run tests against a deployment database.
- No commits, pushes, account creation, billing changes, or cloud writes without user authorization.
- Start with ordinary modules; do not introduce provider interfaces, repository classes, Redis, Celery, React, or a vector database.

## Review Focus

- Parallel admin approvals of claims sharing a found item must have exactly one winner; test in Task 9 with independent DB connections.
- An old embedding worker finishing after an edit must not overwrite current content; test in Task 5 using a blocked provider response.
- A forged filename/MIME type or decompression bomb must not bypass upload checks; test in Task 3 with decoded fixtures.
- A stale candidate email link must not expose an invalidated report; test Task 6 API access and Task 10 browser behavior.
- Dhaka midnight, missing attributes, and bilingual normalization must not silently change eligibility or invent evidence; test Tasks 3 and 4 using fixed dates.

## Workspace and Execution Rules

Only two documentation files and the original Bengali plan exist at planning time.
Python 3.10.5 is available. Docker and psql are not on PATH; their availability
elsewhere on this machine has not been established. No tests or provider calls
have been run. Use a dedicated PostgreSQL database supplied by the user, or verify
an existing local installation before proposing an installation. Do not provision
external services during local implementation without authorization.

These tasks form one integrated delivery plan: reports, matching, privacy, and
claim transactions share contracts and are not independently deployable projects.
Tasks 1-6 and the milestone UI subset of Task 7 are the first working slice.
Tasks 8-10 complete the recovery workflow. Tasks 11-12 produce final evidence.

Run commands from the project root in PowerShell. Once Task 1 exists, use
`.\.venv\Scripts\python.exe` and installed scripts explicitly. The test suite must
fail clearly if its required database is unavailable; missing integration tests
cannot be counted as passed. Record exact installed versions after resolution.

## File Map

| Files | Responsibility |
| --- | --- |
| pyproject.toml, .gitignore, .env.example, README.md | Dependencies, safe configuration, development commands |
| backend/__init__.py, backend/app/__init__.py | Python package markers |
| backend/app/main.py, config.py, db.py, errors.py | App factory, settings, sessions, safe errors |
| backend/app/models.py, schemas.py, metadata.py | Four ORM models, typed API payloads, bilingual controlled values |
| backend/alembic.ini, backend/migrations/env.py, backend/migrations/versions/0001_initial.py | Reproducible PostgreSQL schema |
| backend/app/auth.py, limits.py, seed_admin.py | Password/JWT/access helpers, throttling, explicit admin creation |
| backend/app/image_utils.py, storage.py | Decode/re-encode images and private storage HTTP calls |
| backend/app/attributes.py, matcher.py | Pure scoring plus transactional candidate persistence |
| backend/app/embedder.py, tick.py, notify.py | Real providers and bounded database-backed processing |
| backend/app/routers/{auth,items,matches,claims,admin,internal}.py | HTTP entry points, dependencies, authorization |
| tests/conftest.py, tests/test_*.py | Isolated fixtures and focused regression/integration checks |
| frontend/{index,auth,report,dashboard,match,admin}.html | Six responsive pages |
| frontend/js/{config,api,i18n,auth,report,dashboard,match,admin}.js | Shared HTTP/translation logic and page behavior |
| frontend/style.css, frontend/locales/{en,bn}.json, frontend/vendor/{pico.min.css,LICENSE} | Styling, translations, licensed vendored CSS |
| scripts/{probe_services,evaluate,load_demo}.py | Explicit live probes, reproducible evaluation, non-sensitive demo data |
| data/evaluation/{pairs.jsonl,README.md}, reports/{evaluation,usability,testing}.md | Dataset contract and measured evidence |
| render.yaml, frontend/vercel.json, .github/workflows/test.yml | Deployment templates, frontend headers, automated tests |
| docs/{deployment,user-guide,demo,module-notes}.md | Operations, usage, rehearsals, team explanations |

Create files when their task needs them, not empty stubs for future tasks.

## Shared Interfaces and Clarifications

Use synchronous SQLAlchemy sessions and ordinary `def` FastAPI handlers. HTTPX
and Gemini calls are synchronous with explicit timeouts. FastAPI runs synchronous
handlers in its thread pool. Do not block an async handler with sync I/O.

`create_app(settings: Settings | None = None) -> FastAPI` accepts explicit test
settings. `get_session()` yields one Session; transactions belong to service
operations. `get_current_user()` loads the user from the validated JWT subject.
`require_admin()` checks the current DB role. Test fixtures override the session
dependency rather than connecting to production.

`Item` additionally has `revision` (all edits), `content_revision` (matching-input
edits only), and `embedded_revision` (the content revision vectors describe).
PATCH's `expected_revision` compares against `revision`. A private-detail-only edit
increments `revision` without invalidating vectors or matches. This disambiguates
the specification's edit and embedding revisions without changing its behavior.

Each external-work row has a UUID lease token as well as lease expiry. Writes must
match lease token and input revision. Clearing an expired lease does not make an
old response authoritative. Matching uses item locks and revision comparisons.

Embedding vectors may be partially present: a successful text vector is usable
when embedded_revision equals content_revision, even if image work is pending.
Only missing vectors are retried. Completing image work sets match_pending again.
Terminal image failure preserves text matching and displays reduced evidence.

Notification statuses are pending, processing, sent, failed, cancelled; embedding
statuses are pending, processing, ready, failed. Cancelling pending notification
does not erase notified_at. A new valid unsent pair queues notification; an existing
sent pair never queues a second initial alert. Approved pair details remain visible
to participants after reservation/return, but claim eligibility becomes false.

`ServiceFailure(code: str, retryable: bool, retry_after: float | None = None)` is
defined in errors.py and used by provider modules. Never persist exception strings
containing content or credentials. All datetime values used by workers are UTC.

Throttles initially allow 5 login attempts/minute/IP, 3 registrations/hour/IP,
10 reports/hour/user, 10 claims/hour/user. Keep values in config. Do not trust a
client-supplied forwarding header without a documented trusted proxy configuration.
An oversized multipart body must be rejected while streaming, not only after parsing.

Serialize short report-edit/archive and claim lifecycle transactions with the same
PostgreSQL transaction advisory lock, acquired before item row locks:

```python
session.execute(text('SELECT pg_advisory_xact_lock(6071101)'))
```

Import text from SQLAlchemy. This demonstration-level lock keeps competing claim
graphs safe without recursively locking reports. Never acquire it during storage,
embedding, email, or other network I/O. Keep stable UUID ordering for item locks.
Its ceiling is serialized lifecycle writes; replace with finer-grained locking only
if measured usage requires it. Matching workers retain their own row/revision checks.

### Task 1: Runnable API and Isolated PostgreSQL Test Harness

**Files:** Create pyproject.toml, .gitignore, .env.example, README.md,
backend package markers, backend/app/{main,config,db,errors}.py, tests/conftest.py,
tests/test_health.py, .github/workflows/test.yml.

**Produces:** Settings, create_app, get_session, ServiceFailure; pytest fixtures
`client`, `db_session`, `session_factory`, `settings`.

- [ ] Create packaging with Python >=3.10 and direct dependencies from the tech stack;
  use psycopg[binary], python-multipart, email-validator, pytest and ruff. Configure
  package discovery for backend only. Ignore .venv, .env, caches and report artifacts
  containing private input. .env.example contains blank secrets, not working keys.
- [ ] Verify the root exists before `python -m venv .venv`; install with
  `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.
- [ ] Write this health test before implementing create_app:

```python
def test_health_does_not_require_provider_calls(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
```

- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_health.py -v`;
  first observe missing app/fixture failure, then implement app factory and rerun.
- [ ] Implement /ready using SELECT 1, returning 503 with sanitized DB errors.
  Test unavailable DB returns 503 without the connection URL in the response.
- [ ] Require TEST_DATABASE_URL explicitly and a database name ending `_test` for
  integration fixtures. Refuse a URL equal to DATABASE_URL, including normalized
  credential/driver variants pointing to the same host/database. Never drop the DB.
  Apply migrations once and use a transaction/savepoints for ordinary tests;
  concurrent tests use independent transactions and delete only their fixture rows.
- [ ] Add CI PostgreSQL service with disposable findiu_test DB and run migrations,
  pytest and ruff. Pin compatible resolved dependencies; document how to reproduce.
  Do not publish CI configuration to GitHub yet.

### Task 2: Schema, Authentication, and Admin Seed

**Files:** Create models.py, schemas.py, auth.py, limits.py, seed_admin.py,
routers/auth.py, migration files; modify main.py; tests/test_auth.py,
tests/test_models.py.

**Consumes:** Task 1 settings/session/errors. **Produces:** User, Item, Match, Claim,
JWT dependencies, all initial schema enums/constraints, /api/v1/auth endpoints.

- [ ] Write tests for case-normalized duplicate emails, forged admin role on
  registration, wrong password, expired/wrong-audience JWT, and live DB role checks.
  Use this endpoint assertion after registering a normal user:

```python
def test_registration_cannot_choose_admin(client):
    response = client.post('/api/v1/auth/register', json={
        'name': 'Demo', 'email': 'demo@example.test',
        'password': 'long-demo-password', 'role': 'admin',
    })
    assert response.status_code == 422
```

- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_models.py -v`
  and confirm failure before implementing routes/models.
- [ ] Build all four tables using the approved spec plus shared clarifications.
  Store them in non-exposed `findiu` schema. Use unique pair/claim constraints,
  enum/check constraints, JSONB vectors, indexes and timezone-aware timestamps.
  Raw cosine fields allow [-1,1]; composite/attribute scores allow [0,1].
- [ ] Implement Argon2, fixed HS256 validation, required JWT claims, one-hour expiry,
  normalized emails and strict input schemas (`extra='forbid'`). Return generic
  invalid-credentials errors. Set core startup secret minimum to 32 characters.
- [ ] Implement throttle windows with a monotonic clock and bounded eviction.
  Verify a sixth login attempt in one minute returns 429; clear test limiter state
  per test. Do not make readiness failures consume login quota.
- [ ] Implement explicit `python -m backend.app.seed_admin`; require seed variables,
  refuse silent role escalation or overwriting an existing account/password.
- [ ] Run migrations on the dedicated DB, then rerun the task tests and ruff.

### Task 3: Reports, Private Images, and Safe Edits

**Files:** Create metadata.py, image_utils.py, storage.py, routers/items.py;
modify schemas.py/main.py; tests/test_images.py, tests/test_items.py.

**Consumes:** User authentication and ORM models. **Produces:**
`prepare_image(raw: bytes) -> bytes` (sanitized JPEG),
`Storage.upload(path: str, jpeg: bytes) -> None`, `download(path) -> bytes`,
`delete(path) -> None`, `signed_url(path, expires_in=300) -> str`, report endpoints.

- [ ] Write a decoded-image test, not an extension-only test:

```python
def test_filename_cannot_make_text_an_image():
    import pytest
    from backend.app.image_utils import prepare_image
    from backend.app.errors import ServiceFailure
    with pytest.raises(ServiceFailure):
        prepare_image(b'this is not an image')
```

- [ ] Add tests for forged MIME, oversized bytes/pixels, animated PNG, EXIF rotation,
  stripped metadata and longest edge <=1024. Run
  `.\.venv\Scripts\python.exe -m pytest tests/test_images.py -v` before/after code.
- [ ] Implement bounded upload middleware (6 MiB multipart body cap, 5 MiB image
  cap), Pillow decode/validation and JPEG re-encoding. Count streamed bytes even
  when Content-Length is absent. Reject oversized inputs with 413.
- [ ] Use HTTPX to call Supabase Storage with private credentials and ten-second
  timeouts. Mock requests in tests; no SDK/provider abstraction needed.
- [ ] Implement metadata with initial category IDs bottle, bag, keys, wallet, phone,
  electronics, documents, clothing, other; colors black/white/blue/red/green/yellow/
  brown/gray/other/unknown; locations campus/library/classroom/cafeteria/transport/
  other/unknown. Describe these broad areas honestly; they are not verified buildings.
- [ ] Write report tests: consent required, future Dhaka date rejected, private fields
  hidden from another user, upload rollback cleanup, no signed URL before access,
  stale edit 409, private-only edit retains vectors, matching edit invalidates pairs,
  unchanged image survives failed replacement. Use injected date/clock for midnight.
- [ ] Implement report writes with owner/active/pending-claim checks and row locks.
  PATCH supports `remove_image=true`, rejects simultaneous replacement/removal,
  requires expected_revision and forbids owner/type changes. Archive cancels matches
  and unsent notifications transactionally. Enforce all spec character limits.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_images.py tests/test_items.py -v`.

### Task 4: Pure Attribute and Vector Scoring

**Files:** Create attributes.py, matcher.py pure scoring functions;
tests/test_scoring.py.

**Consumes:** canonical report fields and config. **Produces:**
`attribute_score(lost: Item, found: Item) -> float`,
`cosine(a: list[float], b: list[float]) -> float`,
`score_pair(lost: Item, found: Item, settings: Settings) -> dict[str, float | None]`.

- [ ] Write and run the exact missing-image weighting regression:

```python
def test_missing_image_uses_text_attribute_weights(settings, scored_pair):
    from backend.app.matcher import score_pair
    lost, found = scored_pair
    lost.image_embedding = found.image_embedding = None
    parts = score_pair(lost, found, settings)
    assert parts['image_sim'] is None
    assert abs(parts['score'] - (
        .6 * max(0, parts['text_sim']) + .4 * parts['attr_score']
    )) < 1e-9
```

- [ ] Add `scored_pair` fixture producing finite 768-dimensional unit vectors and
  known attributes. Test NaN, infinity, zero vector, dimension/model mismatch,
  missing brand/color (no agreement), NFKC/casefold/trim brand normalization,
  identical vectors, negative cosine, both-image weights, and 0/30/31-day boundaries.
- [ ] Implement using math and stdlib normalization; no NumPy/scikit-learn needed.
  Keep date eligibility separate from scoring and use configured window consistently.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_scoring.py -v` and ruff.

### Task 5: Real Embeddings and Recoverable Tick Processing

**Files:** Create embedder.py, tick.py, routers/internal.py;
tests/test_embeddings.py, tests/test_tick.py; modify config.py/main.py.

**Consumes:** Storage, vectors, ServiceFailure, session_factory.
**Produces:** `embed_text(text: str, settings: Settings) -> list[float]`,
`embed_image(jpeg: bytes, settings: Settings) -> list[float]`,
`run_tick(session_factory, settings: Settings) -> dict[str, int]`.

- [ ] Write tests that record embedding inputs and assert private_detail is absent;
  text succeeds/image fails; only missing image retries; nonfinite vectors fail;
  429 honors Retry-After; credential error terminates retry; missing key never fakes
  success; six attempts exhaust. Run tests before implementing provider calls.
- [ ] Implement google-genai calls using configured model/dimensions and separate
  text/image requests. Text is title plus public description with consistent format.
  Set SDK HTTP timeout in its documented units and validate normalization.
- [ ] Implement leased due-work selection using SELECT FOR UPDATE SKIP LOCKED;
  release DB transaction before HTTP. Record UUID lease tokens, 120-second expiry,
  input revision, six-attempt retry schedule and sanitized errors.
- [ ] Add concurrency tests with two independent sessions and synchronization Events:
  only one worker owns a row; edit while provider is blocked discards old result;
  expired lease can be reclaimed; old lease cannot overwrite new completion.
- [ ] Implement secret-protected POST /internal/tick. Check deadline before each job
  and external call; reduce timeout to remaining budget. Stop starting work once
  budget is exhausted. Initially process embeddings only; Task 6/8 add other stages.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_embeddings.py tests/test_tick.py -v`.
  No real provider calls belong in this test command.

### Task 6: Transactional Matching and Candidate API

**Files:** Extend matcher.py/tick.py; create routers/matches.py;
tests/test_matching.py; modify schemas.py/main.py.

**Consumes:** score_pair, Item revisions/state, session_factory.
**Produces:** `match_item(session_factory, item_id: UUID, settings: Settings) -> int`,
candidate list/detail and authorized candidate-image access.

- [ ] Write PostgreSQL tests for new lost/new found symmetry, same-owner exclusion,
  category/date filters, current model/revision requirement, text-only fallback,
  duplicate scans, score below threshold invalidation, and interrupted scan recovery.
- [ ] Add this privacy test after creating `matched_users` fixture with two owners
  and an unrelated third account:

```python
def test_unrelated_user_cannot_follow_candidate(client, matched_users):
    match, outsider_headers = matched_users
    response = client.get(f'/api/v1/matches/{match.id}', headers=outsider_headers)
    assert response.status_code == 404
    assert 'private_detail' not in response.text
```

- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_matching.py -v`, then
  implement SQL candidate filtering, CPU scores outside transaction, stable item
  locks, revision recheck and pair upsert. Skip stale results without clearing newer
  match_pending work. Concurrent scans must not duplicate pairs.
- [ ] Expose summary-only match schemas with evidence availability and claim
  eligibility. GET item/image may authorize current valid match participants without
  granting GET item access. Inaccessible/invalidated matches and images return 404.
- [ ] Add at most five matching items to tick. Mark scan complete only after all
  eligible candidates have been persisted in the bounded demonstration dataset.
  Document CPU scan limit; revisit vector indexing only if measured runtime exceeds
  the tick budget. Verify deadline can leave work pending safely.
- [ ] Rerun matching, item and tick tests together.

### Task 7: Milestone Frontend and Deployment Templates

**Files:** Create frontend files except admin page behavior; render.yaml,
frontend/vercel.json, docs/deployment.md, docs/demo.md, scripts/probe_services.py;
tests/test_probe.py. Create admin shell only when Task 10 starts.

**Consumes:** Tasks 1-6 APIs. **Produces:** usable home/auth/report/dashboard/match
pages, bilingual assets, safe deploy configuration and explicit service probe CLI.

- [ ] Implement api.js `request(path, {method, body})` returning parsed JSON, adding
  bearer token and leaving multipart Content-Type to the browser. Timeout errors
  never replay POST/PATCH. On 401 clear session and show login; on 404 candidate
  links show an unavailable message. Never append access tokens to URLs.
- [ ] Implement i18n.js loading en/bn JSON, localStorage language preference and
  document.lang. Use textContent for user text. Keep Bengali in locale files with
  UTF-8 encoding; UI text should explain similarity rather than imply ownership.
- [ ] Vendor Pico with license and create mobile-first styles. Provide visible input
  labels, focus styles, status aria-live region, image preview/clear, explicit AI
  consent, and pending/failed/no-match distinctions. Keep typed form data on errors.
- [ ] Connect real report/dashboard/match APIs. Poll every 15 seconds only while
  visible and pending; stop on navigation/visibility change. Do not poll by making
  internal tick publicly callable.
- [ ] Create Render template binding 0.0.0.0:$PORT with one Uvicorn worker; no keys in
  YAML. Create Vercel configuration for static root frontend, restrictive CSP,
  security headers and Cache-Control no-store for config. Document explicit Alembic
  migrations, frontend API origin and image-domain CSP configuration.
- [ ] Create probe_services CLI with separate explicit `--gemini`, `--storage`,
  `--email` options. Default only prints configuration presence; it does not contact
  providers or reveal values. Use synthetic text/image and a generated temporary
  storage path; clean up the probe object. Email requires `--recipient` explicitly.
  Test default issues no network calls and flags select only their named provider.
- [ ] Run probe tests locally. With separately authorized cloud access, verify model,
  quotas, database, bucket, sender and cron headers; record sanitized outcomes.
- [ ] Browser check at 360px and 1280px: two users submit reports, view score/image,
  language switch persists, validation is usable, XSS strings display as text,
  expiry logs out, and cold-start message preserves input. Record browser evidence.
  Do not mark milestone passed until deployed real embeddings and private-image
  access checks succeed. Local mocked demonstrations are development evidence only.

### Task 8: Brevo Notifications and Retry Delivery

**Files:** Create notify.py, tests/test_notify.py; extend tick.py, config.py,
schemas.py; add admin notification retry in Task 9.

**Consumes:** current valid Match and lost-owner locale/email.
**Produces:** `send_match_email(recipient: str, locale: str, dashboard_url: str,
notification_key: str, settings: Settings) -> None`, ten-email tick stage.

- [ ] Write HTTPX mocked tests for English/Bengali content, verified sender payload,
  429/5xx retry, 401 terminal failure, timeout, and exclusion of private data/images.
  Inspect outgoing request JSON; a successful test must not depend on real delivery.
- [ ] Implement Brevo transactional email with escaped template content and generic
  dashboard link. Verify current endpoint's idempotency support before using an
  idempotency header; otherwise document at-least-once delivery honestly.
- [ ] Add leases and current-validity checks before email delivery; persist sent state
  only for the lease owner. Never queue duplicate initial notices for sent pairs.
- [ ] Test invalidated pair cancels unsent work; revoked old lease cannot mark a new
  send complete; failure never removes dashboard match. Run
  `.\.venv\Scripts\python.exe -m pytest tests/test_notify.py tests/test_tick.py -v`.

### Task 9: Claims, Admin Review, and Transactional Handover

**Files:** Create routers/claims.py, routers/admin.py; tests/test_claims.py,
tests/test_admin.py; modify schemas.py/main.py.

**Consumes:** authentication, Item/Match/Claim, candidate validity.
**Produces:** claim create/list, admin item/claim listing, review/return/retry endpoints.

- [ ] Write permission tests: found owner cannot claim, unrelated user cannot claim,
  invalid pair cannot claim, duplicate/rejected claim cannot resubmit, ordinary user
  cannot view admin verification fields. GET /claims returns only claimant's answers.
- [ ] Write competing-approval test using two admin clients with independent DB
  sessions, a Barrier to release both, and claims sharing one found report. Assert
  statuses sorted are [200,409], one claim approved, the other rejected, and no
  second lost report reserved. Use a finite timeout so deadlocks fail the test.
- [ ] Acquire the shared lifecycle advisory lock, then lock the claim's two item
  rows in sorted UUID order. Re-read claim status, match validity and report states;
  reject conflicting approvals atomically. Every report edit/archive and claim
  submit/review/return uses this lock order. Add edit/claim race test proving pending
  verification details cannot be changed, plus crossed competing-claim graphs to
  verify no deadlock or second approval occurs.
- [ ] On approval reserve both reports, record review details, reject competitors,
  invalidate other candidates and cancel their unsent email. On rejection leave
  reports active. Reject second review with 409. Approved pair remains readable.
- [ ] Confirm return only for approved reserved pair, stamp returned_by/at and close
  both reports atomically. Repeated return yields the same successful outcome.
- [ ] Implement admin retry endpoints resetting only failed work, without erasing
  already completed embeddings or sending notices previously marked sent.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_claims.py tests/test_admin.py tests/test_items.py -v`.

### Task 10: Claim and Admin Browser Workflows

**Files:** Extend frontend/match.html, frontend/js/match.js;
create frontend/admin.html, frontend/js/admin.js; extend locales; docs/user-guide.md.

**Consumes:** Task 9 endpoints. **Produces:** accessible claim/review/handover UI.

- [ ] Render claim form only when API says eligible; show pending/approved/rejected
  outcomes and explain admin verification. Backend still enforces eligibility.
- [ ] Admin page loads paginated reports and pending claims with private details,
  answer, explicit approve/reject choices and a separate confirm-return action.
  Handle 409 by reloading current state and explaining the conflict, not retrying.
- [ ] Include failed-work status and retry controls for admins. No secrets or raw
  provider error bodies appear in browser notices. Translate all new text.
- [ ] Browser verification: ordinary users cannot operate admin APIs; second tab's
  stale approval gets conflict; edits freeze during pending claim; returned pair
  remains visible; expired signed image URL can be refreshed only while authorized;
  invalid candidate link displays unavailable without private text.
- [ ] Document user/admin steps and screenshot the two-user recovery flow without
  real personal information. Test on mobile and keyboard-only navigation.

### Task 11: Evaluation Dataset, Metrics, and Demo Fixtures

**Files:** Create scripts/evaluate.py, scripts/load_demo.py,
data/evaluation/pairs.jsonl, data/evaluation/README.md,
tests/test_evaluation.py, reports/evaluation.md.

**Consumes:** exact scoring functions from Task 4 and real embeddings from Task 5.
**Produces:** reproducible metrics/threshold table and non-sensitive demo fixture CLI.

- [ ] Define JSONL records with physical_item_id, report_id, type, category, public
  attributes, title, description, event_date, relative image path and split. Keep
  pair labels in same dataset records using match_group_id; no private verification
  text is sent for embedding. Collect 30 text pairs and 10 consented photo pairs;
  do not fabricate participant/photo collection evidence.
- [ ] Partition by physical_item_id before tuning. Generate same-category hard
  negatives without cross-split leakage. Cache vectors keyed by model, dimensions
  and SHA-256 of exact public input bytes; never use incompatible cached vectors.
- [ ] Write known-answer metric tests:

```python
def test_precision_at_three_counts_missing_slots():
    from scripts.evaluate import precision_at_k
    assert precision_at_k(['correct'], {'correct'}, 3) == 1 / 3
```

- [ ] Implement `precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float`,
  recall with explicit zero-positive handling, false-positive counts, threshold
  sweep on tune split, then one locked held-out run. Report empty-set conventions.
  Compare attribute-only, text+attribute and all-evidence configurations.
- [ ] Add CLI `--split tune|test`, `--threshold`, `--allow-api`; offline default fails
  clearly on missing cached vectors, rather than silently embedding through an API.
  Write measured reports only after actual execution and distinguish mock metrics.
- [ ] Demo loader refuses non-demo DB by default, requires explicit confirmation for
  deployment writes, and creates synthetic reports/accounts with runtime-supplied
  passwords; no committed admin credentials. Show deterministic demo steps in docs.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation.py -v`.
  Start dataset collection after Task 3 metadata is frozen, not at project end.

### Task 12: Release Verification and Submission Evidence

**Files:** Finish README.md, docs/{deployment,user-guide,demo,module-notes}.md,
reports/{evaluation,usability,testing}.md; add resolved dependency snapshot.

**Consumes:** all previous tasks. **Produces:** repeatable install, real test report,
live acceptance evidence, limitations, and team explanations.

- [ ] Run `.\.venv\Scripts\python.exe -m ruff check backend tests scripts` and
  `.\.venv\Scripts\python.exe -m pytest -v`. No required integration skips count
  as success. Record command, timestamp, database version, result and limitations.
- [ ] Verify clean-database Alembic upgrade and install from resolved dependencies.
  Check CI test database safety guards and migration behavior on a populated fixture.
- [ ] Finish deployment runbook: environment names, migrations before startup, seed
  once, private bucket/no anonymous DB access, CORS/CSP, cron secret header, verified
  sender, cold-start behavior, retry inspection, and sanitized log locations.
- [ ] Provide pg_dump/pg_restore commands for the findiu schema, plus managed backup
  alternative if those binaries remain unavailable. Verify restore on a disposable
  DB with row counts and image-path references; DB exports do not back up storage.
  Document separate private-bucket export and orphan-cleanup procedure.
- [ ] With authorized cloud access, execute final two-user flow using real providers:
  register, report/upload, match/email, claim, review, handover. Verify outsider
  access fails and provider outage preserves a saved report. Record evidence.
- [ ] Conduct 3-5 actual usability sessions, record anonymized tasks/results and fix
  blockers. No invented participants or screenshots. Produce user guide and slides
  content from observed behavior. Each team member writes their module explanation.
- [ ] Rehearse demo, export data before submission, and document free-tier, duplicate
  email, one-hour logout/revocation, small-dataset and identity-verification limits.
  Freeze features before final bug-fix pass. No automatic publish or commit.

## Acceptance Gates and Dependency Order

| Gate | Dependencies | Required evidence |
| --- | --- | --- |
| Backend foundation | Tasks 1-3 | Dedicated PostgreSQL tests, auth/privacy, safe private upload |
| Real matching slice | Tasks 4-6 | Current vectors, idempotent pairs, stale-worker recovery |
| Milestone 1 | Task 7 plus authorized deployment | Live two-user report-to-match flow and bilingual UI |
| Recovery workflow | Tasks 8-10 | Real email, claim review, conflict prevention, handover |
| Submission | Tasks 11-12 | Held-out evaluation, full test run, usability and rehearsal |

Local implementation can proceed while cloud access is unavailable. In that case,
mark deployment/provider gates blocked and state exactly which checks are unrun;
do not leave independent local tasks unfinished while waiting for credentials.

## Self-Review Coverage

Spec sections 1-2: Tasks 1/7/12; section 3: Tasks 2/3/6/9/10; section 4: Task 2;
section 5: Task 3; section 6: Tasks 3/9/10; section 7: Tasks 4/5/6/11; section 8:
Tasks 5/6/8; section 9: Tasks 1/2/3/6/9; section 10: Tasks 7/10; section 11:
Tasks 1-12 checks; section 12: staged gates/team ownership; sections 13-14: Tasks
1/7/12 and explicit live verification gates. Shared function signatures and enum
names are defined above. No task authorizes commits or external publication.

## Execution Handoff

Recommended method: native implementation in the current session, completing one
task and its checks before the next, with a final independent review. The tasks
share schema and lifecycle contracts heavily; avoiding repeated fresh contexts is
the simpler approach for this small academic project. Cloud access and PostgreSQL
test availability are operational prerequisites, not reasons to fake passing gates.

Review this concrete plan and choose native or subagent-driven execution before
product implementation. Subagent-driven execution uses a fresh implementer and
reviewer per task; it costs more context and coordination but adds earlier review.
