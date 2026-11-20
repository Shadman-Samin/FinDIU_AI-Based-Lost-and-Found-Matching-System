# Demo Rehearsal

Use only synthetic reports and images. Local mode uses an explicitly selected
lexical/colour fingerprint provider; explain this before presenting any score.
It is not Gemini evaluation evidence.

1. Open the home page, show Bangla/English and the ownership warning.
2. Sign in as the lost-report owner, open a report and its candidate.
3. Explain category/date/owner eligibility and the 45/25/30 weighted evidence
   components (60/40 without two image vectors).
4. Submit a claim with the synthetic hidden evidence.
5. In a second browser session, sign in as the review desk and inspect both private
   fields. Show that an ordinary student receives 403 for admin operations.
6. Approve, then confirm physical handover separately. Show both report statuses.
7. Show the PostgreSQL tests, sanitized failure/retry state and the evaluation
   harness. State which live provider and human evaluation gates remain pending.

Avoid repeatedly running `scripts.seed_demo`; the legacy seed script creates
additional records on repeated runs. Existing test/demo artifacts are synthetic.
Do not run loaders against deployment without explicit approval and a backup.
