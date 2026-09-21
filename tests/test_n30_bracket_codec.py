"""R3: the deliberate, versioned bracket/transition identity (ADR-094).

Legacy values below are the Curator's retained evidence for the *removed* versionless
bracket identity (``n30-curator-v1/lifecycle-digest-results/digest-results.json``): the
old function over the exact snapshot in ``COMMON`` produced two seed-dependent digests for
the nonempty history (A for hash seeds 0,2,3,7 and B for 1,4,5,6). They are pinned here as
losing evidence, never as an accepted identity. New pinned values are intentionally absent:
the new digests are asserted by stability and by difference, and the first independent run
should record them as fresh goldens.
"""

import json
import os
import subprocess
import sys
import unittest
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

from hive_mind_os.campaign_metrics import (
    BRACKET_CODEC_DOMAIN,
    BRACKET_CODEC_ID,
    BRACKET_CODEC_VERSION,
    BracketSnapshot,
    BracketTransition,
    CampaignMetricsError,
    bracket_from_document,
    canonical_digest,
    canonical_document,
    transition_after_round,
)
from hive_mind_os.n30_host_registry import N30StoreError, decode_bracket
from tests.test_campaign_metrics import lease, protocol, seal_for, stage_evidence
from tests.test_n30_host_registry import N30Base

ROOT = Path(__file__).resolve().parents[1]
LEGACY_EMPTY = "sha256:c49319d05d430073ffb443c6868b2e8c00b232fd3c4a76c9e3276755e71050dd"
LEGACY_A = "sha256:cc39e337ad6f68d2a1687ba2cdeb0ce25e44b82dc89ba639993a1bd48f3c9b52"
LEGACY_B = "sha256:4b2790283b385828bd71dfaa53e1f7956aae1be9be0f0464ac475dcdf387c540"
LEGACY_NONEMPTY_BY_SEED = {
    "0": LEGACY_A,
    "1": LEGACY_B,
    "2": LEGACY_A,
    "3": LEGACY_A,
    "4": LEGACY_B,
    "5": LEGACY_B,
    "6": LEGACY_B,
    "7": LEGACY_A,
}
COMMON = {
    "protocol_digest": "sha256:" + "1" * 64,
    "admission_digest": "sha256:" + "2" * 64,
    "stage": "original",
    "track": "builder-component",
}

CHILD = """
import json
from hive_mind_os.campaign_metrics import BracketSnapshot, BracketTransition, canonical_digest

common = dict(
    protocol_digest='sha256:' + '1' * 64,
    admission_digest='sha256:' + '2' * 64,
    stage='original',
    track='builder-component',
)
empty = BracketSnapshot(**common)
nonempty = BracketSnapshot(**common, round_number=1, inconclusive={frozenset({'MB0', 'MB1'}): 1})
transition = BracketTransition(1, {}, {}, {frozenset({'MB0', 'MB1'}): 1}, frozenset(), None, frozenset())
print(json.dumps({
    'legacy_empty': canonical_digest(empty.legacy_document()),
    'legacy_nonempty': canonical_digest(nonempty.legacy_document()),
    'empty': empty.bracket_digest,
    'nonempty': nonempty.bracket_digest,
    'transition': canonical_digest(transition),
}))
"""

REOPEN_CHILD = """
import sys
from tests.n30_synthetic import World

w = World(sys.argv[1], create=False, outcome_dependency='direct_permitted')
handle = w.admit()
state = w.registry.recover_bracket(handle, w.p.protocol_digest, 'original', 'builder-component')
print(w.registry.resolve_bracket(handle, state.opaque_handle, w.p.protocol_digest, 'schedule').bracket_digest)
w.registry.close()
"""


def legacy_digest(value):
    """Independent re-implementation of the historical canonical digest (str(key))."""

    def plain(item):
        if hasattr(item, "to_document"):
            return plain(item.to_document())
        if isinstance(item, Mapping):
            return {str(key): plain(val) for key, val in item.items()}
        if isinstance(item, (tuple, list, set, frozenset)):
            values = [plain(val) for val in item]
            return (
                sorted(values, key=lambda val: json.dumps(val, sort_keys=True))
                if isinstance(item, (set, frozenset))
                else values
            )
        return item

    encoded = json.dumps(plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()


def child_environment(seed):
    environment = dict(os.environ, PYTHONHASHSEED=seed)
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(ROOT / "src"), str(ROOT), environment.get("PYTHONPATH", "")))
    )
    return environment


def nonempty():
    return BracketSnapshot(
        **COMMON, round_number=1, inconclusive={frozenset({"MB0", "MB1"}): 1}
    )


class BracketCodecIdentityTests(unittest.TestCase):
    def test_versioned_document_names_domain_type_version_and_typed_pairs(self):
        document = nonempty().to_document()
        self.assertEqual(document["domain"], BRACKET_CODEC_DOMAIN)
        self.assertEqual(document["type"], "bracket-snapshot")
        self.assertEqual(document["version"], BRACKET_CODEC_VERSION)
        self.assertEqual(BRACKET_CODEC_ID, f"{BRACKET_CODEC_DOMAIN}/v{BRACKET_CODEC_VERSION}")
        self.assertEqual(document["inconclusive"], [{"pair": ["MB0", "MB1"], "count": 1}])
        transition = BracketTransition(
            1, {}, {}, {frozenset({"MB1", "MB0"}): 2}, frozenset(), None, frozenset()
        ).to_document()
        self.assertEqual(transition["type"], "bracket-transition")
        self.assertEqual(transition["inconclusive"], [{"pair": ["MB0", "MB1"], "count": 2}])
        # a snapshot and a transition can never share a preimage
        self.assertNotEqual(document["type"], transition["type"])

    def test_legacy_identity_is_retained_as_evidence_and_is_not_the_new_identity(self):
        empty = BracketSnapshot(**COMMON)
        self.assertEqual(canonical_digest(empty.legacy_document()), LEGACY_EMPTY)
        self.assertIn(
            canonical_digest(nonempty().legacy_document()), {LEGACY_A, LEGACY_B}
        )
        # Empty histories intentionally take a new digest: the version is in the preimage.
        self.assertNotEqual(empty.bracket_digest, LEGACY_EMPTY)
        self.assertNotIn(nonempty().bracket_digest, {LEGACY_A, LEGACY_B})
        self.assertEqual(canonical_digest(empty), empty.bracket_digest)

    def test_eight_hash_seeds_new_identity_is_stable_and_legacy_variants_are_pinned(self):
        results = {}
        for seed in LEGACY_NONEMPTY_BY_SEED:
            process = subprocess.run(
                [sys.executable, "-c", CHILD],
                env=child_environment(seed),
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            results[seed] = json.loads(process.stdout)
        for seed, value in results.items():  # the old evidence is reproduced, per seed
            self.assertEqual(value["legacy_empty"], LEGACY_EMPTY, seed)
            self.assertEqual(value["legacy_nonempty"], LEGACY_NONEMPTY_BY_SEED[seed], seed)
        self.assertEqual({v["legacy_nonempty"] for v in results.values()}, {LEGACY_A, LEGACY_B})
        for name in ("empty", "nonempty", "transition"):  # the new identity does not vary
            self.assertEqual(len({v[name] for v in results.values()}), 1, name)
        first = next(iter(results.values()))
        self.assertNotIn(first["nonempty"], {LEGACY_A, LEGACY_B})
        self.assertNotEqual(first["empty"], LEGACY_EMPTY)
        self.assertEqual(first["nonempty"], nonempty().bracket_digest)

    def test_new_codec_goldens_pin_full_preimages_and_digests(self):
        """Independent Curator goldens (n30-curator-remand1/additional-controls/
        new-codec-goldens.json), pinned with their complete preimages, not guessed hashes."""
        base = {
            "domain": "hive-mind-os.bracket-state",
            "version": 1,
        }
        snapshot_common = {
            "protocol_digest": COMMON["protocol_digest"],
            "admission_digest": COMMON["admission_digest"],
            "stage": "original",
            "track": "builder-component",
        }
        body = {"losses": {}, "byes": {}, "quarantined": [], "terminal": None,
                "applied_receipt_digests": []}
        pair = [{"pair": ["MB0", "MB1"], "count": 1}]
        goldens = {
            "empty": (
                BracketSnapshot(**COMMON),
                {**base, "type": "bracket-snapshot", **snapshot_common, "round_number": 0,
                 **body, "inconclusive": []},
                "sha256:63053dcdece5e6593334ceeb031408f3758f785b7a712d3a9ee16d648d71819a",
            ),
            "inconclusive": (
                nonempty(),
                {**base, "type": "bracket-snapshot", **snapshot_common, "round_number": 1,
                 **body, "inconclusive": pair},
                "sha256:ee1b9ffc099fa4e7958a0978b8484167fc3a1a6148f7c036d733958dfb3aa0c9",
            ),
            "transition": (
                BracketTransition(
                    1, {}, {}, {frozenset({"MB0", "MB1"}): 1}, frozenset(), None, frozenset()
                ),
                {**base, "type": "bracket-transition", "round_number": 1, **body,
                 "inconclusive": pair},
                "sha256:31ece3e842853d910faac48f615c52c5b0e20a376d9c4b97e55a4f6ee34f1fd0",
            ),
        }
        for name, (value, document, digest) in goldens.items():
            with self.subTest(name):
                self.assertEqual(json.loads(json.dumps(canonical_document(value))), document)
                self.assertEqual(canonical_digest(value), digest)
        self.assertEqual(goldens["empty"][0].bracket_digest, goldens["empty"][2])
        self.assertEqual(goldens["inconclusive"][0].bracket_digest, goldens["inconclusive"][2])

    def test_pair_order_equivalence_without_collisions(self):
        def digest(meetings):
            return BracketSnapshot(**COMMON, round_number=1, inconclusive=meetings).bracket_digest

        base = digest({frozenset(("MB0", "MB1")): 1})
        self.assertEqual(base, digest({frozenset(("MB1", "MB0")): 1}))
        both = digest({frozenset(("MB0", "MB1")): 1, frozenset(("MB2", "MB3")): 1})
        self.assertEqual(
            both, digest({frozenset(("MB3", "MB2")): 1, frozenset(("MB1", "MB0")): 1})
        )
        distinct = {
            base,
            both,
            digest({frozenset(("MB0", "MB1")): 2}),
            digest({frozenset(("MB0", "MB2")): 1}),
            digest({frozenset(("MB0", "MB1")): 1, frozenset(("MB2", "MB3")): 2}),
            digest({frozenset(("MB0", "MB2")): 1, frozenset(("MB1", "MB3")): 1}),
            # strings that look like JSON/keys can never be read as a different pair
            digest({frozenset(('a","b', "c")): 1}),
            digest({frozenset(("a", 'b","c')): 1}),
            digest({frozenset(('["MB0", "MB1"]', "MB2")): 1}),
        }
        self.assertEqual(len(distinct), 9)

    def test_unrelated_campaign_documents_keep_their_legacy_digests(self):
        p = protocol()
        evidence = stage_evidence(p, "original")
        seal = seal_for(p, evidence, "MB0", 1, canonical_digest("candidate"), 11)
        for label, value in (
            ("protocol", p),
            ("stage evidence", evidence),
            ("lease", lease(p, "original")),
            ("seal", seal),
            ("plain mapping", {"a": 1, "b": [1, 2], "c": {"d": None}}),
            ("non-str keys", {1: "x", 2: "y"}),
            ("frozenset key (same process)", {frozenset(("a", "b")): 1}),
            ("legacy bracket document", nonempty().legacy_document()),
        ):
            with self.subTest(label):
                self.assertEqual(canonical_digest(value), legacy_digest(value))
        # ``canonical_document`` restored ``str(key)``; it does not claim generic determinism
        key = next(iter(canonical_document({frozenset(("a", "b")): 1})))
        self.assertEqual(key, str(frozenset(("a", "b"))))


class BracketDecoderStrictnessTests(unittest.TestCase):
    def document(self):
        return json.loads(json.dumps(canonical_document(nonempty())))

    def test_round_trip_is_exact(self):
        snapshot = nonempty()
        self.assertEqual(bracket_from_document(self.document()), snapshot)
        self.assertEqual(
            bracket_from_document(self.document()).bracket_digest, snapshot.bracket_digest
        )
        self.assertEqual(decode_bracket(self.document()), snapshot)

    def test_malformed_unknown_versionless_and_mixed_documents_reject(self):
        def edit(**changes):
            document = self.document()
            document.update(changes)
            return document

        def without(name):
            document = self.document()
            del document[name]
            return document

        legacy = json.loads(json.dumps(canonical_document(nonempty().legacy_document())))
        good_pairs = [{"pair": ["MB0", "MB1"], "count": 1}]
        cases = {
            "legacy versionless": legacy,
            "empty legacy history": json.loads(
                json.dumps(canonical_document(BracketSnapshot(**COMMON).legacy_document()))
            ),
            "missing version": without("version"),
            "missing domain": without("domain"),
            "unknown version": edit(version=2),
            "string version": edit(version="1"),
            "boolean version": edit(version=True),
            "unknown domain": edit(domain="other.bracket-state"),
            "wrong type": edit(type="bracket-transition"),
            "extra field": edit(extra=1),
            "missing field": without("terminal"),
            "mixed: version plus legacy json-key mapping": edit(
                inconclusive={'["MB0", "MB1"]': 1}
            ),
            "pairs not a list": edit(inconclusive="x"),
            "entry not an object": edit(inconclusive=[["MB0", "MB1", 1]]),
            "duplicate pair": edit(inconclusive=good_pairs + good_pairs),
            "duplicate pair reordered": edit(
                inconclusive=[{"pair": ["MB0", "MB1"], "count": 1}, {"pair": ["MB0", "MB1"], "count": 2}]
            ),
            "unsorted entries": edit(
                inconclusive=[
                    {"pair": ["MB2", "MB3"], "count": 1},
                    {"pair": ["MB0", "MB1"], "count": 1},
                ]
            ),
            "unsorted pair": edit(inconclusive=[{"pair": ["MB1", "MB0"], "count": 1}]),
            "identical pair members": edit(inconclusive=[{"pair": ["MB0", "MB0"], "count": 1}]),
            "three member pair": edit(inconclusive=[{"pair": ["MB0", "MB1", "MB2"], "count": 1}]),
            "non string member": edit(inconclusive=[{"pair": ["MB0", 1], "count": 1}]),
            "negative count": edit(inconclusive=[{"pair": ["MB0", "MB1"], "count": -1}]),
            "boolean count": edit(inconclusive=[{"pair": ["MB0", "MB1"], "count": True}]),
            "extra entry field": edit(
                inconclusive=[{"pair": ["MB0", "MB1"], "count": 1, "note": "x"}]
            ),
            "unsorted quarantine": edit(quarantined=["MB1", "MB0"]),
            "duplicate quarantine": edit(quarantined=["MB0", "MB0"]),
            "bad terminal type": edit(terminal=3),
            "losses not an object": edit(losses=[["MB0", 1]]),
            "not an object": [],
        }
        for label, document in cases.items():
            with self.subTest(label):
                with self.assertRaises(CampaignMetricsError):
                    bracket_from_document(document)
                with self.assertRaises(N30StoreError):
                    decode_bracket(document)


class RegistryCodecLineageTests(N30Base):
    def test_reopen_cas_and_receipt_lineage_use_one_versioned_codec(self):
        w = self.world(outcome_dependency="direct_permitted")
        handle, state = w.prepared()
        first = self.schedule(w, handle, state)
        initial = self.bracket(w, handle, state)
        advanced = self.apply(w, handle, state, w.script_direct(first.receipts))  # DRAW
        snapshot = self.bracket(w, handle, advanced)
        self.assertTrue(snapshot.inconclusive)

        rows = w.registry._query(
            "SELECT canonical, bracket_digest FROM bracket_versions ORDER BY version"
        )
        self.assertEqual(len(rows), 2)
        for data, digest in rows:
            document = json.loads(bytes(data))
            self.assertEqual(document["domain"], BRACKET_CODEC_DOMAIN)
            self.assertEqual(document["version"], BRACKET_CODEC_VERSION)
            self.assertEqual(bracket_from_document(document).bracket_digest, digest)
        self.assertEqual(
            w.registry._query("SELECT value FROM meta WHERE key = 'bracket_codec'"),
            [(BRACKET_CODEC_ID,)],
        )
        self.assertEqual(rows[0][1], initial.bracket_digest)
        self.assertEqual(rows[1][1], snapshot.bracket_digest)

        second = advanced.schedule(
            w.p, registry=w.registry, admission_handle=handle
        )  # plans and receipts of the next round bind the versioned digest
        self.assertTrue(second.receipts)
        self.assertTrue(
            all(r.plan.bracket_digest == snapshot.bracket_digest for r in second.receipts)
        )
        registry = w.reopen()  # full lineage verification with the same codec
        handle2 = w.admit()
        state2 = registry.recover_bracket(
            handle2, w.p.protocol_digest, "original", "builder-component"
        )
        current = registry.resolve_bracket(handle2, state2.opaque_handle, w.p.protocol_digest, "schedule")
        self.assertEqual(current.bracket_digest, snapshot.bracket_digest)
        stale = BracketTransition(
            current.round_number, current.losses, current.byes, current.inconclusive,
            current.quarantined, "max_rounds", current.applied_receipt_digests,
        )
        with self.assertRaises(CampaignMetricsError):  # CAS against the retired version-0 digest
            registry.commit_bracket(handle2, state2.opaque_handle, initial.bracket_digest, stale)
        # the recomputed successor uses the same codec as the stored one
        bracket0 = initial
        expected = transition_after_round(w.p, bracket0, w.script_direct(first.receipts))
        self.assertEqual(
            canonical_digest(expected),
            canonical_digest(
                BracketTransition(
                    snapshot.round_number, snapshot.losses, snapshot.byes, snapshot.inconclusive,
                    snapshot.quarantined, snapshot.terminal, snapshot.applied_receipt_digests,
                )
            ),
        )

    def test_reopen_verifies_identically_under_different_hash_seeds(self):
        w = self.world(outcome_dependency="direct_permitted")
        handle, state = w.prepared()
        scheduled = self.schedule(w, handle, state)
        advanced = self.apply(w, handle, state, w.script_direct(scheduled.receipts))
        expected = self.bracket(w, handle, advanced).bracket_digest
        w.registry.close()
        for seed in ("0", "1", "7"):
            with self.subTest(seed):
                process = subprocess.run(
                    [sys.executable, "-c", REOPEN_CHILD, str(w.directory)],
                    env=child_environment(seed),
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(process.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
