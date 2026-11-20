import json
from collections import Counter
from pathlib import Path

import pytest


def test_generated_corpus_is_labelled_synthetic_and_split_by_physical_item(tmp_path):
    from scripts.build_dev_corpus import build_corpus

    dataset = build_corpus(tmp_path / "corpus")
    records = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 66
    assert Counter((row["split"], row["type"]) for row in records) == {
        ("tune", "lost"): 18,
        ("tune", "found"): 28,
        ("test", "lost"): 8,
        ("test", "found"): 12,
    }
    for row in records:
        assert row["synthetic"] is True and row["source"] == "findiu-synthetic-v1"
        assert "private_detail" not in row and "claim_answer" not in row
        assert not Path(row.get("image_path") or "").is_absolute()
        if row.get("image_path"):
            assert (dataset.parent / row["image_path"]).is_file()
    splits = {}
    groups = {}
    for row in records:
        splits.setdefault(row["physical_item_id"], set()).add(row["split"])
        groups.setdefault(row["match_group_id"], []).append(row)
    assert all(len(values) == 1 for values in splits.values())
    positives = [
        rows for rows in groups.values() if {row["type"] for row in rows} == {"lost", "found"}
    ]
    assert len(positives) == 24
    assert all(rows[0]["owner_id"] != rows[1]["owner_id"] for rows in positives)


def test_corpus_generation_is_reproducible_including_illustrations(tmp_path):
    from scripts.build_dev_corpus import build_corpus

    first = build_corpus(tmp_path / "first")
    second = build_corpus(tmp_path / "second")
    assert first.read_bytes() == second.read_bytes()
    records = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    for row in records:
        if row.get("image_path"):
            assert (first.parent / row["image_path"]).read_bytes() == (
                second.parent / row["image_path"]
            ).read_bytes()


def test_generator_refuses_to_overwrite_real_reports(tmp_path):
    from scripts.build_dev_corpus import build_corpus

    existing = tmp_path / "reports.jsonl"
    existing.write_text(
        json.dumps({"synthetic": False, "report_id": "real-user-report"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="overwrite"):
        build_corpus(tmp_path)
    assert json.loads(existing.read_text())["report_id"] == "real-user-report"


def test_local_evaluation_cli_needs_no_cache_or_provider(tmp_path, capsys, monkeypatch):
    from scripts import evaluate
    from scripts.build_dev_corpus import build_corpus

    def forbidden(*args):
        raise AssertionError("Local evaluation must not call a hosted provider")

    monkeypatch.setattr(evaluate, "build_embedder", forbidden)
    dataset = build_corpus(tmp_path / "corpus")
    assert (
        evaluate.main([str(dataset), "--engine", "local", "--split", "tune", "--threshold", "0.75"])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["metrics"]["local_all"]["queries"] == 18
    assert report["synthetic"] is True
    assert report["unavailable_configurations"] == ["semantic_only", "hybrid_all"]
    assert len(report["dataset_sha256"]) == 64


def test_local_evaluation_cannot_opt_in_to_api_calls(capsys):
    from scripts.evaluate import main

    with pytest.raises(SystemExit) as error:
        main(["unused.jsonl", "--engine", "local", "--split", "tune", "--allow-api"])
    assert error.value.code == 2
    assert "--allow-api is not permitted with local evaluation" in capsys.readouterr().err


def test_calibration_only_selects_a_precision_qualified_operating_point():
    from scripts.evaluate import select_threshold

    sweep = {
        "0.50": {"precision": 0.8, "recall": 1.0, "f1": 0.889},
        "0.60": {"precision": 0.95, "recall": 0.8, "f1": 0.869},
        "0.75": {"precision": 1.0, "recall": 0.7, "f1": 0.823},
    }
    assert select_threshold(sweep, minimum_precision=0.9) == 0.6
    assert select_threshold({"0.50": sweep["0.50"]}, minimum_precision=0.9) is None


def test_bm25_ranking_prefers_distinctive_public_clues_over_generic_terms():
    from scripts.evaluate import bm25_rank

    query = {"title": "Blue bag", "description": "crescent sticker broken zipper"}
    found = [
        {"report_id": "generic", "title": "Blue bag", "description": "plain blue campus bag"},
        {
            "report_id": "marked",
            "title": "Blue backpack",
            "description": "broken zipper crescent sticker",
        },
    ]
    assert bm25_rank(query, found)[0] == "marked"


def test_bootstrap_metrics_are_deterministic_and_use_query_level_sampling():
    from test_evaluation import item

    from scripts.evaluate import evaluate

    records = [
        item("lost", "lost", "a", "owner", [1, 0], 1),
        item("found", "found", "a", "finder", [1, 0], 2),
    ]
    result = evaluate(records, 0.75, mode="local", bootstrap=True)["local_all"]
    assert result["confidence_intervals_95"]["f1"] == [1.0, 1.0]
    assert result == evaluate(records, 0.75, mode="local", bootstrap=True)["local_all"]
