import json
import os

from backend.app import pipeline
from backend.app.detection import evaluate as ev
from backend.app.ingestion import service as ing


def test_ingestion_detects_all_sources(smoke_dataset):
    pfs = ing.parse_directory(smoke_dataset)
    sources = {pf.source_type for pf in pfs}
    assert {"BANK", "CDR", "IPDR"} <= sources
    # confidence high -> no manual mapping needed on synthetic data
    assert all(pf.confidence >= 0.8 for pf in pfs if pf.source_type)


def test_entity_fusion(smoke_dataset):
    inv = pipeline.run(smoke_dataset, window_minutes=10)
    core = {k: v for k, v in inv.entities.items() if not v.get("external")}
    fused = [v for v in core.values()
             if "ACCOUNT_NO" in v["types"] and "PHONE" in v["types"]]
    # bank accounts fuse with telecom identities via registered mobile
    assert len(fused) >= 1


def test_correlation_finds_planted_coincidence(smoke_dataset):
    inv = pipeline.run(smoke_dataset, window_minutes=10)
    gt = json.load(open(os.path.join(smoke_dataset, "ground_truth.json")))
    planted = [g for g in gt if g["type"] == "call_transfer_coincidence"]
    assert planted, "expected a planted coincidence"
    assert len(inv.correlation_hits) >= 1


def test_detection_recall(smoke_dataset):
    inv = pipeline.run(smoke_dataset, window_minutes=10)
    gt = json.load(open(os.path.join(smoke_dataset, "ground_truth.json")))
    report = ev.evaluate(gt, inv.risk, inv.node_to_entity)
    # every planted scenario with identifiers should be caught (recall == 1.0)
    assert report["overall_recall"] == 1.0


def test_reporting_generates(smoke_dataset, tmp_path):
    from backend.app.reporting import service as rep
    inv = pipeline.run(smoke_dataset, window_minutes=10)
    data = {"summary": inv.summary(), "events": inv.events, "entities": inv.entities,
            "correlation_hits": inv.correlation_hits, "transfers": inv.transfers,
            "risk": inv.risk, "input_dir": inv.input_dir, "window": 10}
    p = rep.generate(data, str(tmp_path), "pdf")
    assert os.path.getsize(p) > 1000
