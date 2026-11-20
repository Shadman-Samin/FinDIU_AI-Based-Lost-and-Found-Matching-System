# Evaluation Data

No participant-collected evaluation records are included yet. Do not populate
this file with invented participant or photo evidence. Recruit consenting
participants, remove identifiers, and retain only public report fields before
adding `pairs.jsonl`.
`synthetic-v1/` is a separate, reproducible 66-report development fixture corpus,
not participant-collected data. Keep later real items in a different directory.

One JSON object per report. `physical_item_id` and `match_group_id` are offline
evaluation labels and must never be uploaded to the application. Keep every
physical item and match group entirely within one split (`tune` or `test`). A
positive lost/found pair shares `match_group_id`; hard negatives should use
different groups but the same category. `owner_id` is a pseudonym used only to
exclude same-owner comparisons.

Required fields: `report_id`, `physical_item_id`, `owner_id`, `type`, `category`,
`public_attributes` (`color`, optional `brand`, `location`), `title`,
`description`, ISO `event_date`, `match_group_id`, `split`, and
`consent_for_ai: true`, `embedding_model`, and `embedding_dimensions`. Optional `image_path` is relative to this directory and
requires `image_consent: true`. Never include private verification details,
claim answers, names, email addresses, student IDs, or unconsented photos.
`consent_for_ai` covers the declared matching use. New network embedding calls
additionally require `consent_for_external_ai: true` for every selected report.
An application report's `semantic_consent` must be mapped faithfully to this
field; neither a mode switch nor an evaluation command may invent consent.

The offline vector cache is separate and ignored by version control. Keys include
provider model, dimensions, modality, and SHA-256 of exact public input bytes.
Local evaluation is the default and uses no network/cache. It calculates lexical
and image evidence and a separately labelled hashed-vector baseline. Genuine
semantic/hybrid evaluation uses `--engine semantic` or `--engine hybrid`, with
`--cache` and optional explicit `--model`/`--dimensions` overrides. It refuses
missing vectors unless `--allow-api` and report-scoped external consent are both
present. Use `tune` for threshold sweeps; freeze before `test`. Never tune on real
test groups or merge synthetic metrics into real-data results.
