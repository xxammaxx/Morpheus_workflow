import importlib.util
import multiprocessing
import sqlite3
from pathlib import Path


ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location("continuation_claim", ROOT / "runtime" / "continuation_claim.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def identity(index="same"):
    return {
        "identity_key": f"project/source/correlation/{index}",
        "run_id": f"run-cont-{index}",
        "project_id": "project",
        "source_run_id": "run-source",
        "correlation_id": f"correlation-{index}",
    }


def worker(path, output, index):
    result = MODULE.ClaimStore(path).claim(identity(index))
    output.put(result)


def test_claim_schema_has_durable_primary_key(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"))
    with sqlite3.connect(store.path) as connection:
        columns = connection.execute("PRAGMA table_info(continuation_claims)").fetchall()
        primary_keys = {row[1] for row in columns if row[5]}
    assert primary_keys == {"identity_key"}


def test_same_identity_has_one_claim_and_reuses_run_id(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"), lease_seconds=60)
    first = store.claim(identity())
    second = store.claim(identity())
    assert first["claim_acquired"] is True
    assert second == {"claim_acquired": False, "run_id": first["run_id"], "state": "CLAIMED"}


def test_concurrent_pair_acquires_once_across_processes(tmp_path):
    path = str(tmp_path / "claims.sqlite")
    MODULE.ClaimStore(path)
    output = multiprocessing.Queue()
    processes = [multiprocessing.Process(target=worker, args=(path, output, "same")) for _ in range(2)]
    for process in processes:
        process.start()
    results = [output.get(timeout=10) for _ in processes]
    for process in processes:
        process.join()
    assert sum(result["claim_acquired"] for result in results) == 1
    assert {result["run_id"] for result in results} == {"run-cont-same"}


def test_distinct_identities_are_not_globally_serialized(tmp_path):
    path = str(tmp_path / "claims.sqlite")
    MODULE.ClaimStore(path)
    output = multiprocessing.Queue()
    processes = [multiprocessing.Process(target=worker, args=(path, output, str(i))) for i in range(20)]
    for process in processes:
        process.start()
    results = [output.get(timeout=10) for _ in processes]
    for process in processes:
        process.join()
    assert sum(result["claim_acquired"] for result in results) == 20


def test_expired_claim_recovers_same_canonical_run(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"), lease_seconds=0)
    first = store.claim(identity())
    recovered = store.claim(identity())
    assert first["run_id"] == recovered["run_id"] == "run-cont-same"
    assert recovered["recovered"] is True
