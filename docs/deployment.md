# Deployment Runbook

No cloud deployment or live provider verification is recorded yet. The local
matcher runs on the API server, including a hosted server. Keep PostgreSQL in the private, non-exposed `findiu` schema,
and use a private Supabase Storage bucket with service credentials only on the API.

Set environment variables from `.env.example`. Production must explicitly use
`STORAGE_PROVIDER=supabase`. Start with `MATCHING_MODE=local`; Gemini is optional.
Set a random JWT key
and independent random internal tick key; use HTTPS frontend/API URLs and an
exact CORS origin list. Never deploy the development `.env` or local uploads.

To enable hosted semantic evidence, set `MATCHING_MODE=hybrid`,
`EMBEDDING_PROVIDER=gemini` and a key. No key/failure keeps comparisons local.
Owners must separately consent through the current report form; historical
reports default to no external-processing permission. Administrators cannot
grant that permission for another owner. Local comparisons remain available
while optional semantic work is pending or fails.

Run `python -m alembic -c backend/alembic.ini upgrade head` before starting
`uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port $PORT`.
Provision the admin account explicitly. Publish `frontend/` after editing its
public API base URL. A frontend host must allow the Google Fonts CSS/font origins
or self-host those fonts. Current inline page bootstraps require CSP hashes before
a strict `script-src 'self'` policy can be enabled; do not claim strict CSP is
already configured by the local Python static server.

Before changing deployment data, take the backup described below. Preview
`python -m scripts.backfill_local_features --allow-remote`, then authorize bounded
batches with `--apply --allow-remote --limit 100` if appropriate. Repeat until the
preview has no pending rows. This reads images for local feature extraction; it
does not call Gemini, erase reports, grant consent or delete claimed matches.
Claimed scores/evidence remain historical snapshots. Derived columns and evidence
are lost on migration downgrade; restore a backup for a data-preserving rollback.

Create one ten-minute cron POST to `/internal/tick` with an Authorization bearer
header. Do not put secrets in query strings. Configure a verified Brevo sender.
Confirm health, readiness, private signed
URL access, one delivered email, scheduled processing, outsider denial and the
complete two-user return flow. Record provider/model/quota and latency; generic
health checks do not guarantee free-tier uptime.
Verify genuine text/image Gemini calls, external-consent enforcement and provider
failure fallback separately if hybrid mode is enabled. Synthetic metrics cannot
stand in for live provider quality or real-photo accuracy.

## Backup And Recovery

Before changing deployment data, export the application schema with PostgreSQL
tools using environment-based connection secrets:

```powershell
pg_dump --format=custom --schema=findiu --file=findiu-backup.dump $env:DATABASE_URL
pg_restore --dbname=$env:RESTORE_DATABASE_URL --no-owner findiu-backup.dump
```

Restore only into a disposable or approved recovery database. Compare users,
items, matches and claims row counts and image references before switching traffic.
The database export does not contain Storage objects: export the private bucket
separately with access controls. Orphan cleanup must compare object paths against
every database image reference and retain referenced files. A provider outage
must preserve saved reports and sanitized failed-work state.

Free hosting may sleep or pause. Throttles reset on restart, signed images remain
bearer capabilities until expiry, and email delivery may duplicate after ambiguous
timeouts. These are documented demonstration limits, not uptime guarantees.
