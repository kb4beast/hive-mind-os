"""Immutable, evidence-only VPR remand contracts and ledger-parser rules."""
from __future__ import annotations

import re
from collections import Counter

EVALUATED_COMMIT = "b789b68e7d6a741e0b85a3ac33cbce846e1e32c9"
EVALUATED_TREE = "b909b7b7e374bff22912059387ef0fe639498af6"
REJECTED_TUPLES = (
    ("20e26e3c53d41ec4093b23f0957766cd0cbdab70", "f454db6d64120c946ae6700bcf4b4b6ea1bef26c"),
    ("20e26e3c53d41ec4093b23f0957766cd0cbdab70", "4f20bd2"),
)
DAG_DIR = "docs/execution/dags/validation-provenance-remand-v1"
EVIDENCE = "evidence/performance/validation-provenance-remand-v1"
OPENING = "evidence/courts/CASE-VALIDATION-PROVENANCE-REMAND-OPENING.json"
QUALIFICATION = "evidence/courts/CASE-VALIDATION-PROVENANCE-REMAND-QUALIFICATION.json"
VTC_QUALIFICATION = "evidence/courts/CASE-VALIDATION-TARGET-COMPOSITION-QUALIFICATION.json"
FPCR_DISCOVERY = "evidence/performance/fixture-prerequisite-causality-reseal-v2/discovery-analysis.json"
FPCR_EXECUTION = "evidence/performance/fixture-prerequisite-causality-reseal-v2/execution.json"
FPCR_TRANSCRIPT = "evidence/performance/fixture-prerequisite-causality-reseal-v2/execution-transcript.json"
FPCR_CROSS = "evidence/performance/fixture-prerequisite-causality-reseal-v2/cross-examination.json"
VTC_DISCOVERY = "evidence/performance/validation-target-composition-v1/discovery-analysis.json"
VTC_CROSS = "evidence/performance/validation-target-composition-v1/cross-examination.json"
VTC_INTEGRATION = "evidence/performance/validation-target-composition-v1/integration.json"
ADVERSE = [VTC_QUALIFICATION, FPCR_DISCOVERY, FPCR_EXECUTION, FPCR_TRANSCRIPT, FPCR_CROSS, VTC_DISCOVERY, VTC_CROSS, VTC_INTEGRATION, "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json"]
COMMON_FORBIDDEN = [
    ".autopilot/plan.json", ".autopilot/bin/**", ".autopilot/tests/**", "tests/**", "src/**", "pyproject.toml",
    "docs/execution/dags/validation-target-composition-v1/**", "docs/execution/dags/fixture-prerequisite-v1/**",
    "docs/execution/dags/fixture-prerequisite-causality-appeal-v1/**", "docs/execution/dags/fixture-prerequisite-causality-reseal-v2/**",
    "docs/execution/dags/git-commit-observation-v1/**", "docs/execution/dags/doctor-performance-v1/**",
    "evidence/performance/doctor-performance-v1/**", "refs/heads/main", "refs/remotes/origin/**",
]

# Header shape intentionally captures unittest's canonical ID inside parentheses.
HEADER = re.compile(r"^.+ \((?P<id>[A-Za-z_][\w.]*)\) \.\.\.(?: (?P<label>.*))?$")
DEFAULT_LABELS = frozenset({"ok", "FAIL", "ERROR", "skipped", "expected failure", "unexpected success"})
WARNING_PREFIXES = ("WARNING:", "warning:", "ResourceWarning:", "DeprecationWarning:")

class LedgerParseError(ValueError):
    """The retained evidence cannot produce a complete, unambiguous ledger."""

def parse_outcome_ledger(lines, discovery_ids, custom_labels=()):
    """Fail-closed transcript state machine.

    States are IDLE and AWAITING_TERMINAL.  A canonical unittest header enters
    AWAITING_TERMINAL. Warning lines may interleave without changing state. A
    terminal label on that header binds exactly one discovery ID. Any malformed
    line while awaiting a terminal, an unknown ID, a duplicate binding, a
    terminal label outside the declared default/custom vocabulary, or any
    missing discovery ID raises LedgerParseError. Custom labels must be passed
    explicitly by the caller so labels in historical text never gain meaning by
    accident.
    """
    expected = tuple(discovery_ids)
    if not expected or len(set(expected)) != len(expected):
        raise LedgerParseError("discovery vector must be non-empty and unique")
    expected_set, allowed = set(expected), DEFAULT_LABELS | set(custom_labels)
    outcomes, pending = {}, None
    for raw in lines:
        line = raw.rstrip("\r\n")
        match = HEADER.match(line)
        if pending is None:
            if match is None:
                continue
            ident, label = match.group("id"), match.group("label")
            if ident not in expected_set:
                raise LedgerParseError("header ID is outside discovery vector: " + ident)
            if label in allowed:
                if ident in outcomes:
                    raise LedgerParseError("duplicate binding: " + ident)
                outcomes[ident] = label
            elif label in (None, ""):
                pending = ident
            else:
                raise LedgerParseError("unknown terminal label: " + label)
            continue
        if line.startswith(WARNING_PREFIXES):
            continue
        if match is not None:
            raise LedgerParseError("new header before pending terminal: " + pending)
        if line not in allowed:
            raise LedgerParseError("invalid pending terminal label: " + line)
        if pending in outcomes:
            raise LedgerParseError("duplicate binding: " + pending)
        outcomes[pending], pending = line, None
    if pending is not None:
        raise LedgerParseError("missing terminal label: " + pending)
    missing = [ident for ident in expected if ident not in outcomes]
    if missing:
        raise LedgerParseError("unbound discovery IDs: " + ",".join(missing))
    if len(outcomes) != len(expected):
        raise LedgerParseError("non-bijective ledger")
    return {"ordered_ids": list(expected), "outcomes": outcomes, "counts": dict(sorted(Counter(outcomes.values()).items()))}

def node(ident, title, objective, rationale, dependencies, role, seat, inputs, outputs, read_scope, tests, parallel, locks, importance):
    return {"id":ident,"title":title,"objective":objective,"rationale":rationale,"dependencies":dependencies,"primary_role":role,"court_seat":seat,"consulted_roles":["curator","steward"],"required_inputs":inputs,"expected_outputs":outputs,"read_scope":read_scope,"write_scope":outputs,"required_tests":tests,"acceptance_criteria":["Bind only exact b789/b909 and retain input receipt/transcript digests.","Write only the declared contract or evidence artifact.","No CI/candidate execution, source/test/plan mutation, main checkout/update, or remote effect occurs.","No result authorizes implementation, candidate use, promotion, performance, or baseline retry."],"parallel_safe":parallel,"semantic_locks":locks,"critical_path_importance":importance,"stopping_condition":"Required checks pass, the sole declared artifact is retained, and no out-of-scope path changed.","rollback":"Revert only this node's retained contract or evidence commit; never delete prior adverse evidence."}

SEAL = [f"{DAG_DIR}/.gitignore",f"{DAG_DIR}/README.md",f"{DAG_DIR}/specs.py",f"{DAG_DIR}/generate_plan.py",f"{DAG_DIR}/verify_plan.py",f"{DAG_DIR}/manifest.json",OPENING,f"{EVIDENCE}/"]
SPECS = [
 node("VPR-SEAL-000", "Seal validation provenance remand", "As Clerk, seal a five-node evidence-only remand before any ledger evaluation.", "VTC deferred solely because an ordered per-ID outcome ledger was absent; VPR may reduce that provenance uncertainty only.", [], "orchestrator", "clerk-distinct", ["AGENTS.md", "docs/execution/DAG_AUTHORING_STANDARD.md", VTC_QUALIFICATION, *ADVERSE], SEAL, ["AGENTS.md", "docs/execution/DAG_AUTHORING_STANDARD.md", VTC_QUALIFICATION, *ADVERSE], [f"python {DAG_DIR}/verify_plan.py"], False, ["contract:vpr-v1"], 100),
 node("VPR-LEDGER-010", "Build ordered outcome ledger", "As independent Explorer, evaluate the retained transcript through the sealed fail-closed parser and bind every retained discovery ID exactly once, or record failure without inference.", "An aggregate delta is not an executable provenance ledger. The parser must preserve warning interleaving and explicit custom-label provenance.", ["VPR-SEAL-000"], "explorer", "independent-explorer", [f"{DAG_DIR}/specs.py", FPCR_DISCOVERY, FPCR_TRANSCRIPT, VTC_DISCOVERY], [f"{EVIDENCE}/ordered-outcome-ledger.json", f"{EVIDENCE}/ledger-replay.json"], [f"{DAG_DIR}/specs.py", FPCR_DISCOVERY, FPCR_TRANSCRIPT, VTC_DISCOVERY], [f"python {DAG_DIR}/verify_plan.py"], True, ["evidence:vpr-ledger"], 95),
 node("VPR-CROSS-020", "Cross-examine provenance remand", "As separate Cross-Examiner, challenge parser completeness, custom-label treatment, source binding, and any claim that a ledger changes implementation authority.", "A parseable transcript may still be incomplete or ambiguously labeled; fail closed rather than fabricate bindings.", ["VPR-SEAL-000"], "curator", "cross-examiner-distinct", [f"{DAG_DIR}/specs.py", VTC_QUALIFICATION, FPCR_DISCOVERY, FPCR_TRANSCRIPT, VTC_CROSS], [f"{EVIDENCE}/cross-examination.json"], [f"{DAG_DIR}/specs.py", VTC_QUALIFICATION, FPCR_DISCOVERY, FPCR_TRANSCRIPT, VTC_CROSS], [f"python {DAG_DIR}/verify_plan.py"], True, ["evidence:vpr-cross"], 90),
 node("VPR-INTEGRATE-030", "Integrate provenance evidence", "As Integrator, reconcile the ledger evaluation and cross-examination into a bounded applicability record with all adverse findings retained.", "Only independent reconciliation can state whether provenance uncertainty was reduced; it cannot make a remediation applicable.", ["VPR-LEDGER-010", "VPR-CROSS-020"], "integrator", "integrator-distinct", [f"{EVIDENCE}/ordered-outcome-ledger.json", f"{EVIDENCE}/ledger-replay.json", f"{EVIDENCE}/cross-examination.json", VTC_QUALIFICATION], [f"{EVIDENCE}/integration.json"], [f"{EVIDENCE}/ordered-outcome-ledger.json", f"{EVIDENCE}/ledger-replay.json", f"{EVIDENCE}/cross-examination.json", VTC_QUALIFICATION], [f"python {DAG_DIR}/verify_plan.py"], False, ["integration:vpr"], 80),
 node("VPR-JUDGE-040", "Judge validation provenance remand", "As a Judge distinct from all prior VPR roles, decide only whether provenance uncertainty was reduced and retain all remaining gates.", "Neither result may authorize implementation, a candidate, promotion, performance, CI, or baseline retry.", ["VPR-INTEGRATE-030"], "orchestrator", "judge-distinct-from-all-vpr-roles", [f"{EVIDENCE}/integration.json", f"{EVIDENCE}/cross-examination.json", VTC_QUALIFICATION], [QUALIFICATION], [f"{EVIDENCE}/integration.json", f"{EVIDENCE}/cross-examination.json", VTC_QUALIFICATION], [f"python {DAG_DIR}/verify_plan.py"], False, ["court:vpr-verdict"], 70),
]
