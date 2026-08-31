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


def accept_worker(path, output, index, generation):
    result = MODULE.ClaimStore(path).accept_orchestration(identity(index)["identity_key"], identity(index)["run_id"], generation)
    output.put(result)


def claim_and_accept_worker(path, output, index):
    store = MODULE.ClaimStore(path, lease_seconds=60)
    claimed = store.claim(identity(index))
    accepted = store.accept_orchestration(identity(index)["identity_key"], identity(index)["run_id"], claimed["generation"])
    output.put(accepted)


def conditional_canonical_start_worker(path, output):
    with sqlite3.connect(path, timeout=10) as connection:
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("BEGIN IMMEDIATE")
        result = connection.execute(
            "UPDATE autodev_runs SET state = 'BASELINING' "
            "WHERE run_id = 'run-cont-same' AND state = 'ACCEPTED'"
        )
        output.put(result.rowcount)


def test_claim_schema_has_durable_primary_key(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"))
    with sqlite3.connect(store.path) as connection:
        columns = connection.execute("PRAGMA table_info(continuation_claims)").fetchall()
        primary_keys = {row[1] for row in columns if row[5]}
    assert primary_keys == {"identity_key"}


def test_claim_store_uses_durable_sqlite_settings(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"))
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2


def test_same_identity_has_one_claim_and_reuses_run_id(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"), lease_seconds=60)
    first = store.claim(identity())
    second = store.claim(identity())
    assert first["claim_acquired"] is True
    assert second["claim_acquired"] is False
    assert second["run_id"] == first["run_id"]


def test_identity_key_cannot_rebind_canonical_provenance(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"), lease_seconds=60)
    store.claim(identity())
    conflicting = identity()
    conflicting["run_id"] = "run-cont-attacker"
    try:
        store.claim(conflicting)
    except ValueError as exc:
        assert "ownership conflict" in str(exc)
    else:
        raise AssertionError("claim identity was rebound")


def test_run_id_cannot_be_owned_by_different_identity(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"), lease_seconds=60)
    store.claim(identity("owner"))
    conflicting = identity("other")
    conflicting["run_id"] = "run-cont-owner"
    try:
        store.claim(conflicting)
    except ValueError as exc:
        assert "run_id ownership conflict" in str(exc)
    else:
        raise AssertionError("run_id was rebound to another identity")


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


def test_orchestration_accept_is_idempotent(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"), lease_seconds=60)
    claimed = store.claim(identity())
    first = store.accept_orchestration(identity()["identity_key"], identity()["run_id"], claimed["generation"])
    duplicate = store.accept_orchestration(identity()["identity_key"], identity()["run_id"], claimed["generation"])
    assert first["accepted"] is True
    assert duplicate["accepted"] is False
    assert duplicate["delivery_state"] == "ACCEPTED"


def test_duplicate_downstream_delivery_burst_starts_logically_once(tmp_path):
    path = str(tmp_path / "claims.sqlite")
    store = MODULE.ClaimStore(path, lease_seconds=60)
    claimed = store.claim(identity())
    output = multiprocessing.Queue()
    processes = [multiprocessing.Process(target=accept_worker, args=(path, output, "same", claimed["generation"])) for _ in range(20)]
    for process in processes:
        process.start()
    results = [output.get(timeout=10) for _ in processes]
    for process in processes:
        process.join()
    assert sum(result["accepted"] for result in results) == 1
    assert sum(not result["accepted"] for result in results) == 19


def test_canonical_run_transition_is_atomic_logical_start_guard(tmp_path):
    path = str(tmp_path / "claims.sqlite")
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE autodev_runs (run_id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        connection.execute("INSERT INTO autodev_runs VALUES ('run-cont-same', 'ACCEPTED')")
    output = multiprocessing.Queue()
    processes = [multiprocessing.Process(target=conditional_canonical_start_worker, args=(path, output)) for _ in range(20)]
    for process in processes:
        process.start()
    results = [output.get(timeout=10) for _ in processes]
    for process in processes:
        process.join()
    assert sum(results) == 1
    assert sum(result == 0 for result in results) == 19


def test_ack_loss_retries_delivery_without_second_logical_start(tmp_path):
    path = str(tmp_path / "claims.sqlite")
    store = MODULE.ClaimStore(path, lease_seconds=60)
    claimed = store.claim(identity())
    first_delivery = store.accept_orchestration(identity()["identity_key"], identity()["run_id"], claimed["generation"])
    # The caller loses the response after the durable consumer acceptance.
    retry_delivery = MODULE.ClaimStore(path).accept_orchestration(identity()["identity_key"], identity()["run_id"], claimed["generation"])
    assert first_delivery["accepted"] is True
    assert retry_delivery["accepted"] is False
    assert retry_delivery["delivery_state"] == "ACCEPTED"


def test_post_accept_crash_retry_is_idempotent(tmp_path):
    path = str(tmp_path / "claims.sqlite")
    store = MODULE.ClaimStore(path, lease_seconds=60)
    claimed = store.claim(identity())
    accepted = store.accept_orchestration(identity()["identity_key"], identity()["run_id"], claimed["generation"])
    # Crash occurs before the caller can persist/observe any final acknowledgement.
    restarted = MODULE.ClaimStore(path, lease_seconds=60)
    replay = restarted.accept_orchestration(identity()["identity_key"], identity()["run_id"], claimed["generation"])
    assert accepted["accepted"] is True
    assert replay["accepted"] is False


def test_stale_generation_cannot_accept_after_recovery(tmp_path):
    store = MODULE.ClaimStore(str(tmp_path / "claims.sqlite"), lease_seconds=0)
    first = store.claim(identity())
    recovered = store.claim(identity())
    stale = store.accept_orchestration(identity()["identity_key"], identity()["run_id"], first["generation"])
    current = store.accept_orchestration(identity()["identity_key"], identity()["run_id"], recovered["generation"])
    assert stale["stale"] is True
    assert current["accepted"] is True


def test_acceptance_survives_service_restart(tmp_path):
    path = str(tmp_path / "claims.sqlite")
    first_store = MODULE.ClaimStore(path, lease_seconds=60)
    claimed = first_store.claim(identity())
    accepted = first_store.accept_orchestration(identity()["identity_key"], identity()["run_id"], claimed["generation"])
    restarted_store = MODULE.ClaimStore(path, lease_seconds=60)
    replay = restarted_store.accept_orchestration(identity()["identity_key"], identity()["run_id"], claimed["generation"])
    assert accepted["accepted"] is True
    assert replay["accepted"] is False
    assert replay["delivery_state"] == "ACCEPTED"


def test_distinct_downstream_runs_start_in_parallel(tmp_path):
    path = str(tmp_path / "claims.sqlite")
    MODULE.ClaimStore(path)
    output = multiprocessing.Queue()
    processes = [multiprocessing.Process(target=claim_and_accept_worker, args=(path, output, str(i))) for i in range(20)]
    for process in processes:
        process.start()
    results = [output.get(timeout=10) for _ in processes]
    for process in processes:
        process.join()
    assert sum(result["accepted"] for result in results) == 20
