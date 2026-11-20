# FinDIU Design Specification

Date: 2026-11-16
Status: Written specification approved in conversation; implementation planning authorized.

## 1. Purpose and Constraints

FinDIU helps people report lost and found belongings, discover likely matches, and
request an admin-reviewed return. Similarity identifies candidates, never ownership.
The agreed target is an academic demonstration with sound security and reliability
boundaries, a small dataset, and code that each team member can explain.

Preserve all features in the original Bengali plan: text and image matching,
Bengali/English UI, private images, dashboards, email, claims, admin review,
retries, evaluation, usability testing, and documentation.

Milestone 1 is November 19, 2026; feature freeze is November 25; submission is
November 28. These are delivery targets, not claims that deployment is complete.
Runtime must use free cloud services without depending on a local computer.
Development and automated tests may run locally. Free hosting is best effort.

Assumptions: small campus demonstration, ordinary user registration, one image
per report, and admin-mediated handover. Registration does not verify university
affiliation. Users are warned not to submit identity documents or sensitive photos.
Public-facing descriptions must omit verification secrets and contact details.

## 2. Architecture and Alternatives

Selected: static HTML/CSS/JavaScript and vendored Pico.css on Vercel; one Python
FastAPI service on Render; SQLAlchemy and Alembic against Supabase PostgreSQL;
private Supabase Storage; Gemini embeddings; Brevo HTTP email; cron-job.org ticks.

This preserves the team plan and keeps each module explainable. A React frontend
would introduce tooling without a demonstrated need. A separate queue, worker,
and vector database would increase deployment complexity for the small dataset.
Use database work state and Python similarity calculations instead.

The frontend only calls the backend. Database credentials, storage service keys,
Gemini keys, and Brevo keys stay on the backend. Database tables must not be
accessible through Supabase's anonymous Data API: keep them outside exposed
schemas or enable RLS with no anonymous/authenticated client policies.

Use ordinary modules rather than a generic provider framework. Separate routers,
schemas, database models, authentication, image processing, storage, embeddings,
attributes, matching, and notifications by responsibility.

## 3. Authentication and Access

- Hash passwords with Argon2. Normalize email by trimming and lowercasing; enforce
  uniqueness in PostgreSQL. Never log passwords or tokens.
- Registration always creates a user role. Admin creation is an explicit CLI seed
  using deployment environment variables, not a public endpoint or startup reset.
- Signed JWTs expire after one hour. Validate a fixed algorithm, issuer, audience,
  subject, and expiry; load current role from the database on protected requests.
- Store browser tokens in sessionStorage; clear on logout or expiry. No refresh
  tokens in this version. Logout does not revoke an already issued token.
- Allow only configured frontend origins in CORS. Use HTTPS, a restrictive CSP,
  safe DOM text rendering, and no third-party executable scripts.
- Bound request sizes and apply per-IP throttling to registration/login plus
  per-user throttling to report creation and claims. Single-instance in-memory
  throttles reset on restart and are a documented demonstration limitation.
- Load the requested record before deciding access. Return a uniform 404 for
  inaccessible object IDs; return 401 for invalid authentication and 403 for an
  authenticated user attempting an admin endpoint.
- List endpoints are paginated, default 20 and maximum 100 records.

Access matrix:

| Resource | Report owner | Matched lost-report owner | Unrelated user | Admin |
| --- | --- | --- | --- | --- |
| Own report and private detail | Yes | Only if owner | No | Yes |
| Candidate summary and scores | If match participant | Yes | No | Yes |
| Candidate image | If match participant | Yes | No | Yes |
| Other report's private detail | No | No | No | Yes |
| Claim answer | Only if claimant | Only if claimant | No | Yes |
| Review claims / confirm return | No | No | No | Yes |

There is no public browse-all-items endpoint. A candidate summary excludes owner
contact data, private details, raw image paths, embeddings, and claim answers.
Owners can view their own reports; admin access is explicit, not accidental reuse
of an unrestricted serializer.

## 4. Data Model

Use UUID primary keys, foreign keys, UTC timezone-aware timestamps, and named
database constraints. Event dates are date-only values interpreted in Asia/Dhaka.
All tables have created_at; mutable tables have updated_at.

| Table | Fields beyond shared identity/timestamps |
| --- | --- |
| users | name, normalized email (unique), password_hash, role: user/admin, locale: en/bn |
| items | type: lost/found, user_id, category, color, brand, title, description, location, event_date, private_detail, image_path (nullable), status, content_revision, text_embedding (JSONB nullable), image_embedding (JSONB nullable), embedding_model, embedding_dimensions, embedded_revision, embed_status, embed_attempts, embed_next_attempt_at, embed_lease_until, embed_last_error_code, match_pending, consent_version, consented_at |
| matches | lost_id, found_id, lost_revision, found_revision, text_sim, image_sim (nullable), attr_score, score, scoring_version, valid, notify_status, notify_attempts, notify_next_attempt_at, notify_lease_until, notify_last_error_code, notification_key, notified_at |
| claims | match_id, claimant_id, answer, status: pending/approved/rejected, reviewed_by (nullable), reviewed_at (nullable), review_note (nullable), returned_by (nullable), returned_at (nullable) |

Use unique constraints on matches(lost_id, found_id) and
claims(match_id, claimant_id). Check enums and score ranges in database constraints.
Embeddings must be finite, nonzero, and exactly the configured dimension.
Index item eligibility filters, user ownership, due-work timestamps, and pending
claims. Ownership/type relationships across tables are checked transactionally.
No hard deletion API is required; users can archive eligible reports.

Retain the four-table structure. Work tracking lives beside the work it describes.
Last error codes are sanitized categories, never provider response bodies.

## 5. Input and Storage Contract

- Use fixed category, color, and campus-area IDs with bilingual labels. Keep
  unknown/other options. Brand is optional normalized text.
- Bound names and report titles to 120 characters, descriptions to 2,000,
  private details and claim answers to 1,000. Passwords are 12-128 characters.
- Reject future event dates in Asia/Dhaka. Type and owner cannot change on edit.
- Accept at most one JPEG or PNG image, up to 5 MiB and 20 megapixels. Decode with
  Pillow, reject malformed/animated inputs and decompression bombs, apply EXIF
  orientation, resize longest edge to 1,024 pixels, and re-encode as RGB JPEG
  without metadata. Browser previews are convenience checks only.
- Generate UUID storage names. Store paths, never signed URLs, in PostgreSQL.
  Signed URLs expire after five minutes and are generated only after authorization.
  These URLs are bearer capabilities until expiration, not revocable sessions.
- Require explicit consent to external AI processing of supplied public text and
  image. private_detail and claim answers are never embedding inputs.
- Upload the processed image before committing its report. On DB failure, attempt
  compensating storage deletion. A crash may leave an orphan; document an admin
  cleanup procedure. On image replacement, commit the new reference before
  deleting the old object. Retain the old image if replacement fails.

## 6. Report and Claim Lifecycle

Reports use active, reserved, returned, archived. A match does not change active
status. Owners can edit/archive active reports unless involved in a pending claim.
Reserved/returned reports cannot be edited. Archival is terminal in this version.

Only the owner of a match's lost report can submit a claim. Both reports must be
active, owned by different users, and linked by a currently valid match. Store
the verification answer without revealing the found report's private detail.
The same claimant cannot repeatedly submit the same claim after rejection.

For claim submission, edits, approval, rejection, and handover, lock the involved
item rows in stable ID order before rechecking conditions. This serializes
conflicting operations, including a concurrent edit and claim submission.

Admin approval locks both reports, approves the pending claim, reserves both
reports, rejects competing pending claims involving either report, and invalidates
other candidates involving those reports in one transaction. Admin rejection
records reviewer, time, and note without closing either report. Already reviewed
claims cannot be reviewed again. No automatic approval from similarity scores.

Admin confirms physical handover on an approved claim: both reserved reports
become returned and the claim records who confirmed and when. Repeated confirmation
returns the existing outcome. Reversing an approval is outside this version's UI;
admins must confirm evidence before approval.

## 7. Embeddings, Matching, and Invalidation

Model: gemini-embedding-2, requested output dimensionality 768. Generate separate
text and image embeddings to retain score explanations. Use the same text format
for lost/found descriptions. Do not pass the older model's task_type parameter.
Validate returned vectors and normalize defensively before storage.

Embedding state is pending, processing, ready, or failed. Persist the report first;
request failure must not lose it. Preserve successful text work if image processing
fails. Text-only candidates may be generated while the image retry remains pending;
the UI indicates reduced evidence. Never invent image scores or fake AI results.

Compare active reports of opposite type and different owners, same category, with
0 <= found.event_date - lost.event_date <= configured window (initially 30 days).
The window is a demonstration assumption to validate against labeled examples.
Fetch eligible candidates from SQL and calculate cosine similarity in Python.
Compare only vectors with the same model, dimension, and current input revision.

Clamp negative cosine similarity to zero for the weighted score and preserve raw
cosine values for explanations. Initial weights: text/image/attributes =
0.45/0.25/0.30 with both image vectors; otherwise text/attributes = 0.60/0.40.
Attribute weights are color/brand/location/date = 0.40/0.30/0.20/0.10. Known
equal normalized values score 1; differing values score 0; missing/unknown values
score 0 and do not count as agreements. Date score is max(0, 1 - day_gap/30).
Store per-component scores. A displayed percentage is similarity, not probability
of ownership. Start with threshold 0.75, label it provisional, then tune on data.

Upsert each pair and mark match_pending false only in the transaction completing
the scan. Retry after a crash is safe. Recheck item revisions/status under locks
before persisting results computed outside the transaction.

Edits increment content_revision and invalidate all affected candidates in the
same transaction. For simplicity, all matching-field edits regenerate embeddings;
private-detail-only edits do not. Images and public text remain bound to consent.
New work sets match_pending. Ready embeddings are retained for unedited inputs.
Candidates below threshold become invalid. Invalid candidates cannot be viewed
or claimed; pending notification is cancelled. A previously sent notification is
not resent when an existing pair is recalculated.

## 8. Durable Processing and Email

POST /internal/tick requires a separate secret in an Authorization bearer header,
constant-time comparison, and no token in URL/query logs. No browser access needed.
Process at most five due embedding items, five matching items, and ten emails per
tick within a 45-second budget. Bound each external request to ten seconds.
Use database row locks with SKIP LOCKED and two-minute leases for external work;
expired leases are reclaimable. Do not hold DB transactions during network calls.

Persist revision/lease ownership when claiming work and check it again on write.
Use retries at approximately 1, 5, 15, 60, and 240 minutes, honoring Retry-After
when supplied and adding bounded jitter. After six attempts, mark failed for admin
inspection and explicit retry. Authentication/configuration failures stop automatic
retries; timeouts, quota limits, and provider 5xx errors remain retryable.

Email the lost-report owner only, in their preferred language, with a dashboard
link and generic candidate notice. Exclude private details, claim answers, images,
and owner contact data. Persist a stable notification key. Use provider idempotency
if its endpoint supports it; otherwise delivery is at least once and rare duplicate
emails after an ambiguous timeout/crash are an acknowledged limitation. Recheck
match validity before sending. Dashboard visibility never depends on email success.

One cron every ten minutes calls tick. A separate cheap health check may reduce
cold starts but is not an uptime guarantee. GET /health checks service liveness;
GET /ready performs a bounded SELECT 1 and returns 503 if DB is unavailable.
Do not claim that health traffic guarantees Supabase will never pause.

## 9. API Contract

Prefix application endpoints with /api/v1. Use JSON except multipart report writes.
Use FastAPI OpenAPI as the canonical executable contract. List responses contain
items, limit, offset, total. Errors expose code and message plus field details for
validation; they never expose SQL, stack traces, or upstream credential errors.

| Method and path | Behavior |
| --- | --- |
| POST /auth/register | Create ordinary user; 201 |
| POST /auth/login | Return bearer access token and expiry; 200 |
| GET /auth/me | Current user profile and role |
| GET /metadata | Category/color/location IDs and bilingual labels |
| POST /items | Multipart report fields and optional image; 201, pending state |
| GET /items | Current user's reports only, paginated |
| GET /items/{id} | Owner/admin report details |
| PATCH /items/{id} | Multipart partial update; expected_revision required |
| POST /items/{id}/archive | Owner/admin active report archival |
| GET /items/{id}/image | Authorized short-lived URL, Cache-Control: no-store |
| GET /matches | Current user's valid matches, paginated |
| GET /matches/{id} | Authorized summaries, component scores, claim eligibility |
| POST /claims | match_id and answer; claimant derived from authentication; 201 |
| GET /claims | Current user's claims, paginated |
| GET /admin/items | All reports, paginated and filtered |
| GET /admin/claims | Claims with admin-only verification fields |
| POST /admin/claims/{id}/review | approve/reject plus review_note |
| POST /admin/claims/{id}/return | Confirm handover |
| POST /admin/items/{id}/retry | Reset exhausted embedding work |
| POST /admin/matches/{id}/retry | Reset failed notification work |

Health, readiness, and internal tick are unprefixed operational routes. Reject
stale edits and conflicting lifecycle operations with 409. Return 413 for oversized
uploads, 422 for invalid fields, and 429 for throttling. Do not automatically retry
non-idempotent browser writes; fetch the report list after an ambiguous submission.

## 10. Frontend

Six pages: home, login/register, report form, dashboard, match detail/claim form,
admin. Share one API module, translation module, and stylesheet. Backend URL is
public configuration; no secrets in frontend configuration. Vendor Pico.css and
retain its license. No frontend framework or build step is required initially.

Support English/Bengali labels and validation messages; persist locale locally.
Set document language, preserve keyboard focus and visible labels, announce status
changes accessibly, and check mobile layout at 360px and desktop at 1280px.
Forms preserve entered fields on API error. Disable duplicate submits while a
request is in flight. Display processing/failed/no-match states distinctly.
Show a server-waking message for slow requests without automatically resubmitting
reports. Poll only while the dashboard is visible and pending work exists.

## 11. Verification and Acceptance

Use pytest for scoring, normalization, image safety, JWT validation, and service
failure behavior with mocked external APIs. Use real PostgreSQL integration tests
for constraints, leases, locks, stale edits, claim conflicts, and transaction rollback;
SQLite cannot verify these behaviors. Never run tests against a deployment database.

Security checks use two ordinary users and one admin: no private detail leakage,
no arbitrary image access, no claim on someone else's lost report, no role escalation,
and no ordinary access to admin routes. Verify safe rendering of user-supplied HTML.
Test report persistence during Gemini failure, image-only embedding failure, process
interruption/retry, duplicate cron calls, and notification failure.

Evaluate 30 bilingual positive text pairs, hard negatives in the same category,
and 10 physical-item photo pairs. Partition by physical item before tuning. Report
precision@1, precision@3, recall at threshold, and false-positive counts; compare
attribute-only, text+attribute, and text+image+attribute configurations. Record small
sample limitations and model/scoring versions. Never tune on the held-out set.

Milestone 1 acceptance: deployed frontend/API/DB, registration/login, two users
submitting lost/found reports with private images, persisted real embeddings,
scheduled matching, visible candidate with score breakdown, dashboard, language
toggle, and evidence that an unrelated user cannot read private content. A mocked
embedding test does not count as live AI evidence.

Final acceptance adds delivered email, retries, claim creation, admin approval,
competing-claim prevention, confirmed return, evaluation results, 3-5 usability
participants, deployment instructions, screenshots, test evidence, and rehearsal.

## 12. Delivery and Team Boundaries

| Target | Outcome |
| --- | --- |
| Nov 16 | Freeze schema/API; service connectivity and real text/image embedding probe |
| Nov 17 | Auth, reports, private upload, durable processing, first matching slice |
| Nov 18 | Dashboard, editing, translations, access tests, demo rehearsal |
| Nov 19 | Milestone 1 acceptance demonstration |
| Nov 20-23 | Email, claims, admin review and handover |
| Nov 24-25 | Evaluation, usability, reliability checks, feature freeze |
| Nov 26-28 | Bug fixes, documentation, rehearsal and submission |

Shadman owns foundation, auth/storage, embeddings/matching, tick, integration,
evaluation script, and deployments. Nusrat owns frontend, translations, Brevo,
claim routes, usability, and user documentation. Jannatul owns attributes, image
validation, item/admin routes, privacy serialization, and integration test evidence.
Nusrat and Jannatul create the dataset in parallel once input fields are frozen.
Shared contracts and migrations are reviewed before parallel changes merge.

Use short-lived branches and reviewed merges once Git is initialized; no keys in
source control. Each owner supplies tests and a one-page explanation. Git commits,
remote publication, and external account setup require explicit user instruction.

## 13. Configuration and Deployment Gates

Backend environment: DATABASE_URL, JWT_SECRET, JWT_ISSUER, JWT_AUDIENCE,
ALLOWED_ORIGINS, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, STORAGE_BUCKET,
GEMINI_API_KEY, GEMINI_EMBEDDING_MODEL, BREVO_API_KEY, BREVO_SENDER_EMAIL,
FRONTEND_URL, INTERNAL_TICK_TOKEN. Admin seed uses ADMIN_EMAIL, ADMIN_NAME,
ADMIN_PASSWORD only when explicitly invoked. Commit placeholder .env.example only.

Keep score weights, threshold, dimensions, time window, and resource limits in
validated backend configuration. Fail startup for missing core DB/auth settings.
Missing provider configuration is visible as a sanitized operational failure;
never silently substitute fake AI or successful email results.

First live checks require authorized access to the team's cloud accounts:
confirm model access and actual quotas in AI Studio; send one text and one image
request; verify Supabase TLS database connection/pooler compatibility and private
bucket; verify Brevo sender and deliver a test email; verify Render and Vercel
deployment settings and cron header support. No account creation, key access,
paid plan, or deployment has been performed as part of this specification.

Use a small DB connection pool suitable for Supabase. Run Alembic migrations as an
explicit deployment step before starting the application; do not depend on Render
free one-off jobs. Provide a clean-database installation command, environment guide,
admin seed command, database export/restore instructions, and demo fixture loader.
Keep an export before the final demonstration; free-tier backups are not assumed.

## 14. Verified References and Remaining Limits

Documentation inspected November 16, 2026:

- https://ai.google.dev/gemini-api/docs/embeddings : stable model ID,
  image/text support, 768 dimensions, incompatible embedding spaces across models.
- https://ai.google.dev/gemini-api/docs/pricing : standard free text/image input
  and free-tier content use for product improvement.
- https://render.com/docs/free : idle sleep, ephemeral filesystem, blocked SMTP,
  750 workspace free-instance hours, and possible suspension on excess usage.

Account-specific Gemini quotas, Supabase pause behavior/limits, Brevo delivery and
idempotency support, and original proposal acceptance requirements remain live
verification gates. The original plan's fixed quota and keep-alive guarantees are
not accepted as verified facts. Academic scope means no institutional identity
verification, password reset, full audit event history, uptime SLA, or independently
scaled workers in this release. These limits must be stated in the final report.
