# Synthetic development corpus

This is **not real campus data and not evidence of production accuracy**.
It contains 66 synthetic reports: 24 lost/found physical-item pairs, 16 separate
look-alike found reports, and two lost reports with no labelled counterpart.
English, Bengali, typos, missing photos/brands, and varied public clues are included.

- `tune`: 16 pairs, 12 look-alikes, two unmatched queries (46 reports).
- `test`: eight different physical-item pairs and four look-alikes (20 reports).
- Physical-item and match-group labels never cross splits.
- One held-out look-alike has public evidence indistinguishable from another
  student-card sleeve. No algorithm can infer secret identity from those clues;
  administrator verification is intentionally still necessary.
- JPEGs are drawings with viewpoint/brightness/compression variation, not real
  photos. They contain no names, IDs or claim answers. Labels and filenames are
  never passed into matching features.
- Consent flags are synthetic fixture eligibility declarations, not claims that
  real participants consented. Real reports require separate consent and review.
- External AI permission is absent by default. `--allow-api` additionally requires
  explicit `consent_for_external_ai: true` on every record; local consent alone
  cannot authorize a hosted provider call.
- `manifest.json` records JSONL and original-image SHA-256 hashes. Evaluation
  additionally hashes normalized image content.

Regenerate only this owned synthetic corpus:

```powershell
.\.venv\Scripts\python.exe -m scripts.build_dev_corpus
.\.venv\Scripts\python.exe -m scripts.evaluate data/evaluation/synthetic-v1/reports.jsonl --engine local --split tune --output reports/synthetic-v1-tune.json
```

Select the threshold using `tune` only. Pass that fixed value with `--threshold`
when evaluating `test`; never retune from the held-out result. The generator
refuses to overwrite non-synthetic/foreign report files.

The local run compares attributes, lexical features, image hashes, local fusion,
synonym/location/colour ablations, BM25 ranking, and a hashed-vector baseline.
The latter is **not Gemini or a semantic neural model**. Hosted semantic and
hybrid metrics remain unavailable until genuine, model-versioned vectors exist.

Keep later consented real reports in a different dataset directory, with physical
items grouped before splitting. Never merge this corpus into reported real-world
test results. Synthetic held-out results still share this generator and vocabulary;
their apparent generalization does not establish real-photo or native-language quality.
