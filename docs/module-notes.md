# Module Explanation Notes

These are code walkthrough prompts, not claims that each student wrote a module
or completed an oral rehearsal.

| Area | Files | Explain In The Viva |
| --- | --- | --- |
| Authentication | `backend/app/auth.py`, `routers/auth.py`, `dependencies.py` | Argon2 versus encryption; fixed JWT algorithm/issuer/audience; why role comes from the DB; session expiry |
| Privacy and uploads | `image_utils.py`, `storage.py`, `routers/items.py` | Decode/re-encode, metadata removal, private object paths, authorized five-minute URLs and compensating deletion |
| Local text | `text_features.py` | Unicode/Bengali normalization, curated synonyms, weighted Jaccard, character-trigram Dice, containment and Jaro-Winkler; why this is not general translation |
| Local images | `image_features.py` | 64-bit dHash/aHash, 48-bin HSV intersection, uniform-hash rejection, central crop and background/lighting limits |
| Matching | `attributes.py`, `matcher.py`, `processing.py` | Hard eligibility versus optional embeddings; finite/current/model-compatible cosine; local-first fusion, missing signal weights, saved threshold/evidence and no ownership probability |
| External consent | `routers/items.py`, `processing.py`, migrations | Report-scoped permission, owner-only grant, local-only defaults and rechecking authorization before image requests |
| Durable work | `processing.py`, `routers/internal.py` | Database leases, SKIP LOCKED, input revisions, stale-worker fencing, retry delays and secret cron calls |
| Claims | `lifecycle.py`, `routers/matches.py` | Stable item locks, competing claim rejection, reserve versus returned, and idempotent handover |
| Frontend | `frontend/js/` | Safe text rendering, sessionStorage, bilingual controlled labels, owner-only dashboard, loading/error states |
| Evaluation | `scripts/build_dev_corpus.py`, `scripts/evaluate.py` | Physical-item split isolation, synthetic versus real evidence, API consent/cache identity, precision-constrained tune thresholds, query bootstrap intervals, ablations and rank-only BM25 |

Each teammate should trace one real request from UI to database and back, identify
a failure case, show its test and explain a limitation. Use the approved spec for
architecture reasoning and `docs/matching-algorithms.md` for the implemented
formulas. Never describe the hashed evaluation baseline as Gemini or present
synthetic drawings, perfect tune scores, or tiny bootstrap intervals as real-world
accuracy evidence. Image/location ablations show no gain on this small corpus;
do not invent one. Claim evidence is frozen rather than rewritten by re-scoring.
