# Local Test Evidence

The final completed full test run used Python 3.10.5, pytest 9.2.0, and a dedicated
PostgreSQL 17.4 `findiu_test` database on loopback port 55432. It returned
`98 passed, 2 warnings in 29.56s`. Required integration tests ran; they were not
replaced with SQLite or counted as skipped success. The warnings are an upstream
Starlette/AnyIO deprecation and the deliberately rejected SHA384 JWT test key.

Commands:

```powershell
$env:TEST_DATABASE_URL="postgresql://findiu_dev@127.0.0.1:55432/findiu_test"
python -m pytest -v
python -m ruff check backend tests scripts
python -m ruff format --check backend tests scripts
```

Ruff and JavaScript syntax checks passed. Tests include authorization/privacy,
image decoding/size limits, candidate eligibility, lease/revision fencing,
concurrent competing approvals, current-match visibility, retries, atomic pair
handover, provider error handling, evaluation consent/split leakage, cache safety
and known-answer metrics. Synthetic vectors verify calculations only.

Firefox screenshots at 1440x900 and 390x844 were inspected. Browser checks covered
language switching, sign-in, report creation/edit/archive, candidate evidence,
claim submission, admin approval and physical handover; the latest bilingual
dashboard/report/admin run had no JavaScript page errors or horizontal overflow.
Native browser date/file controls follow the installed browser's own locale.

The GitHub Actions template and Render blueprint are local, unpublished files;
they have not been run in those services. Real provider delivery, held-out accuracy,
human usability and cloud uptime remain unverified. See evaluation/usability
reports and the deployment runbook for the actual remaining evidence gates.
