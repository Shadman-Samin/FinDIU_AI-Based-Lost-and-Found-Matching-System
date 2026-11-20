"""Evaluate local matching offline; cached semantic evaluation is explicit.

Local evaluation includes a reproducible hashed-vector baseline, not fabricated
Gemini evidence. Network embedding is opt-in for semantic/hybrid engines only.
Tune on development groups; test requires a threshold selected beforehand.
"""

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from random import Random
from time import perf_counter

from backend.app.errors import ServiceFailure
from backend.app.image_features import FEATURE_VERSION, image_features
from backend.app.image_utils import prepare_image
from backend.app.matcher import SCORING_VERSION, score_pair
from backend.app.providers import LocalEmbedder, build_embedder, validate_vector
from backend.app.text_features import tokens


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    return sum(item in relevant for item in ranked[:k]) / k


def recall(retrieved: set[str], relevant: set[str]) -> float:
    return len(retrieved & relevant) / len(relevant) if relevant else 0.0


def text_input(record: dict) -> str:
    attrs = record["public_attributes"]
    parts = [record["title"], record["description"], record["category"]]
    parts.extend(attrs.get(key, "") or "" for key in ("color", "brand", "location"))
    return " | ".join(part for part in parts if part)


def cache_key(model: str, dimensions: int, modality: str, raw: bytes) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    return f"{model}:{dimensions}:{modality}:{digest}"


def load_records(path: Path, split: str) -> list[dict]:
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    physical_splits = defaultdict(set)
    group_splits = defaultdict(set)
    required = {
        "report_id",
        "physical_item_id",
        "owner_id",
        "type",
        "category",
        "public_attributes",
        "title",
        "description",
        "event_date",
        "split",
        "match_group_id",
        "consent_for_ai",
        "embedding_model",
        "embedding_dimensions",
    }
    for record in records:
        missing = required - record.keys()
        if missing:
            raise ValueError(f"Missing required dataset fields: {', '.join(sorted(missing))}")
        if "private_detail" in record or "claim_answer" in record:
            raise ValueError("Evaluation records must not contain private verification data")
        if record["consent_for_ai"] is not True:
            raise ValueError(f"AI consent is required for report {record['report_id']}")
        if record.get("image_path") and record.get("image_consent") is not True:
            raise ValueError(f"Image consent is required for report {record['report_id']}")
        physical_splits[record["physical_item_id"]].add(record["split"])
        group_splits[record["match_group_id"]].add(record["split"])
    if any(len(splits) > 1 for splits in (*physical_splits.values(), *group_splits.values())):
        raise ValueError("Physical items and match groups must not cross evaluation splits")
    selected = [record for record in records if record["split"] == split]
    if not selected:
        raise ValueError(f"No records for split={split!r}")
    ids = [record["report_id"] for record in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("report_id values must be unique within a split")
    for record in selected:
        if record["type"] not in {"lost", "found"}:
            raise ValueError("report type must be lost or found")
        if not record.get("physical_item_id") or not record.get("match_group_id"):
            raise ValueError("physical_item_id and match_group_id are required labels")
        if Path(record.get("image_path") or "").is_absolute():
            raise ValueError("image_path must be relative to the dataset directory")
    return selected


def _record_vectors(record, dataset_dir, cache, embedder=None):
    semantic_model = not str(record.get("embedding_model") or "").startswith("local-hash-")
    if semantic_model and record.get("consent_for_external_ai") is not True:
        raise ValueError("External AI consent is required for semantic vectors")
    text = text_input(record).encode("utf-8")
    image_path = record.get("image_path")
    image = None
    if image_path:
        root = dataset_dir.resolve()
        resolved = (root / image_path).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("image_path must remain inside the evaluation dataset")
        image = prepare_image(resolved.read_bytes())
    model = record.get("embedding_model")
    dimensions = record.get("embedding_dimensions")
    if not model or not isinstance(dimensions, int):
        raise ValueError(
            f"Embedding model/dimensions are required for report {record['report_id']}"
        )
    text_key = cache_key(model, dimensions, "text", text)
    image_key = cache_key(model, dimensions, "image", image) if image is not None else None
    local_baseline = isinstance(embedder, LocalEmbedder)
    for modality, key, raw in (
        ("text", text_key, text.decode("utf-8")),
        ("image", image_key, image),
    ):
        if key is None:
            continue
        if key not in cache:
            if embedder is None:
                raise ValueError(
                    f"Missing cached {modality} vector for report {record['report_id']}"
                )
            try:
                cache[key] = getattr(embedder, f"embed_{modality}")(raw)
            except ServiceFailure as error:
                if not local_baseline or error.code != "empty_embedding":
                    raise
                # Degenerate legacy fingerprints are unavailable, not local pipeline failures.
                cache[key] = None
        if cache[key] is not None or not local_baseline:
            cache[key] = validate_vector(cache[key], dimensions)
    record = dict(record)
    record["text_embedding"] = cache.get(text_key)
    record["image_embedding"] = cache.get(image_key) if image_key else None
    record["image_features"] = image_features(image) if image is not None else None
    record["image_sha256"] = hashlib.sha256(image).hexdigest() if image is not None else None
    return record


def eligible(lost: dict, found: dict, date_window_days: int) -> bool:
    lost_date, found_date = (
        date.fromisoformat(lost["event_date"]),
        date.fromisoformat(found["event_date"]),
    )
    gap = (found_date - lost_date).days
    return (
        lost["owner_id"] != found["owner_id"]
        and lost["category"] == found["category"]
        and 0 <= gap <= date_window_days
    )


def _score(lost, found, date_window_days, mode="semantic", **options):
    left = {
        **lost["public_attributes"],
        "event_date": date.fromisoformat(lost["event_date"]),
        "title": lost["title"],
        "description": lost["description"],
        "image_features": lost.get("image_features"),
        "text_embedding": lost.get("text_embedding"),
        "image_embedding": lost.get("image_embedding"),
        "embedding_model": lost.get("embedding_model"),
        "embedding_dimensions": lost.get("embedding_dimensions"),
    }
    right = {
        **found["public_attributes"],
        "event_date": date.fromisoformat(found["event_date"]),
        "title": found["title"],
        "description": found["description"],
        "image_features": found.get("image_features"),
        "text_embedding": found.get("text_embedding"),
        "image_embedding": found.get("image_embedding"),
        "embedding_model": found.get("embedding_model"),
        "embedding_dimensions": found.get("embedding_dimensions"),
    }
    if mode == "semantic" and lost.get("embedding_model", "gemini-embedding-2") != found.get(
        "embedding_model", "gemini-embedding-2"
    ):
        raise ValueError("Cannot compare reports embedded by different models")
    if mode == "semantic" and lost.get("embedding_dimensions", 768) != found.get(
        "embedding_dimensions", 768
    ):
        raise ValueError("Cannot compare reports with different embedding dimensions")
    return score_pair(left, right, date_window_days, mode=mode, **options)


def _query_metrics(query, candidates, relevant, threshold):
    ranked = sorted(candidates, key=lambda row: (-row[1], row[0]))
    predicted = {report_id for report_id, score in ranked if score >= threshold}
    ranked_ids = [report_id for report_id, _ in ranked]
    return {
        "query": query,
        "candidates": len(ranked),
        "tp": len(predicted & relevant),
        "fp": len(predicted - relevant),
        "fn": len(relevant - predicted),
        "precision_at_5": precision_at_k(ranked_ids, relevant, 5),
        "recall_at_5": recall(set(ranked_ids[:5]), relevant),
    }


def _summarize(rows, bootstrap=False):
    tp, fp, fn = (sum(row[key] for row in rows) for key in ("tp", "fp", "fn"))
    precision = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    result = {
        "queries": len(rows),
        "eligible_pairs": sum(row["candidates"] for row in rows),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": rec,
        "f1": 2 * precision * rec / (precision + rec) if precision + rec else 0.0,
        "mean_precision_at_5": sum(row["precision_at_5"] for row in rows) / len(rows)
        if rows
        else 0.0,
        "mean_recall_at_5": sum(row["recall_at_5"] for row in rows) / len(rows) if rows else 0.0,
    }
    if bootstrap and rows:
        random = Random(20261119)
        samples = [
            _summarize([rows[random.randrange(len(rows))] for _ in rows]) for _ in range(500)
        ]
        result["confidence_intervals_95"] = {}
        for key in ("precision", "recall", "f1", "mean_recall_at_5"):
            values = sorted(sample[key] for sample in samples)
            result["confidence_intervals_95"][key] = [values[12], values[487]]
    return result


def bm25_rank(query, candidates):
    documents = [
        Counter(tokens(row["title"]) * 2 + tokens(row["description"])) for row in candidates
    ]
    frequency = Counter(word for document in documents for word in document)
    query_words = set(tokens(query["title"]) + tokens(query["description"]))
    average = (
        sum(sum(document.values()) for document in documents) / len(documents) if documents else 1
    )
    ranked = []
    for report, document in zip(candidates, documents, strict=True):
        score = 0.0
        length = sum(document.values())
        for word in query_words:
            tf = document[word]
            if tf:
                idf = math.log(
                    1 + (len(documents) - frequency[word] + 0.5) / (frequency[word] + 0.5)
                )
                score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / max(average, 1)))
        ranked.append((report["report_id"], score))
    return [report_id for report_id, _ in sorted(ranked, key=lambda row: (-row[1], row[0]))]


def evaluate(records, threshold, date_window_days=30, *, mode="semantic", bootstrap=False):
    lost_reports = [record for record in records if record["type"] == "lost"]
    found_reports = [record for record in records if record["type"] == "found"]
    names = (
        ("attribute_only", "text_attributes", "all_evidence")
        if mode == "semantic"
        else (
            "attribute_only",
            "lexical_only",
            "local_text_attributes",
            "local_all",
            "no_synonyms",
            "no_location_zones",
            "no_colour_histogram",
            "image_hash_only",
            "hash_baseline",
            "semantic_only",
            "hybrid_all",
        )
    )
    results = {name: [] for name in names}
    available, bm25 = set(), []
    for lost in lost_reports:
        eligible_found = [
            found for found in found_reports if eligible(lost, found, date_window_days)
        ]
        scores = {name: [] for name in names}
        for found in eligible_found:
            if mode == "semantic":
                components = _score(lost, found, date_window_days)
                variants = {
                    "attribute_only": components["attr_score"],
                    "text_attributes": 0.6 * max(0, components["text_sim"])
                    + 0.4 * components["attr_score"],
                    "all_evidence": components["score"],
                }
            else:
                components = _score(lost, found, date_window_days, "local")
                perceptual = (components["evidence"]["image"] or {}).get("perceptual")
                hash_score = None
                if perceptual:
                    weight = perceptual["weights"]["dhash"] + perceptual["weights"]["ahash"]
                    if weight:
                        hash_score = (
                            perceptual["dhash_sim"] * perceptual["weights"]["dhash"]
                            + perceptual["ahash_sim"] * perceptual["weights"]["ahash"]
                        ) / weight
                variants = {
                    "attribute_only": components["attr_score"],
                    "lexical_only": components["text_sim"],
                    "local_text_attributes": _score(
                        lost, found, date_window_days, "local", images=False
                    )["score"],
                    "local_all": components["score"],
                    "no_synonyms": _score(lost, found, date_window_days, "local", synonyms=False)[
                        "score"
                    ],
                    "no_location_zones": _score(
                        lost, found, date_window_days, "local", location_zones=False
                    )["score"],
                    "no_colour_histogram": _score(
                        lost, found, date_window_days, "local", color_histogram=False
                    )["score"],
                    "image_hash_only": hash_score,
                }
                if (
                    (lost.get("embedding_model") or "").startswith("local-hash-")
                    and lost.get("text_embedding")
                    and found.get("text_embedding")
                ):
                    variants["hash_baseline"] = _score(lost, found, date_window_days)["score"]
                else:
                    hybrid = _score(lost, found, date_window_days, "hybrid")
                    if hybrid["evidence"]["mode"] == "hybrid":
                        variants["hybrid_all"] = hybrid["score"]
                        variants["semantic_only"] = hybrid["evidence"]["text"]["semantic"]
            for name, value in variants.items():
                if value is not None:
                    scores[name].append((found["report_id"], max(0.0, value)))
                    available.add(name)
        # Labelled positives excluded by hard eligibility rules still count as misses.
        relevant = {
            found["report_id"]
            for found in found_reports
            if found["match_group_id"] == lost["match_group_id"]
        }
        for name in names:
            results[name].append(
                _query_metrics(lost["report_id"], scores[name], relevant, threshold)
            )
        if mode != "semantic":
            ranked = bm25_rank(lost, eligible_found)
            bm25.append((precision_at_k(ranked, relevant, 5), recall(set(ranked[:5]), relevant)))
    optional = {"hash_baseline", "semantic_only", "hybrid_all"}
    summary = {
        name: _summarize(rows, bootstrap)
        for name, rows in results.items()
        if name not in optional or name in available
    }
    if mode != "semantic":
        summary["bm25_ranking"] = {
            "queries": len(bm25),
            "mean_precision_at_5": sum(row[0] for row in bm25) / len(bm25) if bm25 else 0.0,
            "mean_recall_at_5": sum(row[1] for row in bm25) / len(bm25) if bm25 else 0.0,
            "note": "Rank-only retrieval ablation; raw BM25 is not a calibrated 0-1 match score.",
        }
    return summary


def select_threshold(sweep, minimum_precision=0.9):
    qualified = [
        (float(threshold), row)
        for threshold, row in sweep.items()
        if row["precision"] >= minimum_precision
    ]
    if not qualified:
        return None
    return max(
        qualified, key=lambda row: (row[1]["recall"], row[1]["precision"], row[1]["f1"], row[0])
    )[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--cache",
        type=Path,
        help="JSON model/dimension/hash -> vector cache (semantic/hybrid only)",
    )
    parser.add_argument("--split", choices=("tune", "test"), required=True)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--engine", choices=("local", "semantic", "hybrid"), default="local")
    parser.add_argument(
        "--model", help="explicit cache/model override; does not change dataset labels"
    )
    parser.add_argument("--dimensions", type=int)
    parser.add_argument("--minimum-precision", type=float, default=0.9)
    parser.add_argument(
        "--allow-api",
        action="store_true",
        help="explicitly call configured embedding provider for missing vectors",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.split == "test" and args.threshold is None:
        parser.error("--threshold must be fixed from the tune split before evaluating test")
    if args.engine == "local" and args.allow_api:
        parser.error("--allow-api is not permitted with local evaluation")
    if args.engine != "local" and args.cache is None:
        parser.error("--cache is required for semantic/hybrid evaluation")
    if not 0 <= args.minimum_precision <= 1:
        parser.error("--minimum-precision must be between 0 and 1")
    if args.dimensions is not None and not 1 <= args.dimensions <= 3072:
        parser.error("--dimensions must be between 1 and 3072")
    threshold = 0.75 if args.threshold is None else args.threshold
    if not 0 <= threshold <= 1:
        parser.error("--threshold must be between 0 and 1")
    started = perf_counter()
    records = load_records(args.dataset, args.split)
    cache = (
        json.loads(args.cache.read_text(encoding="utf-8"))
        if args.cache and args.cache.exists()
        else {}
    )
    embedder = None
    if args.engine == "local":
        embedder = LocalEmbedder(768)
        for record in records:
            record["embedding_model"], record["embedding_dimensions"] = (
                embedder.model,
                embedder.dimensions,
            )
    else:
        for record in records:
            if args.model:
                record["embedding_model"] = args.model
            if args.dimensions:
                record["embedding_dimensions"] = args.dimensions
    if args.allow_api:
        if any(record.get("consent_for_external_ai") is not True for record in records):
            parser.error("External AI consent is required for every report before --allow-api")
        from backend.app.config import Settings

        embedder = build_embedder(Settings(matching_mode="hybrid", embedding_provider="gemini"))
        if embedder is None:
            parser.error("--allow-api requires a configured GEMINI_API_KEY")
        for record in records:
            record["embedding_model"] = embedder.model
            record["embedding_dimensions"] = embedder.dimensions
    enriched = [_record_vectors(record, args.dataset.parent, cache, embedder) for record in records]
    if args.allow_api:
        args.cache.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    mode = "semantic" if args.engine == "semantic" else "local"
    metrics = evaluate(enriched, threshold, mode=mode, bootstrap=True)
    primary = (
        "all_evidence"
        if args.engine == "semantic"
        else "hybrid_all"
        if args.engine == "hybrid" and "hybrid_all" in metrics
        else "local_all"
    )
    result = {
        "engine": args.engine,
        "scoring_version": SCORING_VERSION,
        "feature_version": FEATURE_VERSION,
        "model_role": "hashed evaluation baseline, not the primary local scorer"
        if args.engine == "local"
        else "cached/opt-in semantic vectors",
        "baseline_missing_vectors": {
            "text": sum(record.get("text_embedding") is None for record in enriched),
            "image": sum(
                bool(record.get("image_path")) and record.get("image_embedding") is None
                for record in enriched
            ),
        }
        if args.engine == "local"
        else None,
        "primary_configuration": primary,
        "synthetic": any(record.get("synthetic") is True for record in enriched),
        "sources": sorted({record.get("source", "provided") for record in enriched}),
        "warning": "Synthetic development results are not real-world accuracy evidence."
        if any(record.get("synthetic") is True for record in enriched)
        else "Dataset consent/provenance is declared, not independently verified.",
        "split": args.split,
        "threshold": threshold,
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "models": sorted({record["embedding_model"] for record in enriched}),
        "dimensions": sorted({record["embedding_dimensions"] for record in enriched}),
        "record_count": len(enriched),
        "metrics": metrics,
        "unavailable_configurations": [
            name for name in ("semantic_only", "hybrid_all") if name not in metrics
        ]
        if args.engine != "semantic"
        else [],
        "image_set_sha256": hashlib.sha256(
            json.dumps(
                sorted((record["report_id"], record.get("image_sha256")) for record in enriched)
            ).encode()
        ).hexdigest(),
    }
    if args.split == "tune":
        result["threshold_sweep"] = {
            f"{threshold:.3f}": evaluate(enriched, threshold, mode=mode)
            for threshold in (
                0.50,
                0.55,
                0.60,
                0.65,
                0.70,
                0.75,
                0.80,
                0.825,
                0.85,
                0.875,
                0.90,
                0.925,
                0.95,
                0.975,
            )
        }
        result["recommended_threshold"] = select_threshold(
            {point: values[primary] for point, values in result["threshold_sweep"].items()},
            args.minimum_precision,
        )
        result["minimum_precision"] = args.minimum_precision
        result["calibration"] = {}
        for name in metrics:
            if name == "bm25_ranking":
                continue
            points = {point: values[name] for point, values in result["threshold_sweep"].items()}
            chosen = select_threshold(points, args.minimum_precision)
            result["calibration"][name] = {
                "threshold": chosen,
                "metrics": points[f"{chosen:.3f}"] if chosen is not None else None,
            }
    result["elapsed_seconds_including_cache_and_optional_embedding"] = perf_counter() - started
    output = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "synthetic": result["synthetic"],
                    "record_count": len(enriched),
                    "threshold": threshold,
                    "recommended_threshold": result.get("recommended_threshold"),
                    "primary_metrics": metrics[primary],
                }
            )
        )
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
