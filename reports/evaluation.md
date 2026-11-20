# Matching Evaluation Status

## Synthetic Development Only

**No real-world accuracy is established.** The 66-report `synthetic-v1` corpus
contains hand-authored English/Bengali clues and generated drawings. It shares
the generator and vocabulary with development, contains few candidates, and is
too small/easy to validate real-photo or unrestricted language performance.

Physical items were assigned to splits before evaluation: 16 paired items, 12
look-alike negatives and two unmatched queries in `tune`; eight different paired
items and four look-alikes in synthetic `test`. The tune sweep retained **0.75**
with a minimum development precision target of 0.90. That value was fixed before
the synthetic held-out run; it was not adjusted to hide its false positive.

At the shared 0.75 operating point:

| Configuration | Tune Precision / Recall / F1 | Synthetic Test Precision / Recall / F1 |
| --- | --- | --- |
| Attributes only | 0.571 / 0.750 / 0.649 | 0.636 / 0.875 / 0.737 |
| Lexical only | 1.000 / 0.563 / 0.720 | 0.875 / 0.875 / 0.875 |
| Local text + attributes | 1.000 / 1.000 / 1.000 | 0.889 / 1.000 / 0.941 |
| Local text + image + attributes | 1.000 / 1.000 / 1.000 | 0.889 / 1.000 / 0.941 |
| Without synonyms | 1.000 / 0.563 / 0.720 | 0.875 / 0.875 / 0.875 |
| Image hashes only | 0.400 / 0.625 / 0.488 | 0.714 / 0.625 / 0.667 |
| Hashed-vector baseline | 0.667 / 0.875 / 0.757 | 0.727 / 1.000 / 0.842 |

This is an ablation comparison at a shared threshold, not a claim that every
baseline was optimally calibrated. The tune report additionally records each
configuration's precision-qualified threshold. The hashed-vector baseline uses
the same structured attribute scorer and is **not Gemini or a neural model**.
Genuine semantic-only/hybrid metrics are unavailable; no provider request was made.

The synthetic held-out local result was **8 TP, 1 FP, 0 FN** across eight queries
and 12 policy-eligible pairs. Its one false positive is a different student-card
sleeve with indistinguishable public evidence. Secret ownership information is
deliberately absent from matching; human verification must resolve that case.
The held-out precision (0.889) does not meet the development precision floor;
that floor is not a generalization guarantee.

Query-bootstrap 95% intervals are precision 0.727-1.000 and F1 0.842-1.000.
Perfect tune scores and intervals at 1.0 merely reflect the sampled fixtures,
not confidence that real reports will have no errors. Mean recall@5 is 1.0 on
synthetic test; its candidates are mostly fewer than five. Precision@5 keeps a
fixed denominator of five, so one positive per query has a maximum of 0.2.
Unmatched tune queries have recall@5 defined as zero.

Removing images, colour histograms or location-zone credit changes no accepted
pair on this small corpus. There is **no measured accuracy gain** for those
signals here; their value requires independent real-photo/location evidence.
BM25 is a rank-only retrieval ablation, not a calibrated probability/threshold score.

Artifacts: `reports/synthetic-v1-tune.json`, `reports/synthetic-v1-heldout.json`,
and `data/evaluation/synthetic-v1/manifest.json`. They record dataset/image hashes,
split counts, versions, errors, intervals and ablations. Reproduction commands
are in the README. A later consented real dataset must remain separate.

## Real Data Gate

Collect at least 30 independently labelled text pairs and 10 separately consented
photo pairs, including hard negatives, missing clues and mixed language. A second
reviewer should resolve labels and report disagreement. Group by physical item
before splitting. Tune weights/threshold only on real development groups; inspect
the final real test split once. Until then the 0.75 real-report threshold remains
provisional, native-language review/usability studies remain incomplete, and no
production accuracy or hosted-provider quality claim is made.
