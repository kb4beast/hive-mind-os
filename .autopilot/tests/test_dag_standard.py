"""Unit tests for the generic DAG round compiler and authoring-standard lint.

Every test here builds a synthetic in-memory plan. The module under test must be
usable on any repository's ``plan.json``, so no test may depend on this
repository's own plan content -- and, since the tool is pointed at repositories
in any language, no ecosystem may be represented only by Python.
"""

from __future__ import annotations

import io
import json
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha1
from pathlib import Path
from typing import Any

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from dag_standard import (  # noqa: E402
    DEFAULT_MAX_SESSIONS,
    ROOT_MANIFESTS,
    DagStandardError,
    Finding,
    PlanGraph,
    compile_rounds,
    dispatch_command_prefix,
    lint_exit_code,
    lint_plan,
    load_plan_graph,
)
from durable_controller import digest_json  # noqa: E402

TEST_PREFIX = "python bin/autopilot.py --repo-root . dispatch"

_HISTORICAL_STANDARD_BLOB = "70e43b0a8078a303d44c0109b8dd218a948258c2"
_HISTORICAL_SEALED_PLAN_BLOB = "ee7ec9f2756fcff2b7010238d7064d017c4df7af"
_HISTORICAL_V1_BLOBS = {
    "README.md": "7fe726912358e62bb557a0dcf043ad6e69629302",
    "generate_plan.py": "b61407bb871e17e07da060ee4796bae05957afa6",
    "manifest.json": "e4e0d24c90c0e9b9f13e15fb90b9bd31a75e3bf5",
    "specs_a.py": "0adb16c3de4b7f78739aed2d00b64eb8a549f4f8",
    "specs_b.py": "0ed6d109bdf09037c41db56f25ca155b4179b2d4",
    "verify_plan.py": "4078803e652ca3be1a38baafb0b186be9420d848",
}


def node(node_id: str, **overrides: Any) -> dict[str, Any]:
    """A complete, contract-valid synthetic node."""

    document: dict[str, Any] = {
        "id": node_id,
        "objective": f"Deliver the {node_id} unit of work.",
        "acceptance_criteria": [f"{node_id} tests pass deterministically."],
        "dependencies": [],
        "parallel_safe": True,
        "critical_path_importance": 50,
        "downstream_unlock_value": 50,
        "read_scope": [f"docs/{node_id}.md"],
        "write_scope": [f"docs/{node_id}.md"],
        "file_locks": [f"docs/{node_id}.md"],
        "forbidden_scope": ["docs/PROTECTED.md"],
        "semantic_locks": [f"{node_id}-lock"],
        "required_tests": [f"{node_id}-tests"],
        "stopping_condition": "Acceptance criteria are met and evidence is retained.",
        "rollback": "Revert the node commit.",
    }
    document.update(overrides)
    return document


def graph_of(*nodes: dict[str, Any]) -> PlanGraph:
    return PlanGraph(nodes)


def sealed_document(
    nodes: list[dict[str, Any]], **plan_fields: Any
) -> dict[str, Any]:
    """Build exact v1 digest material without special-casing any contract field."""

    sealed_nodes = json.loads(json.dumps(nodes))
    for item in sealed_nodes:
        item["contract_digest"] = digest_json(item)
    document: dict[str, Any] = {
        "schema_version": 1,
        "nodes": sealed_nodes,
        **plan_fields,
    }
    document["plan_digest"] = digest_json(document)
    return document


def git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return sha1(b"blob " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()


def findings_of(graph: PlanGraph, check: str, **kwargs: Any) -> tuple[Finding, ...]:
    return tuple(item for item in lint_plan(graph, **kwargs) if item.check == check)


def subject_of(findings: tuple[Finding, ...], subject: str) -> Finding:
    for item in findings:
        if item.subject == subject:
            return item
    raise AssertionError(f"no finding for {subject!r} in {[i.subject for i in findings]}")


class HistoricalV1PreservationTests(unittest.TestCase):
    """V2 work must not silently invalidate the sealed v1 overlay evidence."""

    def test_original_standard_sealed_plan_and_entire_v1_overlay_are_preserved(self) -> None:
        root = Path(__file__).resolve().parents[2]
        standard = root / "docs" / "execution" / "DAG_AUTHORING_STANDARD.md"
        sealed_plan = root / ".autopilot" / "plan.json"
        v1 = root / "docs" / "execution" / "dags" / "generic-hive-mind-product-v1"
        observed = {
            path.relative_to(v1).as_posix(): git_blob_sha(path)
            for path in v1.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual(git_blob_sha(standard), _HISTORICAL_STANDARD_BLOB)
        self.assertEqual(git_blob_sha(sealed_plan), _HISTORICAL_SEALED_PLAN_BLOB)
        self.assertEqual(observed, _HISTORICAL_V1_BLOBS)


class PlanGraphTests(unittest.TestCase):
    def test_levels_use_longest_dependency_path(self) -> None:
        graph = graph_of(
            node("A"),
            node("B", dependencies=["A"]),
            node("C", dependencies=["A", "B"]),
        )
        self.assertEqual(graph.levels(), {0: ("A",), 1: ("B",), 2: ("C",)})
        self.assertEqual(graph.ancestors("C"), frozenset({"A", "B"}))

    def test_duplicate_ids_and_missing_dependencies_are_reported(self) -> None:
        graph = graph_of(node("A"), node("A"), node("B", dependencies=["GHOST"]))
        messages = [item.message for item in findings_of(graph, "graph-validity")]
        self.assertIn("node id A is declared more than once", messages)
        self.assertIn("B depends on unknown node GHOST", messages)

    def test_topology_preflight_rejects_unknown_and_duplicate_declarations(self) -> None:
        cases = (
            (
                "unknown raw dependency",
                graph_of(node("A", dependencies=["MISSING"])),
                "A depends on unknown node MISSING",
            ),
            (
                "duplicate declaration with invalid discarded metadata",
                graph_of(
                    node("A", durability_role="provider"),
                    node("A", durability_role="bogus"),
                ),
                "node id A is declared more than once",
            ),
            (
                "duplicate raw dependency",
                graph_of(node("PROVIDER"), node("A", dependencies=["PROVIDER", "PROVIDER"])),
                "A.dependencies declares PROVIDER more than once",
            ),
        )
        for label, graph, message in cases:
            with self.subTest(label=label):
                graph_findings = findings_of(graph, "graph-validity")
                self.assertIn(message, [item.message for item in graph_findings])
                with self.assertRaisesRegex(DagStandardError, message):
                    compile_rounds(graph, command_prefix=TEST_PREFIX)

    def test_malformed_dependency_values_are_graph_errors_and_never_schedule(self) -> None:
        cases = {
            "object": {"required": "PROVIDER"},
            "null": None,
            "scalar": "PROVIDER",
            "mixed": ["PROVIDER", 7],
        }
        for label, dependencies in cases.items():
            with self.subTest(label=label):
                graph = graph_of(node("A", dependencies=dependencies))
                findings = findings_of(graph, "graph-validity")
                self.assertEqual(len(findings), 1)
                self.assertIn("must be a list of non-empty string ids", findings[0].message)
                with self.assertRaisesRegex(
                    DagStandardError, "invalid plan topology; no rounds were emitted"
                ):
                    compile_rounds(graph, command_prefix=TEST_PREFIX)

    def test_cycle_is_an_error_and_level_checks_are_skipped(self) -> None:
        graph = graph_of(
            node("A", dependencies=["B"]),
            node("B", dependencies=["A"]),
        )
        findings = lint_plan(graph)
        cycles = [item for item in findings if "dependency cycle" in item.message]
        self.assertTrue(cycles)
        self.assertEqual(cycles[0].severity, "error")
        self.assertEqual(
            [item.check for item in findings if item.check != "graph-validity"], []
        )
        with self.assertRaises(DagStandardError):
            compile_rounds(graph)
        self.assertEqual(lint_exit_code(findings), 1)

    def test_conflict_predicate_is_the_dispatcher_predicate(self) -> None:
        graph = graph_of(
            node("A", file_locks=["src/app/**"]),
            node("B", file_locks=["src/app/thing.py"]),
            node("C", file_locks=["docs/C.md"], semantic_locks=["A-lock"]),
        )
        self.assertTrue(graph.conflicts("A", "B"))
        self.assertTrue(graph.conflicts("A", "C"))
        self.assertFalse(graph.conflicts("B", "C"))


class MalformedScopeTests(unittest.TestCase):
    """B2 regression: an unanchored lock pattern used to kill both commands.

    ``controller._scope_static_prefix`` raises ``ValueError`` for any pattern
    whose first character is a wildcard, because no repository-relative prefix
    survives. ``**/*.py`` and ``*.md`` are idiomatic; both crashed the tool.
    """

    def test_unanchored_lock_pattern_raises_inside_the_reused_predicate(self) -> None:
        from controller import scopes_overlap

        for pattern in ("**/*.py", "*.md", "*/generated/**"):
            with self.assertRaises(ValueError):
                scopes_overlap(pattern, "src/app/thing.py")

    def test_unanchored_lock_pattern_becomes_a_finding_not_a_traceback(self) -> None:
        graph = graph_of(
            node("ALPHA", file_locks=["**/*.py"], write_scope=["src/pkg/alpha.py"]),
            node("BETA", file_locks=["src/pkg/beta.py"], write_scope=["src/pkg/beta.py"]),
        )
        # Neither command may raise.
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        findings = findings_of(graph, "scope-syntax")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[0].nodes, ("ALPHA",))
        self.assertEqual(findings[0].subject, "**/*.py")
        self.assertIn("file_locks", findings[0].message)
        self.assertIn("static prefix", findings[0].fix)
        # A pattern the tool cannot compare is treated as conflicting, never as
        # silently disjoint.
        self.assertTrue(graph.conflicts("ALPHA", "BETA"))
        self.assertEqual([item.nodes for item in rounds], [("ALPHA",), ("BETA",)])

    def test_absolute_and_traversing_scopes_are_reported(self) -> None:
        graph = graph_of(
            node("ALPHA", write_scope=["/etc/passwd"], file_locks=["docs/ALPHA.md"]),
            node("BETA", write_scope=["../outside/thing.go"], file_locks=["docs/BETA.md"]),
        )
        findings = findings_of(graph, "scope-syntax")
        self.assertEqual(
            {item.subject for item in findings}, {"/etc/passwd", "../outside/thing.go"}
        )
        self.assertTrue(all(item.severity == "error" for item in findings))

    def test_the_cli_survives_a_malformed_scope(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "nodes": [
                            node("ALPHA", file_locks=["**/*.py"]),
                            node("BETA"),
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                rounds_code = autopilot.main(
                    ["--repo-root", str(root), "dag-rounds", "--plan", str(plan)]
                )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                lint_code = autopilot.main(
                    ["--repo-root", str(root), "dag-lint", "--plan", str(plan), "--json"]
                )
        self.assertEqual(rounds_code, 0)
        self.assertEqual(lint_code, 1)
        report = json.loads(buffer.getvalue())
        self.assertEqual(
            [item["check"] for item in report["findings"] if item["check"] == "scope-syntax"],
            ["scope-syntax"],
        )


class WriteScopeOverlapTests(unittest.TestCase):
    """B4: identical ``write_scope`` entries used to produce zero findings."""

    def test_identical_write_scope_is_an_error_without_any_file_locks(self) -> None:
        graph = graph_of(
            node("ALPHA", write_scope=["svc/core/config.go"], file_locks=[]),
            node("BETA", write_scope=["svc/core/config.go"], file_locks=[]),
        )
        findings = findings_of(graph, "write-scope-overlap")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[0].nodes, ("ALPHA", "BETA"))
        self.assertIn("svc/core/config.go", findings[0].message)
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_overlapping_nodes_are_not_packed_into_one_round(self) -> None:
        graph = graph_of(
            node("ALPHA", write_scope=["svc/core/config.go"], file_locks=[]),
            node("BETA", write_scope=["svc/core/config.go"], file_locks=[]),
        )
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        self.assertEqual([item.nodes for item in rounds], [("ALPHA",), ("BETA",)])

    def test_a_glob_scope_overlapping_a_literal_scope_is_reported(self) -> None:
        graph = graph_of(
            node("OWNER", write_scope=["svc/core/**"], file_locks=[]),
            node("OTHER", write_scope=["svc/core/config.go"], file_locks=[]),
        )
        findings = findings_of(graph, "write-scope-overlap")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].nodes, ("OTHER", "OWNER"))

    def test_different_levels_are_allowed_to_touch_the_same_file(self) -> None:
        graph = graph_of(
            node("FIRST", write_scope=["svc/core/config.go"], file_locks=[]),
            node(
                "SECOND",
                dependencies=["FIRST"],
                write_scope=["svc/core/config.go"],
                file_locks=[],
            ),
        )
        self.assertEqual(findings_of(graph, "write-scope-overlap"), ())


class ScaffoldCollisionTests(unittest.TestCase):
    def test_same_level_nodes_implying_one_package_init_is_an_error(self) -> None:
        graph = graph_of(
            node(
                "ALPHA",
                write_scope=["tests/suite/test_alpha.py"],
                file_locks=["tests/suite/test_alpha.py"],
            ),
            node(
                "BETA",
                write_scope=["tests/suite/test_beta.py"],
                file_locks=["tests/suite/test_beta.py"],
            ),
        )
        findings = findings_of(graph, "scaffold-collision")
        subjects = {item.subject: item for item in findings}
        self.assertIn("tests/suite/__init__.py", subjects)
        self.assertIn("tests/suite/conftest.py", subjects)
        collision = subjects["tests/suite/__init__.py"]
        self.assertEqual(collision.severity, "error")
        self.assertEqual(collision.nodes, ("ALPHA", "BETA"))
        self.assertIn("named in no node's write_scope", collision.message)
        self.assertIn("exactly one owner", collision.fix)
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_exactly_one_named_owner_clears_the_collision(self) -> None:
        graph = graph_of(
            node(
                "ALPHA",
                write_scope=[
                    "tests/suite/test_alpha.py",
                    "tests/suite/__init__.py",
                    "tests/suite/conftest.py",
                ],
                file_locks=["tests/suite/**"],
            ),
            node(
                "BETA",
                dependencies=["ALPHA"],
                write_scope=["tests/suite/test_beta.py"],
                file_locks=["tests/suite/test_beta.py"],
            ),
        )
        self.assertEqual(findings_of(graph, "scaffold-collision"), ())

    def test_glob_coverage_alone_is_permission_not_ownership(self) -> None:
        graph = graph_of(
            node("OWNER", write_scope=["tests/suite/**"], file_locks=["tests/suite/**"]),
            node(
                "ALPHA",
                dependencies=["OWNER"],
                write_scope=["tests/suite/test_alpha.py"],
                file_locks=["tests/suite/test_alpha.py"],
            ),
            node(
                "BETA",
                dependencies=["OWNER"],
                write_scope=["tests/suite/test_beta.py"],
                file_locks=["tests/suite/test_beta.py"],
            ),
        )
        collision = subject_of(
            findings_of(graph, "scaffold-collision"), "tests/suite/__init__.py"
        )
        self.assertEqual(collision.severity, "error")
        self.assertIn("permission, not obligation", collision.message)
        self.assertIn("OWNER", collision.message)

    def test_single_implier_outside_its_scope_is_a_warning(self) -> None:
        graph = graph_of(
            node(
                "ALPHA",
                write_scope=["src/pkg/alpha.py"],
                file_locks=["src/pkg/alpha.py"],
            ),
        )
        findings = findings_of(graph, "scaffold-collision")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(findings[0].subject, "src/pkg/__init__.py")

    def test_earlier_level_establishes_the_scaffold(self) -> None:
        graph = graph_of(
            node(
                "ROOT",
                write_scope=["src/pkg/root.py", "src/pkg/__init__.py"],
                file_locks=["src/pkg/**"],
            ),
            node(
                "ALPHA",
                dependencies=["ROOT"],
                write_scope=["src/pkg/alpha.py"],
                file_locks=["src/pkg/alpha.py"],
            ),
            node(
                "BETA",
                dependencies=["ROOT"],
                write_scope=["src/pkg/beta.py"],
                file_locks=["src/pkg/beta.py"],
            ),
        )
        self.assertEqual(findings_of(graph, "scaffold-collision"), ())

    def test_explicitly_forbidding_the_scaffold_clears_the_collision(self) -> None:
        graph = graph_of(
            node(
                "ALPHA",
                write_scope=["tests/suite/test_alpha.py"],
                file_locks=["tests/suite/test_alpha.py"],
                forbidden_scope=["tests/suite/__init__.py", "tests/suite/conftest.py"],
            ),
            node(
                "BETA",
                write_scope=["tests/suite/test_beta.py"],
                file_locks=["tests/suite/test_beta.py"],
                forbidden_scope=["tests/suite/__init__.py", "tests/suite/conftest.py"],
            ),
        )
        self.assertEqual(findings_of(graph, "scaffold-collision"), ())

    def test_new_top_level_source_root_implies_root_manifest(self) -> None:
        graph = graph_of(
            node(
                "ALPHA",
                write_scope=["service/pkg/alpha.py", "service/pkg/__init__.py"],
                file_locks=["service/pkg/alpha.py", "service/pkg/__init__.py"],
            ),
            node(
                "BETA",
                write_scope=["service/other/beta.py", "service/other/__init__.py"],
                file_locks=["service/other/beta.py", "service/other/__init__.py"],
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            manifest = [
                item
                for item in lint_plan(graph, repo_root=root)
                if item.subject == "pyproject.toml"
            ]
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0].severity, "warning")
        self.assertEqual(manifest[0].nodes, ("ALPHA", "BETA"))

    def test_root_manifests_are_reachable_for_a_non_python_ecosystem(self) -> None:
        """B1: ``ROOT_MANIFESTS`` used to be dead code for everything but Python."""

        self.assertIn("go.mod", ROOT_MANIFESTS)
        self.assertIn("Cargo.toml", ROOT_MANIFESTS)
        self.assertIn("package.json", ROOT_MANIFESTS)
        graph = graph_of(
            node("ALPHA", write_scope=["service/store/reader.go"], file_locks=[]),
            node("BETA", write_scope=["service/queue/writer.go"], file_locks=[]),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            manifests = [
                item.subject
                for item in lint_plan(graph, repo_root=root)
                if item.check == "scaffold-collision" and "." in item.subject
            ]
        # The Go manifest is implied; the unrelated Python one is not.
        self.assertIn("go.mod", manifests)
        self.assertNotIn("pyproject.toml", manifests)


class EcosystemContentionTests(unittest.TestCase):
    """B1/B9: the primary rule must protect every ecosystem, not just Python.

    Each case asserts the contention is *detected* -- and, where the ecosystem is
    in the table, that the specific shared artifact is named.
    """

    @staticmethod
    def _two_creators(first_path: str, second_path: str) -> PlanGraph:
        return graph_of(
            node("ALPHA", write_scope=[first_path], file_locks=[first_path]),
            node("BETA", write_scope=[second_path], file_locks=[second_path]),
        )

    def test_typescript_barrel_is_named(self) -> None:
        graph = self._two_creators("src/api/users.ts", "src/api/orders.ts")
        finding = subject_of(findings_of(graph, "scaffold-collision"), "src/api/index.ts")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(finding.nodes, ("ALPHA", "BETA"))
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_javascript_barrel_is_named(self) -> None:
        graph = self._two_creators("web/widgets/card.jsx", "web/widgets/list.js")
        subjects = {item.subject for item in findings_of(graph, "scaffold-collision")}
        self.assertIn("web/widgets/index.js", subjects)
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_rust_module_file_is_named(self) -> None:
        graph = self._two_creators("src/engine/lexer.rs", "src/engine/parser.rs")
        finding = subject_of(findings_of(graph, "scaffold-collision"), "src/engine/mod.rs")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_a_rust_workspace_crate_root_is_not_given_a_fake_mod_file(self) -> None:
        """``mod.rs`` exists inside a crate source root, never above one.

        In a Cargo workspace the contended surface is ``crates/engine/src``; its
        shared artifacts are ``crates/engine/Cargo.toml`` and
        ``crates/engine/src/lib.rs``, neither of which this table can locate. It
        must therefore name nothing rather than invent ``crates/engine/mod.rs``
        -- and the directory rule must still block.
        """

        graph = self._two_creators(
            "crates/engine/src/exec.rs", "crates/engine/src/plan.rs"
        )
        subjects = {item.subject for item in findings_of(graph, "scaffold-collision")}
        self.assertNotIn("crates/engine/mod.rs", subjects)
        self.assertNotIn("crates/engine/src/mod.rs", subjects)
        self.assertIn("crates/engine/src", subjects)
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_a_rust_module_below_a_workspace_crate_root_still_names_mod(self) -> None:
        graph = self._two_creators(
            "crates/engine/src/exec/step.rs", "crates/engine/src/exec/frame.rs"
        )
        finding = subject_of(
            findings_of(graph, "scaffold-collision"), "crates/engine/src/exec/mod.rs"
        )
        self.assertEqual(finding.severity, "error")

    def test_csharp_project_file_is_named(self) -> None:
        graph = self._two_creators("src/Billing/Invoice.cs", "src/Billing/Ledger.cs")
        finding = subject_of(
            findings_of(graph, "scaffold-collision"), "src/Billing/Billing.csproj"
        )
        self.assertEqual(finding.severity, "error")
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_go_falls_back_to_the_directory_rule(self) -> None:
        """Go needs no per-directory marker, so the language-neutral rule fires."""

        graph = self._two_creators("internal/store/reader.go", "internal/store/writer.go")
        finding = subject_of(findings_of(graph, "scaffold-collision"), "internal/store")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(finding.nodes, ("ALPHA", "BETA"))
        self.assertIn("contested shared surface", finding.message)
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_an_unknown_extension_is_never_a_silent_pass(self) -> None:
        graph = self._two_creators("app/batch/payroll.cbl", "app/batch/ledger.cbl")
        finding = subject_of(findings_of(graph, "scaffold-collision"), "app/batch")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_files_with_no_extension_at_all_are_never_a_silent_pass(self) -> None:
        """Requiring a dot in the last segment is a language assumption.

        ``Dockerfile``, ``Makefile``, Bazel ``BUILD``/``WORKSPACE``,
        ``Earthfile``, ``Gemfile`` and extensionless shell entry points are
        ordinary files. Two nodes creating the first of them in a new directory
        contest it exactly as much as two ``.go`` files would.
        """

        for first, second in (
            ("deploy/staging/Dockerfile", "deploy/staging/Makefile"),
            ("services/edge/BUILD", "services/edge/WORKSPACE"),
            ("ops/bin/deploy", "ops/bin/rollback"),
        ):
            with self.subTest(first=first, second=second):
                graph = self._two_creators(first, second)
                directory = first.rsplit("/", 1)[0]
                finding = subject_of(
                    findings_of(graph, "scaffold-collision"), directory
                )
                self.assertEqual(finding.severity, "error")
                self.assertEqual(finding.nodes, ("ALPHA", "BETA"))
                self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_one_extensionless_contender_still_contests_the_surface(self) -> None:
        """The mixed case was the worst silent pass: an invisible contender left
        a single visible creator, and a genuinely contested directory passed."""

        graph = self._two_creators(
            "deploy/staging/Dockerfile", "deploy/staging/compose.yaml"
        )
        finding = subject_of(findings_of(graph, "scaffold-collision"), "deploy/staging")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_a_literal_directory_scope_cannot_invent_a_surface(self) -> None:
        """Reading a literal scope as a file must not manufacture findings.

        ``internal/store`` is ambiguous (extensionless file, or directory). Read
        as a file its parent is ``internal`` -- a top-level repository root,
        which the directory rule already skips -- so the ambiguity is inert.
        """

        graph = self._two_creators("internal/store", "internal/queue")
        self.assertEqual(findings_of(graph, "scaffold-collision"), ())

    def test_a_directory_with_one_named_owner_is_not_contested(self) -> None:
        graph = graph_of(
            node(
                "OWNER",
                write_scope=["internal/store", "internal/store/reader.go"],
                file_locks=["internal/store/**"],
            ),
            node("BETA", write_scope=["internal/store/writer.go"], file_locks=[]),
        )
        self.assertEqual(findings_of(graph, "scaffold-collision"), ())

    def test_a_directory_established_at_an_earlier_level_is_not_contested(self) -> None:
        graph = graph_of(
            node("ROOT", write_scope=["internal/store/schema.go"], file_locks=[]),
            node(
                "ALPHA",
                dependencies=["ROOT"],
                write_scope=["internal/store/reader.go"],
                file_locks=[],
            ),
            node(
                "BETA",
                dependencies=["ROOT"],
                write_scope=["internal/store/writer.go"],
                file_locks=[],
            ),
        )
        self.assertEqual(findings_of(graph, "scaffold-collision"), ())

    def test_an_existing_directory_is_not_a_new_shared_surface(self) -> None:
        graph = self._two_creators("internal/store/reader.go", "internal/store/writer.go")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "internal" / "store").mkdir(parents=True)
            self.assertEqual(findings_of(graph, "scaffold-collision", repo_root=root), ())

    def test_a_top_level_directory_is_a_repository_root_not_a_surface(self) -> None:
        graph = self._two_creators("docs/alpha.md", "docs/beta.md")
        self.assertEqual(findings_of(graph, "scaffold-collision"), ())

    def test_double_underscore_tests_is_a_test_root(self) -> None:
        """B9: ``__tests__`` is the dominant JS/TS test-root convention.

        A Jest test directory is a folder of files, not a module with a barrel,
        so the ecosystem table must NOT invent ``__tests__/index.ts``. Being a
        recognized test root suppresses the marker and hands the surface to the
        language-neutral directory rule -- a less precise finding, never a
        quieter one: this still blocks.
        """

        graph = self._two_creators(
            "src/__tests__/users.test.ts", "src/__tests__/orders.test.ts"
        )
        subjects = {item.subject for item in findings_of(graph, "scaffold-collision")}
        self.assertNotIn("src/__tests__/index.ts", subjects)
        self.assertIn("src/__tests__", subjects)
        self.assertEqual(lint_exit_code(lint_plan(graph)), 1)

    def test_a_typescript_barrel_outside_a_test_root_is_still_named(self) -> None:
        """Suppression is scoped to test roots; ordinary modules keep the barrel."""

        graph = self._two_creators("src/api/users.ts", "src/api/orders.ts")
        subjects = {item.subject for item in findings_of(graph, "scaffold-collision")}
        self.assertIn("src/api/index.ts", subjects)

    def test_python_test_roots_still_imply_conftest(self) -> None:
        graph = self._two_creators("tests/suite/test_a.py", "tests/suite/test_b.py")
        subjects = {item.subject for item in findings_of(graph, "scaffold-collision")}
        self.assertIn("tests/suite/conftest.py", subjects)


class GlobWriteScopeContentionTests(unittest.TestCase):
    """B5: a directory glob used to disable contention analysis entirely.

    A node scoped ``pkg/foo/**`` still creates files in ``pkg/foo``. The glob
    makes it a *creator* of the surface; it never makes it the *owner* of a
    shared file inside it, because permission is not obligation.
    """

    def test_two_glob_scopes_rooted_in_one_new_directory_contend(self) -> None:
        graph = graph_of(
            node("ALPHA", write_scope=["svc/core/gen-*.go"], file_locks=[]),
            node("BETA", write_scope=["svc/core/api-*.go"], file_locks=[]),
        )
        # The scopes themselves do not overlap ...
        self.assertEqual(findings_of(graph, "write-scope-overlap"), ())
        # ... but both create the first files in the same unowned directory.
        finding = subject_of(findings_of(graph, "scaffold-collision"), "svc/core")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(finding.nodes, ("ALPHA", "BETA"))

    def test_glob_scopes_contend_in_python_too(self) -> None:
        graph = graph_of(
            node("ALPHA", write_scope=["src/pkg/gen_*.py"], file_locks=[]),
            node("BETA", write_scope=["src/pkg/api_*.py"], file_locks=[]),
        )
        finding = subject_of(findings_of(graph, "scaffold-collision"), "src/pkg")
        self.assertEqual(finding.severity, "error")

    def test_recursive_glob_scopes_contend(self) -> None:
        graph = graph_of(
            node("ALPHA", write_scope=["pkg/foo/reader/**"], file_locks=[]),
            node("BETA", write_scope=["pkg/foo/writer/**"], file_locks=[]),
            node("GAMMA", write_scope=["pkg/bar/**"], file_locks=[]),
        )
        subjects = {item.subject for item in findings_of(graph, "scaffold-collision")}
        self.assertEqual(subjects, set())
        contended = graph_of(
            node("ALPHA", write_scope=["pkg/foo/**"], file_locks=[]),
            node("BETA", write_scope=["pkg/foo/extra/*.md"], file_locks=[]),
        )
        # These two also overlap outright, which is reported separately.
        self.assertTrue(findings_of(contended, "write-scope-overlap"))


class UniversalReadScopeTests(unittest.TestCase):
    def test_bare_and_top_level_globs_warn(self) -> None:
        graph = graph_of(
            node("ALPHA", read_scope=["**"]),
            node("BETA", read_scope=["src/**"]),
            node("GAMMA", read_scope=["src/pkg/sub/**", "docs/GAMMA.md"]),
        )
        findings = findings_of(graph, "universal-read-scope")
        self.assertEqual({item.nodes[0] for item in findings}, {"ALPHA", "BETA"})
        for item in findings:
            self.assertEqual(item.severity, "warning")
            self.assertIn("metadata-only index", item.fix)
            self.assertIn("cold expansion", item.fix)

    def test_universal_read_scope_is_not_an_error(self) -> None:
        graph = graph_of(node("ALPHA", read_scope=["**"]))
        findings = lint_plan(graph)
        self.assertEqual(lint_exit_code(findings), 0)
        self.assertEqual(lint_exit_code(findings, strict=True), 1)

    def test_an_unanchored_read_scope_is_not_a_scope_syntax_error(self) -> None:
        """Read scopes are matched, never locked; only locks must be anchored."""

        graph = graph_of(node("ALPHA", read_scope=["**", "**/*.py"]))
        self.assertEqual(findings_of(graph, "scope-syntax"), ())


class ParallelSafeDeclarationTests(unittest.TestCase):
    """B9: a plan with no ``parallel_safe`` was silently fully serialized."""

    def test_a_plan_that_never_declares_parallel_safe_is_diagnosed(self) -> None:
        nodes = [node(f"N{index}") for index in range(3)]
        for item in nodes:
            del item["parallel_safe"]
        graph = graph_of(*nodes)
        findings = findings_of(graph, "parallel-safe-declaration")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(findings[0].subject, "plan")
        self.assertIn("no node in this plan declares parallel_safe", findings[0].message)
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        self.assertEqual([item.sessions for item in rounds], [1, 1, 1])

    def test_a_single_node_omitting_the_field_is_named(self) -> None:
        quiet = node("QUIET")
        del quiet["parallel_safe"]
        graph = graph_of(node("LOUD"), quiet)
        findings = findings_of(graph, "parallel-safe-declaration")
        self.assertEqual([item.subject for item in findings], ["QUIET"])
        self.assertEqual(findings[0].severity, "warning")

    def test_a_fully_declared_plan_says_nothing(self) -> None:
        self.assertEqual(
            findings_of(graph_of(node("A"), node("B")), "parallel-safe-declaration"), ()
        )


class DurabilityOrderingTests(unittest.TestCase):
    def test_same_level_recovery_claim_without_durability_dependency(self) -> None:
        graph = graph_of(
            node(
                "DURABLE",
                semantic_locks=["durability-qualification"],
                objective="Prove crash consistency and event replay.",
            ),
            node(
                "MISSION",
                acceptance_criteria=[
                    "The mission resumes after interruption without restating context."
                ],
            ),
        )
        findings = findings_of(graph, "durability-ordering")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(findings[0].nodes, ("MISSION", "DURABLE"))
        self.assertIn("same dependency level", findings[0].message)

    def test_external_effect_claim_is_flagged(self) -> None:
        graph = graph_of(
            node("DURABLE", semantic_locks=["durable-effects"]),
            node(
                "DELIVERY",
                acceptance_criteria=["Draft PR and comment delivery is receipt-backed."],
            ),
        )
        findings = findings_of(graph, "durability-ordering")
        self.assertEqual([item.nodes[0] for item in findings], ["DELIVERY"])

    def test_dependency_on_durability_clears_the_warning(self) -> None:
        graph = graph_of(
            node("DURABLE", semantic_locks=["durability-qualification"]),
            node(
                "MISSION",
                dependencies=["DURABLE"],
                acceptance_criteria=["The mission resumes after interruption."],
            ),
        )
        self.assertEqual(findings_of(graph, "durability-ordering"), ())

    def test_negated_effect_claims_are_not_flagged(self) -> None:
        graph = graph_of(
            node("DURABLE", semantic_locks=["durability-qualification"]),
            node(
                "GUARD",
                acceptance_criteria=[
                    "No hidden network, merge, or deploy authority is introduced.",
                    "Direct push and deploy are denied.",
                ],
            ),
        )
        self.assertEqual(findings_of(graph, "durability-ordering"), ())

    def test_a_plan_without_any_durability_node_is_flagged(self) -> None:
        graph = graph_of(
            node("MISSION", acceptance_criteria=["Missions resume after a crash."]),
        )
        findings = findings_of(graph, "durability-ordering")
        self.assertEqual(len(findings), 1)
        self.assertIn("no durability node", findings[0].message)

    def test_the_check_can_never_exceed_warning(self) -> None:
        """B7: it is a keyword heuristic over prose and must not block a plan."""

        graph = graph_of(
            node("DURABLE", semantic_locks=["durability-qualification"]),
            node("MISSION", acceptance_criteria=["The mission resumes after a crash."]),
            node("DELIVERY", acceptance_criteria=["Release notes are published."]),
        )
        findings = findings_of(graph, "durability-ordering")
        self.assertTrue(findings)
        self.assertTrue(all(item.severity == "warning" for item in findings))
        self.assertEqual(lint_exit_code(lint_plan(graph)), 0)

    def test_abstract_recovery_nouns_are_not_an_assertion(self) -> None:
        """B7 false positives: assessing recovery is not claiming it."""

        graph = graph_of(
            node("DURABLE", semantic_locks=["durability-qualification"]),
            node(
                "STEWARD",
                objective=(
                    "Make Steward continuously assess operational health, recovery, "
                    "dependencies, observability, and evidence integrity."
                ),
                acceptance_criteria=[
                    "Evidence corruption or recovery gaps fail closed.",
                    "Repair proposals are bounded and reversible.",
                ],
            ),
        )
        self.assertEqual(findings_of(graph, "durability-ordering"), ())

    def test_a_node_that_builds_recovery_machinery_is_a_provider(self) -> None:
        """B7 false negatives: the reconciler was reported against itself."""

        graph = graph_of(
            node(
                "EFFECT",
                semantic_locks=["durable-effects"],
                objective="Make effects durable through an outbox and reconciliation.",
            ),
            node(
                "RECONCILE",
                semantic_locks=["desired-state-reconciler"],
                objective=(
                    "Implement a deterministic desired-state reconciler for mission "
                    "recovery, retries, remands, rollback, and quarantine."
                ),
                acceptance_criteria=[
                    "Stale leases and interrupted verification have bounded repairs.",
                ],
            ),
        )
        self.assertEqual(findings_of(graph, "durability-ordering"), ())

    def test_asserting_recovery_does_not_make_a_node_its_own_provider(self) -> None:
        graph = graph_of(
            node(
                "PROOF",
                semantic_locks=["humanless-qualification"],
                objective=(
                    "Prove role-first end-to-end resolution across ambiguity, CI repair, "
                    "and recoverable failures."
                ),
                acceptance_criteria=[
                    "The mission resumes after interruption without restating context."
                ],
            ),
        )
        findings = findings_of(graph, "durability-ordering")
        self.assertEqual(len(findings), 1)
        self.assertIn("no durability node", findings[0].message)


class TypedDurabilitySemanticsTests(unittest.TestCase):
    """Versioned metadata is authoritative; prose remains legacy-only fallback."""

    def _exact_descendant_shape(self) -> PlanGraph:
        return graph_of(
            node(
                "WAVE-HOST-300",
                durability_role="provider",
                objective=(
                    "Implement immutable wave manifests, checkpoints, candidate sealing, "
                    "bounded host supervision, and one CAS integration transaction per round."
                ),
            ),
            node(
                "TASK-REUSE-310",
                dependencies=["WAVE-HOST-300"],
                durability_role="consumer",
                durability_providers=["WAVE-HOST-300"],
                acceptance_criteria=[
                    "Dispositions distinguish exact reuse, verify existing, resume active, "
                    "repair existing, execute new, stale, conflict, and blocked."
                ],
            ),
            node(
                "GENERIC-EXECUTOR-400",
                dependencies=["TASK-REUSE-310"],
                durability_role="consumer",
                durability_providers=["WAVE-HOST-300"],
                objective=(
                    "Implement the generic runtime that validates plans, compiles rounds, "
                    "launches workers, checkpoints, seals, verifies, integrates, resumes, "
                    "and applies versioned graph patches."
                ),
            ),
            node(
                "PUBLIC-RUNTIME-500",
                dependencies=["GENERIC-EXECUTOR-400"],
                durability_role="consumer",
                durability_providers=["WAVE-HOST-300"],
                objective=(
                    "Expose build, validate, rounds, execute, resume, status, cancel, "
                    "graph, and reconcile through the public runtime."
                ),
            ),
        )

    def test_exact_descendant_shape_uses_roles_not_provider_looking_prose(self) -> None:
        graph = self._exact_descendant_shape()
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        order = [node_id for item in rounds for node_id in item.nodes]
        self.assertEqual(
            order,
            [
                "WAVE-HOST-300",
                "TASK-REUSE-310",
                "GENERIC-EXECUTOR-400",
                "PUBLIC-RUNTIME-500",
            ],
        )
        # Retain the exact provider-looking objectives: their type, not edited
        # prose, determines that they are consumers and never providers.
        self.assertEqual(graph.durability("GENERIC-EXECUTOR-400").role, "consumer")
        self.assertEqual(graph.durability("PUBLIC-RUNTIME-500").role, "consumer")
        self.assertEqual(findings_of(graph, "durability-ordering"), ())

    def test_typed_none_with_a_claim_is_a_fail_closed_contradiction(self) -> None:
        cases = (
            node(
                "NONE-PROSE",
                durability_role="none",
                acceptance_criteria=["The system resumes after a crash."],
            ),
            node(
                "NONE-DURABILITY-LOCK",
                durability_role="none",
                semantic_locks=["durability-qualification"],
            ),
            node(
                "NONE-EFFECT-LOCK",
                durability_role="none",
                semantic_locks=["remote-write"],
            ),
        )
        for item in cases:
            with self.subTest(node=item["id"]):
                graph = graph_of(item)
                with self.assertRaisesRegex(
                    DagStandardError, "declares durability_role 'none'"
                ):
                    compile_rounds(graph, command_prefix=TEST_PREFIX)
                finding = findings_of(graph, "durability-semantics")
                self.assertEqual(len(finding), 1)
                self.assertEqual(finding[0].severity, "error")

    def test_typed_consumer_keeps_precedence_over_durability_lock(self) -> None:
        graph = graph_of(
            node("PROVIDER", durability_role="provider"),
            node(
                "CONSUMER",
                dependencies=["PROVIDER"],
                durability_role="consumer",
                durability_providers=["PROVIDER"],
                semantic_locks=["durability-qualification"],
            ),
        )
        self.assertEqual(
            [item.nodes for item in compile_rounds(graph, command_prefix=TEST_PREFIX)],
            [("PROVIDER",), ("CONSUMER",)],
        )

    def test_typed_schema_rejects_malformed_and_contradictory_values(self) -> None:
        cases = (
            node("BAD-ROLE", durability_role=["provider", "none"]),
            node("MISSING-PROVIDER", durability_role="consumer"),
            node(
                "PROVIDER-WITH-LIST",
                durability_role="provider",
                durability_providers=["PROVIDER-WITH-LIST"],
            ),
            node("ORPHAN-LIST", durability_providers=["SOMETHING"]),
        )
        for item in cases:
            with self.subTest(node=item["id"]):
                with self.assertRaises(DagStandardError):
                    compile_rounds(graph_of(item), command_prefix=TEST_PREFIX)

    def test_consumer_requires_a_known_typed_provider_and_raw_dependency(self) -> None:
        graph = graph_of(
            node("PROVIDER", durability_role="provider"),
            node(
                "CONSUMER",
                durability_role="consumer",
                durability_providers=["PROVIDER"],
            ),
        )
        with self.assertRaisesRegex(DagStandardError, "must depend transitively"):
            compile_rounds(graph, command_prefix=TEST_PREFIX)


class CombinedSemanticCycleTests(unittest.TestCase):
    """The old fixed-point cap must never convert a cycle into a schedule."""

    def test_exact_task_to_descendant_provider_shape_fails_deterministically(self) -> None:
        graph = graph_of(
            node("WAVE-HOST-300"),
            node(
                "TASK-REUSE-310",
                dependencies=["WAVE-HOST-300"],
                acceptance_criteria=["Existing work may resume active tasks safely."],
            ),
            node(
                "GENERIC-EXECUTOR-400",
                dependencies=["TASK-REUSE-310"],
                objective=(
                    "Implement generic durable execution with checkpoints and resumes."
                ),
            ),
            node(
                "PUBLIC-RUNTIME-500",
                dependencies=["GENERIC-EXECUTOR-400"],
                objective="Implement public durable runtime resume commands.",
            ),
        )
        with self.assertRaisesRegex(
            DagStandardError,
            "combined dependency/semantic ordering cycle: GENERIC-EXECUTOR-400",
        ):
            compile_rounds(graph, command_prefix=TEST_PREFIX)
        cycle_findings = findings_of(graph, "semantic-ordering")
        self.assertEqual(len(cycle_findings), 1)
        self.assertEqual(cycle_findings[0].severity, "error")
        self.assertIn("cycle", cycle_findings[0].message)

    def test_caller_cannot_suppress_legacy_constraints_with_empty_findings(self) -> None:
        graph = graph_of(
            node("DURABLE", semantic_locks=["durability-qualification"]),
            node("MISSION", acceptance_criteria=["The mission resumes after a crash."]),
        )
        with self.assertRaisesRegex(DagStandardError, "supplied durability-ordering"):
            compile_rounds(
                graph, command_prefix=TEST_PREFIX, ordering_findings=()
            )


class ContentionCompilationTests(unittest.TestCase):
    """The compiler must never emit a round its own linter rejects.

    Durability ordering was one half of compiler/linter agreement; scaffold
    contention is the other. Two nodes reported as racing to create an unowned
    shared surface cannot be dispatched together, because that dispatch *is* the
    collision. Deferring one makes the surface exist, which resolves it.
    """

    @staticmethod
    def _contending() -> PlanGraph:
        return graph_of(
            node("ROOT", parallel_safe=False),
            node(
                "FIRST",
                dependencies=["ROOT"],
                write_scope=["tests/shared/test_first.py"],
                critical_path_importance=90,
            ),
            node(
                "SECOND",
                dependencies=["ROOT"],
                write_scope=["tests/shared/test_second.py"],
                critical_path_importance=80,
            ),
        )

    def test_contending_nodes_are_never_co_scheduled(self) -> None:
        graph = self._contending()
        errors = [
            finding
            for finding in lint_plan(graph)
            if finding.check == "scaffold-collision" and finding.severity == "error"
        ]
        self.assertTrue(errors, "fixture must actually contend for a shared scaffold")

        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        for compiled in rounds:
            self.assertFalse(
                {"FIRST", "SECOND"} <= set(compiled.nodes),
                "compiler emitted the exact pair the linter reports as an error",
            )

    def test_naming_one_owner_resolves_the_split(self) -> None:
        # The documented fix -- exactly one node NAMES the scaffold -- must also
        # be the fix the compiler honours, otherwise authors get a permanent
        # split they cannot resolve by following the linter's own advice.
        graph = graph_of(
            node("ROOT", parallel_safe=False),
            node(
                "FIRST",
                dependencies=["ROOT"],
                write_scope=[
                    "tests/shared/test_first.py",
                    "tests/shared/__init__.py",
                    "tests/shared/conftest.py",
                ],
                critical_path_importance=90,
            ),
            node(
                "SECOND",
                dependencies=["ROOT"],
                write_scope=["tests/shared/test_second.py"],
                critical_path_importance=80,
            ),
        )
        self.assertEqual(
            [
                finding
                for finding in lint_plan(graph)
                if finding.check == "scaffold-collision"
                and finding.severity == "error"
            ],
            [],
        )
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        self.assertTrue(
            any({"FIRST", "SECOND"} <= set(item.nodes) for item in rounds),
            "an owned scaffold must let the pair share a round again",
        )

    def test_an_existing_scaffold_is_not_contended(self) -> None:
        # A scaffold that already exists needs no creator, so it is not a race.
        # Without this, every mature repository reports permanent false errors.
        graph = self._contending()
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            (repo_root / "tests" / "shared").mkdir(parents=True)
            (repo_root / "tests" / "shared" / "__init__.py").write_text(
                "", encoding="utf-8"
            )
            findings = lint_plan(graph, repo_root=repo_root)
        self.assertEqual(
            [
                finding
                for finding in findings
                if finding.check == "scaffold-collision"
                and finding.severity == "error"
            ],
            [],
        )


class SemanticOrderingCompilationTests(unittest.TestCase):
    """B3: the compiler used to contradict its own linter.

    A confirmed durability-ordering finding is now a scheduling constraint. The
    durability provider is a release barrier inside its level: it goes out alone
    and the rest of the level is proven against the integrated result.
    """

    @staticmethod
    def _level_seven_shaped() -> PlanGraph:
        return graph_of(
            node("BASE", parallel_safe=False),
            node(
                "DURABLE",
                dependencies=["BASE"],
                semantic_locks=["durability-qualification"],
                objective="Prove restart, resume, and crash consistency.",
                critical_path_importance=90,
            ),
            node(
                "MISSION",
                dependencies=["BASE"],
                acceptance_criteria=[
                    "The mission resumes after interruption without restating context."
                ],
                critical_path_importance=80,
            ),
            node(
                "DELIVERY",
                dependencies=["BASE"],
                acceptance_criteria=["Draft PR and comment delivery is receipt-backed."],
                critical_path_importance=70,
            ),
            node("QUIET", dependencies=["BASE"], critical_path_importance=60),
        )

    def test_the_durability_node_is_released_alone_and_the_level_follows(self) -> None:
        graph = self._level_seven_shaped()
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        self.assertEqual([item.nodes for item in rounds][0], ("BASE",))
        level_one = [item for item in rounds if item.level == 1]
        self.assertEqual(len(level_one), 2)
        self.assertEqual(level_one[0].nodes, ("DURABLE",))
        self.assertEqual(
            sorted(level_one[1].nodes), ["DELIVERY", "MISSION", "QUIET"]
        )
        self.assertEqual(level_one[1].deferred_after, ("DURABLE",))
        self.assertIn("deferred behind durability node(s) DURABLE", level_one[1].reason)

    def test_no_semantic_ordering_refuses_an_invalid_schedule(self) -> None:
        graph = self._level_seven_shaped()
        with self.assertRaisesRegex(DagStandardError, "no-semantic-ordering refuses"):
            compile_rounds(graph, semantic_ordering=False, command_prefix=TEST_PREFIX)

    def test_the_compiler_and_the_linter_agree(self) -> None:
        graph = self._level_seven_shaped()
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        placement = {
            node_id: index
            for index, item in enumerate(rounds)
            for node_id in item.nodes
        }
        for finding in findings_of(graph, "durability-ordering"):
            consumer, *providers = finding.nodes
            for provider in providers:
                self.assertLess(
                    placement[provider],
                    placement[consumer],
                    f"{consumer} was scheduled no later than {provider}",
                )

    def test_dependencies_are_still_ordered_before_deferred_nodes(self) -> None:
        graph = graph_of(
            node("DURABLE", semantic_locks=["durability-qualification"]),
            node("MISSION", acceptance_criteria=["The system resumes after a crash."]),
            node("AFTER", dependencies=["MISSION"]),
        )
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        order = [item.nodes for item in rounds]
        self.assertLess(order.index(("DURABLE",)), order.index(("MISSION",)))
        self.assertLess(order.index(("MISSION",)), order.index(("AFTER",)))

    def test_a_later_level_provider_defers_only_the_node_that_named_it(self) -> None:
        graph = graph_of(
            node("SEED"),
            node("MISSION", acceptance_criteria=["The system resumes after a crash."]),
            node("QUIET"),
            node(
                "DURABLE",
                dependencies=["SEED"],
                semantic_locks=["durability-qualification"],
            ),
        )
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        placement = {
            node_id: index for index, item in enumerate(rounds) for node_id in item.nodes
        }
        self.assertLess(placement["DURABLE"], placement["MISSION"])
        self.assertEqual(placement["QUIET"], placement["SEED"])


class ContractCompletenessTests(unittest.TestCase):
    def test_each_missing_contract_field_is_an_error(self) -> None:
        graph = graph_of(
            node(
                "ALPHA",
                required_tests=[],
                stopping_condition="   ",
                rollback=None,
                forbidden_scope=[],
                write_scope=[],
            )
        )
        findings = findings_of(graph, "contract-completeness")
        self.assertEqual(
            {item.subject for item in findings},
            {
                "required_tests",
                "stopping_condition",
                "rollback",
                "forbidden_scope",
                "write_scope",
            },
        )
        self.assertTrue(all(item.severity == "error" for item in findings))


class CleanPlanTests(unittest.TestCase):
    def test_a_conforming_plan_produces_no_findings(self) -> None:
        graph = graph_of(
            node("ALPHA"),
            node("BETA", dependencies=["ALPHA"]),
            node("GAMMA", dependencies=["ALPHA"]),
        )
        findings = lint_plan(graph)
        self.assertEqual(findings, ())
        self.assertEqual(lint_exit_code(findings), 0)
        self.assertEqual(lint_exit_code(findings, strict=True), 0)

    def test_a_conforming_non_python_plan_produces_no_findings(self) -> None:
        graph = graph_of(
            node(
                "SEED",
                write_scope=["internal/store/schema.go"],
                file_locks=["internal/store/schema.go"],
            ),
            node(
                "ALPHA",
                dependencies=["SEED"],
                write_scope=["internal/store/reader.go"],
                file_locks=["internal/store/reader.go"],
            ),
            node(
                "BETA",
                dependencies=["SEED"],
                write_scope=["internal/store/writer.go"],
                file_locks=["internal/store/writer.go"],
            ),
        )
        self.assertEqual(lint_plan(graph), ())


class NonPythonPlansCanFailTests(unittest.TestCase):
    """B6: severities must let a non-Python plan actually fail dag-lint."""

    def test_every_ecosystem_can_produce_a_blocking_exit_code(self) -> None:
        cases = {
            "go": ("internal/store/reader.go", "internal/store/writer.go"),
            "rust": ("src/engine/lexer.rs", "src/engine/parser.rs"),
            "typescript": ("src/api/users.ts", "src/api/orders.ts"),
            "csharp": ("src/Billing/Invoice.cs", "src/Billing/Ledger.cs"),
            "cobol": ("app/batch/payroll.cbl", "app/batch/ledger.cbl"),
        }
        for name, (first, second) in cases.items():
            with self.subTest(ecosystem=name):
                graph = graph_of(
                    node("ALPHA", write_scope=[first], file_locks=[first]),
                    node("BETA", write_scope=[second], file_locks=[second]),
                )
                findings = lint_plan(graph)
                self.assertEqual(lint_exit_code(findings), 1)
                self.assertTrue(
                    any(
                        item.check == "scaffold-collision" and item.severity == "error"
                        for item in findings
                    )
                )


class RoundCompilationTests(unittest.TestCase):
    def test_serial_node_inside_a_parallel_level_splits_the_level(self) -> None:
        graph = graph_of(
            node("ROOT", parallel_safe=False),
            node(
                "SERIAL",
                dependencies=["ROOT"],
                parallel_safe=False,
                critical_path_importance=99,
            ),
            node("PAR1", dependencies=["ROOT"], critical_path_importance=90),
            node("PAR2", dependencies=["ROOT"], critical_path_importance=80),
        )
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        self.assertEqual([item.round_id for item in rounds], ["R1", "R2", "R3"])
        self.assertEqual(rounds[1].nodes, ("PAR1", "PAR2"))
        self.assertTrue(rounds[1].parallel_safe)
        # The highest-importance node in the level is serial; compiling rounds
        # (rather than dispatching the level) keeps it from capping the wave.
        self.assertEqual(rounds[2].nodes, ("SERIAL",))
        self.assertFalse(rounds[2].parallel_safe)
        self.assertEqual(rounds[2].level, 1)
        info = findings_of(graph, "serial-in-level")
        self.assertEqual(len(info), 1)
        self.assertEqual(info[0].severity, "info")
        self.assertIn("2 dispatch rounds", info[0].message)

    def test_level_wider_than_capacity_splits_into_rounds(self) -> None:
        graph = graph_of(*(node(f"N{index}") for index in range(10)))
        rounds = compile_rounds(graph, max_sessions=4, command_prefix=TEST_PREFIX)
        self.assertEqual([item.sessions for item in rounds], [4, 4, 2])
        self.assertEqual(rounds[0].nodes, ("N0", "N1", "N2", "N3"))
        self.assertTrue(all(item.level == 0 for item in rounds))
        info = findings_of(graph, "capacity-split", max_sessions=4)
        self.assertEqual(len(info), 1)
        self.assertIn("above the 4-session cap", info[0].message)
        self.assertEqual(
            len(
                compile_rounds(
                    graph,
                    max_sessions=DEFAULT_MAX_SESSIONS,
                    command_prefix=TEST_PREFIX,
                )
            ),
            2,
        )

    def test_conflicting_nodes_never_share_a_round(self) -> None:
        graph = graph_of(
            node("ALPHA", file_locks=["src/shared/**"]),
            node("BETA", file_locks=["src/shared/thing.py"]),
            node("GAMMA", semantic_locks=["ALPHA-lock"], file_locks=["docs/GAMMA.md"]),
        )
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        self.assertEqual([item.nodes for item in rounds], [("ALPHA",), ("BETA", "GAMMA")])

    def test_ordering_matches_the_dispatcher_selection_order(self) -> None:
        graph = graph_of(
            node("LOW", critical_path_importance=10, downstream_unlock_value=10),
            node("HIGH", critical_path_importance=99, downstream_unlock_value=10),
            node("MID_B", critical_path_importance=50, downstream_unlock_value=20),
            node("MID_A", critical_path_importance=50, downstream_unlock_value=20),
        )
        rounds = compile_rounds(graph, command_prefix=TEST_PREFIX)
        self.assertEqual(rounds[0].nodes, ("HIGH", "MID_A", "MID_B", "LOW"))

    def test_max_sessions_must_be_positive(self) -> None:
        with self.assertRaises(DagStandardError):
            compile_rounds(graph_of(node("ALPHA")), max_sessions=0)


class DispatchCommandTests(unittest.TestCase):
    """B8: the command must be runnable, and must name the right repository."""

    def test_the_command_is_derived_from_the_plan_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".autopilot" / "bin").mkdir(parents=True)
            (root / ".autopilot" / "bin" / "autopilot.py").write_text("", encoding="utf-8")
            plan = root / ".autopilot" / "plan.json"
            plan.write_text("{}", encoding="utf-8")
            prefix = dispatch_command_prefix(plan_path=plan)
        self.assertIn(root.as_posix(), prefix)
        self.assertIn(f"--repo-root {root.as_posix()}", prefix)
        self.assertTrue(prefix.endswith("dispatch"))
        self.assertNotIn("--plan", prefix)

    def test_an_external_plan_has_no_false_dispatch_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            plan = root / "custom-plan.json"
            plan.write_text("{}", encoding="utf-8")
            prefix = dispatch_command_prefix(plan_path=plan, repo_root=root)
        self.assertIsNone(prefix)

    def test_direct_rounds_keep_command_and_execution_mode_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            installed_root = workspace / "installed"
            other_root = workspace / "other"
            (installed_root / ".autopilot").mkdir(parents=True)
            other_root.mkdir()
            plan = installed_root / ".autopilot" / "plan.json"
            plan.write_text(json.dumps({"nodes": [node("ALPHA")]}), encoding="utf-8")
            graph = PlanGraph([node("ALPHA")], source=plan)
            round_ = compile_rounds(graph, repo_root=other_root)[0]
        self.assertEqual(round_.execution_mode, "manual-parent-v1")
        self.assertIsNone(round_.command)

    def test_direct_external_rounds_reject_supplied_command_or_mode_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "external-plan.json"
            graph = PlanGraph([node("ALPHA")], source=plan)
            with self.assertRaisesRegex(
                DagStandardError, "external plan cannot receive an executable dispatch command"
            ):
                compile_rounds(graph, command_prefix="python dispatch")
            with self.assertRaisesRegex(
                DagStandardError, "supplied execution mode does not match"
            ):
                compile_rounds(
                    graph,
                    execution_mode="installed-dispatch-v1",
                    command_prefix="python dispatch",
                )

    def test_external_cli_rounds_are_manual_parent_not_false_shell_commands(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "external-plan.json"
            plan.write_text(json.dumps({"nodes": [node("ALPHA")]}), encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = autopilot.main(
                    ["--repo-root", str(root), "dag-rounds", "--plan", str(plan), "--json"]
                )
        self.assertEqual(code, 0)
        document = json.loads(buffer.getvalue())
        self.assertEqual(document["execution"]["mode"], "manual-parent-v1")
        self.assertFalse(document["execution"]["executable_dispatch_command_available"])
        self.assertIn("No executable dispatcher command", document["execution"]["note"])
        self.assertIsNone(document["rounds"][0]["command"])
        self.assertNotIn("--plan", buffer.getvalue())

    def test_installed_plan_command_is_parseable_by_the_actual_dispatch_parser(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".autopilot").mkdir()
            plan = root / ".autopilot" / "plan.json"
            plan.write_text(json.dumps({"nodes": [node("ALPHA")]}), encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = autopilot.main(
                    ["--repo-root", str(root), "dag-rounds", "--plan", str(plan), "--json"]
                )
        self.assertEqual(code, 0)
        command = json.loads(buffer.getvalue())["rounds"][0]["command"]
        self.assertIsNotNone(command)
        parsed = autopilot.parser().parse_args(shlex.split(command)[2:])
        self.assertEqual(parsed.command, "dispatch")
        self.assertEqual(parsed.node, ["ALPHA"])

    def test_the_default_actor_is_vendor_neutral(self) -> None:
        graph = graph_of(node("ALPHA"), node("BETA"))
        default = compile_rounds(graph, command_prefix=TEST_PREFIX)[0]
        self.assertIn("--actor orchestrator:r1", default.command)
        self.assertNotIn("codex", default.command)
        self.assertEqual(default.to_dict()["nodes"], ["ALPHA", "BETA"])

    def test_actor_is_honoured(self) -> None:
        graph = graph_of(node("ALPHA"), node("BETA"))
        rounds = compile_rounds(
            graph, actor="acme:integrator", command_prefix=TEST_PREFIX
        )
        self.assertEqual(
            rounds[0].command,
            f"{TEST_PREFIX} --actor acme:integrator --node ALPHA --node BETA",
        )

    def test_the_cli_command_names_the_repository_holding_the_plan(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".autopilot").mkdir()
            plan = root / ".autopilot" / "plan.json"
            plan.write_text(
                json.dumps({"nodes": [node("ALPHA")]}), encoding="utf-8"
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                # No --repo-root: its "." default must not decide the target.
                autopilot.main(["dag-rounds", "--plan", str(plan), "--json"])
        command = json.loads(buffer.getvalue())["rounds"][0]["command"]
        self.assertIn(f"--repo-root {root.as_posix()}", command)


class PlanLoadingAndCliTests(unittest.TestCase):
    def _write_plan(self, root: Path, nodes: list[dict[str, Any]]) -> Path:
        path = root / "plan.json"
        path.write_text(
            json.dumps({"schema_version": 1, "nodes": nodes}, indent=2),
            encoding="utf-8",
        )
        return path

    def _write_document(self, root: Path, document: dict[str, Any], name: str = "plan.json") -> Path:
        path = root / name
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        return path

    def test_load_plan_graph_rejects_malformed_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(DagStandardError):
                load_plan_graph(root / "absent.json")
            broken = root / "broken.json"
            broken.write_text(json.dumps({"nodes": {}}), encoding="utf-8")
            with self.assertRaises(DagStandardError):
                load_plan_graph(broken)
            empty = root / "empty.json"
            empty.write_text(json.dumps({"nodes": []}), encoding="utf-8")
            with self.assertRaises(DagStandardError):
                load_plan_graph(empty)

    def test_cli_lint_reports_raw_dependency_errors_and_rounds_rejects_them(self) -> None:
        import autopilot

        cases = {
            "object": {"required": "PROVIDER"},
            "null": None,
            "scalar": "PROVIDER",
            "mixed": ["PROVIDER", 7],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label, dependencies in cases.items():
                with self.subTest(label=label):
                    plan = self._write_plan(root, [node("A", dependencies=dependencies)])
                    lint_output = io.StringIO()
                    with redirect_stdout(lint_output):
                        lint_code = autopilot.main(
                            [
                                "--repo-root",
                                str(root),
                                "dag-lint",
                                "--plan",
                                str(plan),
                                "--json",
                            ]
                        )
                    self.assertEqual(lint_code, 1)
                    report = json.loads(lint_output.getvalue())
                    self.assertEqual(report["counts"]["error"], 1)
                    self.assertEqual(report["findings"][0]["check"], "graph-validity")

                    errors = io.StringIO()
                    with redirect_stderr(errors):
                        rounds_code = autopilot.main(
                            [
                                "--repo-root",
                                str(root),
                                "dag-rounds",
                                "--plan",
                                str(plan),
                            ]
                        )
                    self.assertEqual(rounds_code, 2)
                    self.assertIn("invalid plan topology", errors.getvalue())

    def test_cli_rounds_rejects_an_unknown_dependency_without_lint(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._write_plan(root, [node("A", dependencies=["MISSING"])])
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "dag-rounds",
                        "--plan",
                        str(plan),
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("A depends on unknown node MISSING", errors.getvalue())

    def test_sealed_plan_reports_the_exact_consumed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._write_document(root, sealed_document([node("ALPHA")]))
            graph = load_plan_graph(plan)
        self.assertEqual(graph.integrity.status, "verified-sealed")
        self.assertTrue(graph.integrity.consumed_source_bytes_digest.startswith("sha256:"))
        self.assertTrue(graph.integrity.consumed_plan_digest.startswith("sha256:"))
        self.assertEqual(graph.integrity.sealed_contracts, ("ALPHA",))
        self.assertEqual(graph.integrity.unsealed_contracts, ())

    def test_digest_mutation_and_substitution_reject_before_lint_or_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = sealed_document([node("ALPHA")], title="sealed original")
            plan = self._write_document(root, original)
            original_graph = load_plan_graph(plan)

            substituted = json.loads(json.dumps(original))
            substituted["nodes"][0]["objective"] = "Substituted after verification."
            # Recompute the individual contract seal only: the complete plan
            # seal must still detect this verify/use substitution.
            contract = dict(substituted["nodes"][0])
            contract.pop("contract_digest")
            substituted["nodes"][0]["contract_digest"] = digest_json(contract)
            plan.write_text(json.dumps(substituted), encoding="utf-8")

            # The already-loaded graph is compiled from the one byte snapshot
            # it consumed; it never reopens this path during lint/rounds.
            self.assertEqual(lint_plan(original_graph), ())
            self.assertEqual(len(compile_rounds(original_graph)), 1)
            with self.assertRaisesRegex(DagStandardError, "plan_digest mismatch"):
                load_plan_graph(plan)

    def test_contract_and_plan_digest_mismatches_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = sealed_document([node("ALPHA")], title="original")
            document["nodes"][0]["rollback"] = "Substituted contract material."
            contract_plan = self._write_document(root, document, "contract.json")
            with self.assertRaisesRegex(DagStandardError, "contract_digest mismatch"):
                load_plan_graph(contract_plan)

            document = sealed_document([node("ALPHA")], title="original")
            document["title"] = "Substituted plan material."
            plan_plan = self._write_document(root, document, "plan.json")
            with self.assertRaisesRegex(DagStandardError, "plan_digest mismatch"):
                load_plan_graph(plan_plan)

    def test_legacy_and_partial_seals_are_never_reported_as_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = self._write_plan(root, [node("LEGACY")])
            self.assertEqual(load_plan_graph(legacy).integrity.status, "digest-unsealed")

            partial = {"schema_version": 1, "nodes": [node("PARTIAL")]}
            partial["plan_digest"] = digest_json(partial)
            partial_path = self._write_document(root, partial, "partial.json")
            self.assertEqual(load_plan_graph(partial_path).integrity.status, "partially-sealed")

    def test_cli_reports_integrity_and_durability_mode_as_independent_dimensions(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._write_document(root, sealed_document([node("SEALED-LEGACY")]))
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = autopilot.main(
                    ["--repo-root", str(root), "dag-lint", "--plan", str(plan), "--json"]
                )
        self.assertEqual(code, 0)
        report = json.loads(buffer.getvalue())
        self.assertEqual(report["integrity"]["status"], "verified-sealed")
        self.assertEqual(report["durability_semantics"]["mode"], "legacy-heuristic")
        self.assertFalse(report["expected_plan_binding"]["provided"])
        self.assertFalse(report["expected_plan_binding"]["matched"])

    def test_cli_reports_typed_v2_mode_independently_of_seal_status(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._write_document(
                root, sealed_document([node("TYPED", durability_role="provider")])
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = autopilot.main(
                    ["--repo-root", str(root), "dag-lint", "--plan", str(plan), "--json"]
                )
        self.assertEqual(code, 0)
        report = json.loads(buffer.getvalue())
        self.assertEqual(report["integrity"]["status"], "verified-sealed")
        self.assertEqual(report["durability_semantics"]["mode"], "typed-v2")

    def test_expected_plan_digest_rejects_a_self_consistent_substitute(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted = sealed_document([node("TRUSTED")], title="trusted plan")
            alternate = sealed_document([node("SUBSTITUTE")], title="alternate plan")
            plan = self._write_document(root, alternate)

            plain = io.StringIO()
            with redirect_stdout(plain):
                plain_code = autopilot.main(
                    ["--repo-root", str(root), "dag-lint", "--plan", str(plan), "--json"]
                )
            self.assertEqual(plain_code, 0, "self-consistent seals remain integrity only")
            plain_report = json.loads(plain.getvalue())
            self.assertEqual(plain_report["integrity"]["status"], "verified-sealed")
            self.assertNotEqual(
                plain_report["integrity"]["consumed_plan_digest"], trusted["plan_digest"]
            )

            for command in ("dag-lint", "dag-rounds"):
                with self.subTest(command=command):
                    errors = io.StringIO()
                    with redirect_stderr(errors):
                        rejected = autopilot.main(
                            [
                                "--repo-root",
                                str(root),
                                command,
                                "--plan",
                                str(plan),
                                "--expected-plan-digest",
                                trusted["plan_digest"],
                            ]
                        )
                    self.assertEqual(rejected, 2)
                    self.assertIn("expected plan digest mismatch", errors.getvalue())

    def test_expected_plan_digest_also_binds_an_unsealed_legacy_plan(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted = {"schema_version": 1, "nodes": [node("LEGACY")]}
            expected = digest_json(trusted)
            plan = self._write_document(root, trusted)
            accepted_output = io.StringIO()
            with redirect_stdout(accepted_output):
                accepted = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "dag-lint",
                        "--plan",
                        str(plan),
                        "--expected-plan-digest",
                        expected,
                        "--json",
                    ]
                )
            self.assertEqual(accepted, 0)
            accepted_report = json.loads(accepted_output.getvalue())
            self.assertEqual(accepted_report["integrity"]["status"], "digest-unsealed")
            self.assertTrue(accepted_report["expected_plan_binding"]["matched"])

            replacement = {"schema_version": 1, "nodes": [node("REPLACEMENT")]}
            plan.write_text(json.dumps(replacement), encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                rejected = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "dag-lint",
                        "--plan",
                        str(plan),
                        "--expected-plan-digest",
                        expected,
                    ]
                )
        self.assertEqual(rejected, 2)
        self.assertIn("expected plan digest mismatch", errors.getvalue())

    def test_cli_subcommands_are_wired_and_return_the_documented_exit_codes(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._write_plan(
                root,
                [
                    # ALPHA and BETA deliberately contend for the scaffolds of a
                    # new tests/suite package, which is what drives the exit
                    # code 1 and the two scaffold-collision subjects asserted
                    # below.
                    node(
                        "ALPHA",
                        write_scope=["tests/suite/test_alpha.py"],
                        file_locks=["tests/suite/test_alpha.py"],
                    ),
                    node(
                        "BETA",
                        write_scope=["tests/suite/test_beta.py"],
                        file_locks=["tests/suite/test_beta.py"],
                    ),
                    node("SERIAL", dependencies=["ALPHA", "BETA"], parallel_safe=False),
                ],
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rounds_code = autopilot.main(
                    ["--repo-root", str(root), "dag-rounds", "--plan", str(plan), "--json"]
                )
            self.assertEqual(rounds_code, 0)
            document = json.loads(buffer.getvalue())
            # ALPHA and BETA are lock-disjoint and would pack into one round on
            # capacity alone, but the linter reports them as contending for the
            # tests/suite scaffolds, so the compiler must not co-schedule them.
            # A compiled round is never one dag-lint would reject.
            self.assertEqual(
                [item["nodes"] for item in document["rounds"]],
                [["ALPHA"], ["BETA"], ["SERIAL"]],
            )
            self.assertTrue(document["semantic_ordering"])

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                lint_code = autopilot.main(
                    ["--repo-root", str(root), "dag-lint", "--plan", str(plan), "--json"]
                )
            self.assertEqual(lint_code, 1)
            report = json.loads(buffer.getvalue())
            self.assertEqual(report["counts"]["error"], 2)
            self.assertEqual(
                sorted(
                    item["subject"]
                    for item in report["findings"]
                    if item["check"] == "scaffold-collision"
                ),
                ["tests/suite/__init__.py", "tests/suite/conftest.py"],
            )

    def test_no_semantic_ordering_refuses_a_cli_schedule_with_constraints(self) -> None:
        import autopilot

        nodes = [
            node("DURABLE", semantic_locks=["durability-qualification"]),
            node("MISSION", acceptance_criteria=["The system resumes after a crash."]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._write_plan(root, nodes)
            errors = io.StringIO()
            with redirect_stderr(errors):
                refused = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "dag-rounds",
                        "--plan",
                        str(plan),
                        "--json",
                        "--no-semantic-ordering",
                    ]
                )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                autopilot.main(
                    ["--repo-root", str(root), "dag-rounds", "--plan", str(plan), "--json"]
                )
            ordered = json.loads(buffer.getvalue())
        self.assertEqual(refused, 2)
        self.assertIn("no-semantic-ordering refuses", errors.getvalue())
        self.assertEqual(
            [item["nodes"] for item in ordered["rounds"]], [["DURABLE"], ["MISSION"]]
        )

    def test_strict_mode_promotes_warnings_to_a_failing_exit_code(self) -> None:
        import autopilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self._write_plan(root, [node("ALPHA", read_scope=["**"])])
            with redirect_stdout(io.StringIO()):
                relaxed = autopilot.main(
                    ["--repo-root", str(root), "dag-lint", "--plan", str(plan)]
                )
                strict = autopilot.main(
                    [
                        "--repo-root",
                        str(root),
                        "dag-lint",
                        "--plan",
                        str(plan),
                        "--strict",
                    ]
                )
        self.assertEqual((relaxed, strict), (0, 1))


if __name__ == "__main__":
    unittest.main()
