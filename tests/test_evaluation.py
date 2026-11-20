import json
from datetime import date

import pytest

from scripts.evaluate import evaluate, load_records, precision_at_k, recall


def item(report_id, kind, group, owner, vector, day):
    return {
        "report_id": report_id,
        "physical_item_id": group,
        "owner_id": owner,
        "type": kind,
        "category": "bag",
        "public_attributes": {"color": "blue", "brand": "acme", "location": "library"},
        "title": "Blue campus bag",
        "description": "Blue bag with a marked zipper near the library",
        "event_date": date(2026, 11, day).isoformat(),
        "match_group_id": group,
        "split": "tune",
        "consent_for_ai": True,
        "consent_for_external_ai": True,
        "embedding_model": "test-vector-v1",
        "embedding_dimensions": 2,
        "text_embedding": vector,
        "image_embedding": None,
    }


def test_precision_at_three_counts_missing_slots():
    assert precision_at_k(["correct"], {"correct"}, 3) == pytest.approx(1 / 3)


def test_recall_zero_positive_is_defined_as_zero():
    assert recall({"candidate"}, set()) == 0.0


def test_metrics_rank_a_labelled_positive_over_same_category_negative(tmp_path):
    lost = item("l1", "lost", "physical-a", "owner-a", [1, 0], 1)
    positive = item("f1", "found", "physical-a", "owner-b", [1, 0], 2)
    negative = item("f2", "found", "physical-b", "owner-c", [0, 1], 2)
    result = evaluate([lost, positive, negative], 0.75)
    assert result["all_evidence"]["true_positive"] == 1
    assert result["all_evidence"]["false_positive"] == 0
    assert result["all_evidence"]["false_negative"] == 0
    assert result["all_evidence"]["mean_precision_at_5"] == pytest.approx(1 / 5)
    assert result["all_evidence"]["mean_recall_at_5"] == 1.0


def test_dataset_loader_refuses_cross_split_physical_item(tmp_path):
    rows = [item("l1", "lost", "same", "a", [1, 0], 1), item("f1", "found", "same", "b", [1, 0], 2)]
    rows[1]["split"] = "test"
    path = tmp_path / "pairs.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(ValueError, match="must not cross"):
        load_records(path, "tune")


def test_dataset_loader_requires_explicit_ai_consent(tmp_path):
    record = item("l1", "lost", "same", "a", [1, 0], 1)
    record["consent_for_ai"] = False
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="AI consent"):
        load_records(path, "tune")


def test_test_split_requires_a_preselected_threshold():
    from scripts.evaluate import main

    with pytest.raises(SystemExit) as exit_code:
        main(["unused.jsonl", "--cache", "unused-cache.json", "--split", "test"])
    assert exit_code.value.code == 2


def test_eligibility_filtered_positive_is_counted_as_false_negative(tmp_path):
    lost = item("l1", "lost", "physical-a", "a", [1, 0], 2)
    earlier_found = item("f1", "found", "physical-a", "b", [1, 0], 1)
    metrics = evaluate([lost, earlier_found], 0.75)["all_evidence"]
    assert metrics["eligible_pairs"] == 0
    assert metrics["false_negative"] == 1
    assert metrics["recall"] == 0


def test_offline_runner_requires_cache_and_never_falls_back_to_provider(tmp_path):
    from scripts.evaluate import _record_vectors

    record = item("l1", "lost", "physical-a", "a", [1, 0], 1)
    with pytest.raises(ValueError, match="Missing cached text vector"):
        _record_vectors(record, tmp_path, {})


def test_offline_cli_reports_known_vectors_and_dataset_hash(tmp_path, capsys):
    from scripts.evaluate import cache_key, main, text_input

    records = [
        item("l1", "lost", "physical-a", "a", [1, 0], 1),
        item("f1", "found", "physical-a", "b", [1, 0], 2),
    ]
    dataset = tmp_path / "pairs.jsonl"
    dataset.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")
    cache = {
        cache_key("test-vector-v1", 2, "text", text_input(row).encode()): [1, 0] for row in records
    }
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    assert (
        main([str(dataset), "--engine", "semantic", "--cache", str(cache_path), "--split", "tune"])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert len(report["dataset_sha256"]) == 64
    assert report["metrics"]["all_evidence"]["true_positive"] == 1
    assert "0.750" in report["threshold_sweep"]


def test_api_evaluation_requires_report_scoped_external_permission(tmp_path, monkeypatch, capsys):
    from scripts import evaluate

    record = item("l1", "lost", "physical-a", "owner-a", [1, 0], 1)
    record["consent_for_external_ai"] = False
    dataset = tmp_path / "reports.jsonl"
    dataset.write_text(json.dumps(record), encoding="utf-8")

    def forbidden(*args):
        raise AssertionError("No provider may be constructed without report-scoped permission")

    monkeypatch.setattr(evaluate, "build_embedder", forbidden)
    with pytest.raises(SystemExit) as error:
        evaluate.main(
            [
                str(dataset),
                "--engine",
                "hybrid",
                "--split",
                "tune",
                "--cache",
                str(tmp_path / "vectors.json"),
                "--allow-api",
            ]
        )
    assert error.value.code == 2
    assert "External AI consent is required" in capsys.readouterr().err


def test_degenerate_hashed_image_baseline_cannot_block_local_evaluation(tmp_path, capsys):
    from PIL import Image

    from scripts.evaluate import main

    Image.new("RGB", (32, 32), "black").save(tmp_path / "black.jpg", "JPEG")
    records = [
        item("lost", "lost", "same", "owner", [1, 0], 1),
        item("found", "found", "same", "finder", [1, 0], 2),
    ]
    for row in records:
        row.update(
            title="Black phone",
            description="Plain black phone cover",
            image_path="black.jpg",
            image_consent=True,
            category="phone",
            split="test",
        )
        row["public_attributes"]["color"] = "black"
    dataset = tmp_path / "reports.jsonl"
    dataset.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")
    assert main([str(dataset), "--engine", "local", "--split", "test", "--threshold", "0.75"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["metrics"]["local_all"]["true_positive"] == 1
    assert report["baseline_missing_vectors"] == {"text": 0, "image": 2}
