"""Durability, crash and concurrency tests for the N30 registry (ADR-094).

Synthetic authority only (tests/n30_synthetic.py). These tests prove local SQLite
behaviour; they say nothing about external authority, network filesystems or a
privileged coherent rollback of the whole database file.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from hive_mind_os.campaign_metrics import (
    AdmissionUse,
    BracketSnapshot,
    BracketState,
    CampaignMetricsError,
    canonical_digest,
    canonical_document,
)
from hive_mind_os.n30_host_registry import (
    HostPorts,
    N30HostRegistry,
    N30StoreError,
    issue_request_digest,
)
from tests.n30_synthetic import World
from tests.test_campaign_metrics import seal_for

ROOT = Path(__file__).resolve().parents[1]
BRACKET_COMMON = {
    "protocol_digest": "sha256:" + "1" * 64,
    "admission_digest": "sha256:" + "2" * 64,
    "stage": "original",
    "track": "builder-component",
}

CHILD = r"""
import os
import sys
from pathlib import Path

from hive_mind_os.campaign_metrics import ConsumeRoundRequest, transition_after_round
from hive_mind_os.n30_host_registry import consume_request_digest
from tests.n30_synthetic import World

directory, phase, point = sys.argv[1:4]
armed = {"on": False}


def hook(name):
    if armed["on"] and name == point:
        os._exit(17)


w = World(directory, create=False, outcome_dependency="direct_permitted", fault_hook=hook)
handle = w.admit()
state = w.registry.recover_bracket(handle, w.p.protocol_digest, "original", "builder-component")
if phase == "issue":
    armed["on"] = True
    state.schedule(w.p, registry=w.registry, admission_handle=handle)
else:
    receipts = state.schedule(w.p, registry=w.registry, admission_handle=handle).receipts
    results = w.script_direct(receipts)
    bracket = w.registry.resolve_bracket(handle, state.opaque_handle, w.p.protocol_digest, "apply")
    request = ConsumeRoundRequest(
        bracket.admission_digest,
        w.p.protocol_digest,
        "original",
        1,
        bracket.bracket_digest,
        results,
        transition_after_round(w.p, bracket, results),
    )
    bracket_id, _ = w.registry.state_identity(state.opaque_handle)
    Path(directory, "request.txt").write_text(consume_request_digest(bracket_id, request))
    armed["on"] = True
    state.apply(w.p, results, registry=w.registry, admission_handle=handle)
sys.exit(0)
"""


def raw(path, *statements):
    """Edit the database behind the registry's back, as corruption or an attacker would."""
    connection = sqlite3.connect(path)
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def table_counts(path):
    connection = sqlite3.connect(path)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("audit", "bracket_versions", "receipts", "status_observations", "meta")
        }
    finally:
        connection.close()


def versioned_document(**changes):
    document = json.loads(json.dumps(canonical_document(BracketSnapshot(**BRACKET_COMMON))))
    document.update(changes)
    return document


def legacy_document():
    snapshot = BracketSnapshot(**BRACKET_COMMON)
    return json.loads(json.dumps(canonical_document(snapshot.legacy_document())))


def replace_bracket(document):
    """SQL that swaps every stored bracket document for ``document`` (raw tampering)."""
    literal = json.dumps(document, sort_keys=True, separators=(",", ":")).replace("'", "''")
    return f"UPDATE bracket_versions SET canonical = CAST('{literal}' AS BLOB)"


class DurabilityBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def world(self, **kwargs):
        directory = tempfile.mkdtemp(dir=self._tmp.name)
        world = World(directory, **kwargs)
        self.addCleanup(lambda: world.registry.close())
        return world

    def track(self, registry):
        self.addCleanup(registry.close)
        return registry

    def count(self, registry, table):
        return registry._query(f"SELECT COUNT(*) FROM {table}")[0][0]

    def built(self, *, consumed=False):
        world = self.world(outcome_dependency="direct_permitted")
        handle, state = world.prepared()
        scheduled = state.schedule(world.p, registry=world.registry, admission_handle=handle)
        if consumed:
            state.apply(
                world.p,
                world.script_direct(scheduled.receipts),
                registry=world.registry,
                admission_handle=handle,
            )
        world.registry.close()
        return world


class CorruptionAndSchemaRefusalTests(DurabilityBase):
    def test_tampered_stores_are_refused_and_never_recreated(self):
        cases = {
            "audit chain": (False, ["UPDATE audit SET kind = 'tampered' WHERE seq = 2"]),
            "receipt bytes": (False, ["UPDATE receipts SET issued_at = issued_at + 1"]),
            "bracket identity": (False, ["UPDATE brackets SET track = 'whole-campaign'"]),
            "seal tail deleted": (False, ["DELETE FROM seals WHERE sequence = 4"]),
            "clock high water": (False, ["UPDATE clock_mark SET high_water = 0"]),
            "status content": (
                False,
                [
                    "UPDATE status_observations SET generation = generation + 5"
                    " WHERE id = (SELECT MIN(id) FROM status_observations)"
                ],
            ),
            "admission stage": (False, ["UPDATE admissions SET stage = 'hybrid'"]),
            "recorded result": (False, ["UPDATE request_results SET result_ref = 'zzz'"]),
            "consumption deleted": (
                True,
                ["DELETE FROM consumptions WHERE rowid = (SELECT MIN(rowid) FROM consumptions)"],
            ),
            "schema object added": (False, ["CREATE TABLE extra (x INTEGER)"]),
            "schema column added": (False, ["ALTER TABLE meta ADD COLUMN extra TEXT"]),
            "foreign application id": (False, ["PRAGMA application_id = 1"]),
            # Schema 2 is current (it binds the versioned bracket codec). The unsupported
            # schema-1 identity and any other version are refused, never migrated.
            "unknown schema version": (False, ["PRAGMA user_version = 3"]),
            "previous schema version": (False, ["PRAGMA user_version = 1"]),
            "bracket codec metadata": (
                False,
                ["UPDATE meta SET value = 'hive-mind-os.bracket-state/v2' WHERE key = 'bracket_codec'"],
            ),
            "bracket codec metadata missing": (
                False,
                ["DELETE FROM meta WHERE key = 'bracket_codec'"],
            ),
            "versionless legacy bracket": (False, [replace_bracket(legacy_document())]),
            "unknown bracket version": (False, [replace_bracket(versioned_document(version=2))]),
            "mixed bracket version and legacy pair keys": (
                False,
                [replace_bracket(versioned_document(inconclusive={'["MB0", "MB1"]': 1}))],
            ),
            "duplicate bracket pairs": (
                False,
                [
                    replace_bracket(
                        versioned_document(
                            inconclusive=[
                                {"pair": ["MB0", "MB1"], "count": 1},
                                {"pair": ["MB0", "MB1"], "count": 1},
                            ]
                        )
                    )
                ],
            ),
        }
        for label, (consumed, statements) in cases.items():
            with self.subTest(label):
                world = self.built(consumed=consumed)
                raw(world.path, *statements)
                tampered = table_counts(world.path)
                with self.assertRaises(N30StoreError):
                    world.open_registry()
                with self.assertRaises(N30StoreError):  # still refused, still not replaced
                    world.open_registry()
                self.assertTrue(world.path.exists())
                # refusal performs no writes and never recreates the store
                self.assertEqual(table_counts(world.path), tampered)
                self.assertGreater(tampered["audit"], 0)

    def test_untouched_store_reopens_and_missing_or_foreign_files_are_never_created(self):
        world = self.built(consumed=True)
        self.track(world.open_registry())  # positive control: full verification passes
        missing = world.path.with_name("missing.sqlite")
        with self.assertRaises(N30StoreError):
            N30HostRegistry.open(
                missing,
                policy=world.policy,
                ports=HostPorts(),
                clock=world.clock,
            )
        self.assertFalse(missing.exists())
        garbage = world.path.with_name("garbage.sqlite")
        garbage.write_bytes(b"not a database")
        with self.assertRaises(N30StoreError):
            N30HostRegistry.open(
                garbage, policy=world.policy, ports=HostPorts(), clock=world.clock
            )
        self.assertEqual(garbage.read_bytes(), b"not a database")
        foreign = world.path.with_name("foreign.sqlite")
        raw(foreign, "CREATE TABLE something_else (x INTEGER)", "INSERT INTO something_else VALUES (7)")
        with self.assertRaises(N30StoreError):
            N30HostRegistry.open(
                foreign, policy=world.policy, ports=HostPorts(), clock=world.clock
            )
        connection = sqlite3.connect(foreign)
        try:
            self.assertEqual(
                connection.execute("SELECT x FROM something_else").fetchall(), [(7,)]
            )
        finally:
            connection.close()
        with self.assertRaises(N30StoreError):  # never create over an existing store
            N30HostRegistry.create(
                world.path, policy=world.policy, ports=HostPorts(), clock=world.clock
            )
        with self.assertRaises(N30StoreError):  # network filesystems are unsupported
            N30HostRegistry.create(
                "\\\\host\\share\\n30.sqlite",
                policy=world.policy,
                ports=HostPorts(),
                clock=world.clock,
            )

    def test_store_is_wal_full_with_foreign_keys_and_bounded_busy_timeout(self):
        world = self.world()
        connection = world.registry._conn
        self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
        self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)
        self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 2000)
        with self.assertRaises(sqlite3.IntegrityError):  # foreign keys are enforced
            connection.execute(
                "INSERT INTO brackets VALUES ('x', 'sha256:" + "0" * 64 + "', 'p', 'original', 't')"
            )


class SubprocessCrashTests(DurabilityBase):
    def run_child(self, directory, phase, point):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, (str(ROOT / "src"), str(ROOT), environment.get("PYTHONPATH", "")))
        )
        return subprocess.run(
            [sys.executable, "-c", CHILD, str(directory), phase, point],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=240,
        )

    def crashed(self, phase, point):
        world = self.world(outcome_dependency="direct_permitted")
        world.prepared()
        world.registry.close()
        process = self.run_child(world.directory, phase, point)
        self.assertEqual(process.returncode, 17, process.stderr)
        registry = world.reopen()  # full verification after the crash
        handle = world.admit()
        state = registry.recover_bracket(
            handle, world.p.protocol_digest, "original", "builder-component"
        )
        return world, registry, handle, state

    def test_crash_before_issuance_commit_leaves_nothing_and_service_continues(self):
        world, registry, handle, state = self.crashed("issue", "pre_commit:issue_round")
        self.assertEqual(self.count(registry, "issuances"), 0)
        self.assertEqual(self.count(registry, "receipts"), 0)
        scheduled = state.schedule(world.p, registry=registry, admission_handle=handle)
        self.assertEqual(len(scheduled.receipts), 2)
        self.assertEqual(self.count(registry, "issuances"), 1)

    def test_crash_after_issuance_commit_recovers_one_set_by_request_digest(self):
        world, registry, handle, state = self.crashed("issue", "post_commit:issue_round")
        self.assertEqual(self.count(registry, "issuances"), 1)
        self.assertEqual(self.count(registry, "receipts"), 2)
        again = state.schedule(world.p, registry=registry, admission_handle=handle)
        recovered = registry.recover(
            handle, issue_request_digest(tuple(r.plan for r in again.receipts))
        )
        self.assertEqual(
            [r.receipt_digest for r in recovered.receipts],
            [r.receipt_digest for r in again.receipts],
        )
        self.assertEqual(self.count(registry, "issuances"), 1)  # no duplicate tokens
        self.assertEqual({r.issued_at for r in again.receipts}, {20})

    def test_crash_before_consumption_commit_is_all_or_none(self):
        world, registry, handle, state = self.crashed("consume", "pre_commit:consume_round")
        self.assertEqual(self.count(registry, "consumptions"), 0)
        self.assertEqual(self.count(registry, "bracket_versions"), 1)
        scheduled = state.schedule(world.p, registry=registry, admission_handle=handle)
        advanced = state.apply(
            world.p,
            world.script_direct(scheduled.receipts),
            registry=registry,
            admission_handle=handle,
        )
        self.assertIsInstance(advanced, BracketState)
        self.assertEqual(self.count(registry, "consumptions"), 2)

    def test_crash_after_consumption_commit_recovers_the_recorded_result_once(self):
        world, registry, handle, state = self.crashed("consume", "post_commit:consume_round")
        self.assertEqual(self.count(registry, "consumptions"), 2)
        self.assertEqual(self.count(registry, "bracket_versions"), 2)
        request_digest = Path(world.directory, "request.txt").read_text()
        recovered = registry.recover(handle, request_digest)
        self.assertTrue(recovered.current)
        self.assertEqual(recovered.kind, "consume_round")
        self.assertIs(recovered.state.opaque_handle, state.opaque_handle)
        # the round is consumed exactly once; the next round starts from the successor
        follow = recovered.state.schedule(world.p, registry=registry, admission_handle=handle)
        self.assertEqual({r.issued_at for r in follow.receipts}, {20})
        self.assertEqual(self.count(registry, "consumptions"), 2)
        with self.assertRaises(CampaignMetricsError):
            registry.recover(handle, canonical_digest("never recorded"))


class TwoConnectionRaceTests(DurabilityBase):
    def race(self, calls):
        barrier = threading.Barrier(len(calls))
        outcomes = [None] * len(calls)

        def run(index, call):
            barrier.wait()
            try:
                outcomes[index] = call()
            except BaseException as error:
                outcomes[index] = error

        threads = [
            threading.Thread(target=run, args=(index, call)) for index, call in enumerate(calls)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return outcomes

    def test_independent_connections_race_issuance_and_consumption_to_one_result(self):
        world = self.world(outcome_dependency="direct_permitted")
        handle_a, state_a = world.prepared()
        registry_a = world.registry
        registry_b = self.track(world.open_registry())
        handle_b = world.admit(registry_b)
        pd = world.p.protocol_digest
        state_b = registry_b.recover_bracket(handle_b, pd, "original", "builder-component")

        issued = self.race(
            [
                lambda: state_a.schedule(world.p, registry=registry_a, admission_handle=handle_a),
                lambda: state_b.schedule(world.p, registry=registry_b, admission_handle=handle_b),
            ]
        )
        for outcome in issued:
            self.assertNotIsInstance(outcome, BaseException, repr(outcome))
        digests = [[r.receipt_digest for r in outcome.receipts] for outcome in issued]
        self.assertEqual(digests[0], digests[1])
        self.assertEqual(self.count(registry_a, "issuances"), 1)

        results_a = world.script_direct(issued[0].receipts)
        results_b = world.script_direct(issued[1].receipts)
        applied = self.race(
            [
                lambda: state_a.apply(
                    world.p, results_a, registry=registry_a, admission_handle=handle_a
                ),
                lambda: state_b.apply(
                    world.p, results_b, registry=registry_b, admission_handle=handle_b
                ),
            ]
        )
        winners = [item for item in applied if isinstance(item, BracketState)]
        losers = [item for item in applied if not isinstance(item, BracketState)]
        self.assertEqual(len(winners), 1, applied)
        self.assertTrue(all(isinstance(item, CampaignMetricsError) for item in losers), losers)
        self.assertEqual(self.count(registry_a, "consumptions"), 2)
        self.assertEqual(self.count(registry_b, "bracket_versions"), 2)
        world.reopen()  # every digest and lineage still verifies

    def test_independent_connections_race_seal_append_to_one_history(self):
        world = self.world()
        handle_a, _ = world.prepared()
        registry_a = world.registry
        registry_b = self.track(world.open_registry())
        handle_b = world.admit(registry_b)
        use = AdmissionUse(world.p.protocol_digest, "original", "seal")
        history = canonical_digest(registry_a.resolve(handle_a, use).seal_history)
        first = seal_for(world.p, world.evidence, "MC0", 5, canonical_digest("candidate-a"), 15)
        second = seal_for(world.p, world.evidence, "MC1", 5, canonical_digest("candidate-b"), 16)
        outcomes = self.race(
            [
                lambda: registry_a.append_seals(handle_a, history, 20, (first,)),
                lambda: registry_b.append_seals(handle_b, history, 20, (second,)),
            ]
        )
        failures = [item for item in outcomes if isinstance(item, BaseException)]
        self.assertEqual(len(failures), 1, outcomes)
        self.assertIsInstance(failures[0], CampaignMetricsError)
        self.assertEqual(self.count(registry_a, "seals"), 5)
        world.reopen()


if __name__ == "__main__":
    unittest.main()
