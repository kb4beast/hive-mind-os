"""Immutable contracts for the forward-looking receipt-capture design court."""
from __future__ import annotations

AUTHORITY_COMMIT = "89f1a44a9687d351eae52633d015fc55948005fd"
AUTHORITY_TREE = "bb649cca210b0fa2d2161395e33e6a3b58041b76"
DAG_DIR = "docs/execution/dags/receipt-capture-design-v1"
ARCHITECTURE = "evidence/architecture/receipt-capture-design-v1"
OPENING = "evidence/courts/CASE-RECEIPT-CAPTURE-DESIGN-OPENING.json"
QUALIFICATION = "evidence/courts/CASE-RECEIPT-CAPTURE-DESIGN-QUALIFICATION.json"
PREDECESSOR = "evidence/courts/CASE-VALIDATION-PROVENANCE-REMAND-QUALIFICATION.json"
ADVERSE = [
    PREDECESSOR,
    "evidence/courts/CASE-VALIDATION-TARGET-COMPOSITION-QUALIFICATION.json",
    "evidence/performance/validation-provenance-remand-v1/integration.json",
    "evidence/performance/fixture-prerequisite-causality-reseal-v2/execution.json",
    "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
]
REJECTED_CANDIDATES = {
    "fixture": "41950b74bdec2b6e1c48ee7f5ef3ce947d0c8378",
    "gco": "d02c2d2",
}
COMMON_FORBIDDEN = [
    ".autopilot/plan.json", ".autopilot/bin/**", ".autopilot/tests/**", "tests/**", "src/**", "pyproject.toml",
    "docs/execution/dags/validation-provenance-remand-v1/**", "docs/execution/dags/validation-target-composition-v1/**",
    "docs/execution/dags/fixture-prerequisite-v1/**", "docs/execution/dags/git-commit-observation-v1/**",
    "refs/heads/main", "refs/remotes/origin/**",
]
DESIGN_REQUIREMENTS = [
    "ordered_discovery_vector",
    "one_terminal_outcome_per_id_including_lifecycle_and_class_skips",
    "declared_and_hashed_label_vocabulary",
    "raw_stream_hashes_and_explicit_parser_grammar",
    "summary_reconciliation",
    "source_tree_interpreter_and_environment_binding",
    "privacy_sensitive_redaction",
    "atomic_receipt_write_and_retention",
    "failure_and_rollback",
]

def node(ident, title, objective, rationale, dependencies, role, seat, inputs, outputs, reads, parallel, locks, importance):
    return {
        "id": ident, "title": title, "objective": objective, "rationale": rationale,
        "dependencies": dependencies, "primary_role": role, "court_seat": seat,
        "consulted_roles": ["steward", "curator"], "required_inputs": inputs,
        "expected_outputs": outputs, "read_scope": reads, "write_scope": outputs,
        "required_tests": [f"python {DAG_DIR}/verify_plan.py"], "parallel_safe": parallel,
        "semantic_locks": locks, "critical_path_importance": importance,
        "acceptance_criteria": [
            "Write only the declared contract or design evidence artifact.",
            "Do not execute CI, unittest discovery, a candidate, or a performance measurement.",
            "Do not change source, tests, fixtures, controllers, .autopilot/plan.json, main, or remotes.",
            "Retain adverse evidence; do not reuse, relabel, qualify, or compose 41950 or d02.",
            "No result directly authorizes implementation.",
        ],
        "stopping_condition": "The required verifier passes, the sole declared artifact is retained, and no out-of-scope path changed.",
        "rollback": "Revert only this node's retained contract or design receipt; preserve all prior adverse evidence append-only.",
    }

# The Clerk owns the new architecture directory before the two parallel writers
# are released.  This declared scaffold has no committed marker file.
SEAL = [f"{DAG_DIR}/.gitignore", f"{DAG_DIR}/README.md", f"{DAG_DIR}/specs.py", f"{DAG_DIR}/generate_plan.py", f"{DAG_DIR}/verify_plan.py", f"{DAG_DIR}/manifest.json", OPENING, f"{ARCHITECTURE}/"]
SPECS = [
    node("RCD-SEAL-000", "Seal receipt-capture design court", "As Clerk, seal a five-node forward-looking design court before any design work.", "VPR permits only a newly sealed design court, not implementation.", [], "orchestrator", "clerk-distinct", ["AGENTS.md", "docs/execution/DAG_AUTHORING_STANDARD.md", PREDECESSOR, *ADVERSE], SEAL, ["AGENTS.md", "docs/execution/DAG_AUTHORING_STANDARD.md", PREDECESSOR, *ADVERSE], False, ["contract:receipt-capture-design-v1"], 100),
    node("RCD-ARCH-010", "Specify receipt recorder contract", "As independent Architect, specify a native future recorder contract covering every sealed receipt-capture requirement.", "The historical failure identifies a future design obligation, not a historical target to repair.", ["RCD-SEAL-000"], "architect", "architect-distinct", [f"{DAG_DIR}/specs.py", PREDECESSOR, *ADVERSE], [f"{ARCHITECTURE}/architecture.json"], [f"{DAG_DIR}/specs.py", PREDECESSOR, *ADVERSE], True, ["design:receipt-recorder-contract"], 95),
    node("RCD-CROSS-020", "Cross-examine receipt recorder design", "As separate Curator/Cross-Examiner, assess privacy, security, retention, parser ambiguity, atomicity, and rollback risks in the proposed future receipt contract.", "A recorder can create sensitive data or false certainty unless its boundaries are independently challenged.", ["RCD-SEAL-000"], "curator", "cross-examiner-distinct", [f"{DAG_DIR}/specs.py", PREDECESSOR, *ADVERSE], [f"{ARCHITECTURE}/cross-examination.json"], [f"{DAG_DIR}/specs.py", PREDECESSOR, *ADVERSE], True, ["design:receipt-recorder-cross"], 90),
    node("RCD-INTEGRATE-030", "Integrate receipt-capture design", "As Integrator, reconcile the architecture and cross-examination into a bounded implementation-readiness record.", "The Judge needs explicit disposition of every material design challenge before considering a later proposal court.", ["RCD-ARCH-010", "RCD-CROSS-020"], "integrator", "integrator-distinct", [f"{ARCHITECTURE}/architecture.json", f"{ARCHITECTURE}/cross-examination.json", PREDECESSOR], [f"{ARCHITECTURE}/integration.json"], [f"{ARCHITECTURE}/architecture.json", f"{ARCHITECTURE}/cross-examination.json", PREDECESSOR], False, ["integration:receipt-capture-design"], 80),
    node("RCD-JUDGE-040", "Judge receipt-capture design", "As a Judge distinct from every RCD worker, decide whether a separate native implementation-proposal DAG may be opened; never implement here.", "VPR requires later separately sealed authority, and zero unresolved material design findings is the minimum opening condition.", ["RCD-INTEGRATE-030"], "orchestrator", "judge-distinct-from-all-rcd-roles", [f"{ARCHITECTURE}/integration.json", f"{ARCHITECTURE}/cross-examination.json", PREDECESSOR], [QUALIFICATION], [f"{ARCHITECTURE}/integration.json", f"{ARCHITECTURE}/cross-examination.json", PREDECESSOR], False, ["court:receipt-capture-design-verdict"], 70),
]
