# Local-first matching engine

The API compares public clues locally. Optional Gemini embeddings add semantic
evidence; they are not a prerequisite and a similarity score is never proof of
ownership. Everything runs with the existing stdlib/Pillow dependencies.

## Eligibility Before Ranking

Only active lost/found reports from different owners in the same category are
compared. Found dates must fall on/after the lost date within the configured
30-day window. No lexical prefilter truncates recall at the current small campus
scale. Embedding model/readiness is not an eligibility rule.

## Text

`backend/app/text_features.py` performs NFKC/case normalization, preserves Bengali
vowel marks, converts decimal digits, removes punctuation/report boilerplate,
and applies a small English/Bengali/loanword lexicon. Negation is not a stopword.
This is not general translation, transliteration or learned language understanding.

Only title and description enter lexical evidence; title tokens count twice.
Brand/location/colour fields are scored separately. Labels, owner IDs, private
details and claim answers are never passed into text/image features.

- Weighted token Jaccard: sum of minimum token counts / sum of maximum counts.
- Character-trigram Dice: twice the shared padded word-trigram count / total count.
- Containment: shared weighted tokens / shorter weighted token count.
- Local text score: 0.45 Jaccard + 0.35 Dice + 0.20 containment.
- Empty/boilerplate-only descriptions have zero lexical agreement.
- Shared public terms are capped at eight, stable-ordered and rendered as text.

Jaro-Winkler handles short brand typos: exact normalized brands score 1.0;
similarity at least 0.90 earns 0.85; token containment earns 0.70. Unknown/missing
values never count as agreements. This heuristic needs real-brand false-positive
evaluation and is not a trained entity resolver.

## Images

`backend/app/image_features.py` extracts features from validated/re-encoded JPEGs
on upload/edit, not by downloading each candidate image during ranking.

- dHash: 64 adjacent grayscale intensity comparisons from a 9x8 resize.
- aHash: 64 mean-intensity comparisons from an 8x8 resize.
- Hash similarity: 1 - Hamming distance / 64.
- HSV histogram: 12 hue x two saturation x two value bins (48 bins), normalized;
  intersection sums the minimum bin mass. Value bins distinguish black/white.
- The central 80% crop limits background bias, but does not segment objects.
- Local image score: 0.45 dHash + 0.20 aHash + 0.35 histogram intersection.
- Near-uniform hashes (at most two or at least 62 set bits) are not structural
  evidence. Their weights are removed and usable weights renormalized. If both
  hashes are degenerate, the histogram is also discarded: two blank/solid photos
  would only duplicate the colour attribute, so no image evidence is claimed.

These are cheap perceptual comparisons, not object recognition. Crop, rotation,
backgrounds, lighting and same-model look-alikes can mislead them. Hash-only
synthetic results already show false positives; text/attributes and human proof
must remain independent. pHash/OpenCV/OCR/local neural models are deferred.

## Structured Clues And Fusion

`attributes.py` uses 0.40 colour / 0.30 brand / 0.20 location / 0.10 date.
Exact colours and bilingual aliases agree; close shade aliases such as navy/blue
earn 0.85. There is no blanket warm/cool/neutral agreement between unrelated colours.
Exact known campus areas score 1.0; library/classroom receive conservative 0.5
academic-zone credit. That unvalidated zone heuristic is not measured proximity.
Date score is `max(0, 1 - absolute_gap / window)`. Missing fields are not renormalized
into false agreements; no evidence is invented for an absent brand or colour.

With paired usable image evidence, outer weights are 0.45 text / 0.25 image /
0.30 attributes. Without it, they are 0.60 text / 0.40 attributes.
The provisional threshold is 0.75, retained by synthetic development calibration.

`MATCHING_MODE=hybrid` blends each available semantic signal as 0.65 local + 0.35
nonnegative semantic cosine. Missing semantic vectors keep the full local signal;
missing local image evidence can use a valid semantic image signal. Models,
dimensions, finite/nonzero values and current input revisions must be compatible.
The hashed-vector evaluation baseline is never treated as semantic evidence.
Degenerate legacy fingerprints (for example an all-black colour grid) are
reported as missing baseline vectors, not fatal local-evaluation errors.

## Consent And Durable Work

`semantic_consent` defaults false and must be explicitly supplied by the owner.
The form shows the actual configured scope and sends it separately from general
matching consent. No global key/mode switch opts in existing reports. Admins
cannot grant another owner's permission. Public edits require renewed consent;
scope changes invalidate vectors/work by content revision.

Local matching commits before optional provider work can consume the tick budget.
External requests require report-scoped permission; authorization/revision/lease
is rechecked before **both** text and image transmission and before writes. An
in-flight request already started under consent cannot be recalled, but subsequent
calls stop as soon as revocation is observed. Only the owner may change the flag;
an administrator's unrelated edit preserves it. Consented reports remain queued
when external AI is not yet configured, so later enabling hybrid mode honours the
owner's recorded choice. Provider failures/retries do not block local comparisons.

## Persistence And Upgrades

`items.image_features` is one nullable JSONB feature document with `feature_version`.
Matches store their scoring version, component scores and evidence including the
decision threshold and actual weights. The UI reads these snapshots, not today's
configuration. Historical rows without recorded thresholds display "Not recorded".
The unreleased component-constraint migration allows 1e-9 floating-point rounding
tolerance for historical dot products; current cosine results are still clamped
to [-1, 1]. Saved scores/components and claim IDs are not rewritten to pass migration.

Re-scoring upserts existing pair IDs and retains notification deduplication. Any
match with a claim keeps its saved score/evidence so a background upgrade cannot
make pending ownership verification unreviewable. Lifecycle changes still control
validity and reject competing claims. No upgrade deletes reports, matches or claims.

`python -m scripts.backfill_local_features` previews missing features;
`--apply --limit 100` processes one fenced, idempotent batch. Storage reads are
outside transactions. Failed reads remain retryable; concurrent edits prevent a
stale write. Remote database/storage use requires explicit `--allow-remote`.
Unknown historical external-consent scope remains local-only.

## Evaluation And Deferred Work

See `reports/evaluation.md` for explicitly synthetic results and real-data gates.
The runner includes local/attribute/hashed baselines, synonym/image/location/colour
ablations, precision-constrained threshold selection and query-bootstrap intervals.
BM25 (k1=1.5, b=0.75) is a rank-only offline retrieval ablation; unbounded BM25
scores are not fused as probabilities. Genuine semantic/hybrid metrics require
real model-versioned vectors and are currently unmeasured.

The local scan and lifecycle lock target a small campus catalog, not high-throughput
search. Add an index/cache or narrower locks only after workload measurements.
Local SBERT/CLIP/CNNs, learned classifiers, ANN, OCR and pHash add dependencies/data
or operational cost and are not justified by this small synthetic corpus. Real
consented items, native-language review and honest error analysis come first.
