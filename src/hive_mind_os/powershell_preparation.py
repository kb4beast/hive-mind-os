"""Inert PowerShell preparation for portable DAG inspection.

The returned text is never executed by this module. It contains only read-only
validation/round/status commands and an explicit stop before activation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


class PowerShellPreparationError(ValueError):
    """A requested preparation would be ambiguous or executable beyond scope."""


_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _quote(value: str) -> str:
    if not value or any(character in value for character in ("\x00", "\r", "\n")):
        raise PowerShellPreparationError("PowerShell values must be non-empty single-line text")
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True, slots=True)
class PowerShellPreparation:
    subject: str
    plan_path: str
    standard_path: str
    expected_plan_digest: str
    state_directory: str
    execution_client_path: str
    execution_client_digest: str
    text: str

    @property
    def sha256(self) -> str:
        return "sha256:" + sha256(self.text.encode("utf-8")).hexdigest()

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "hive-mind-inert-powershell-preparation-v1",
            "subject": self.subject,
            "plan_path": self.plan_path,
            "standard_path": self.standard_path,
            "expected_plan_digest": self.expected_plan_digest,
            "state_directory": self.state_directory,
            "execution_client_path": self.execution_client_path,
            "execution_client_digest": self.execution_client_digest,
            "execution_client_scope": (
                "Exact launcher bytes only; the operator and frozen-host attestation "
                "must separately bind the installed package and dependencies."
            ),
            "sha256": self.sha256,
            "execution_authorized": False,
            "forbidden_effects": [
                "credential acquisition", "identity attestation", "signature",
                "terms acceptance", "spending", "push", "merge", "deployment",
                "production mutation", "authority expansion",
            ],
        }


def prepare_read_only_powershell(
    *, subject: str, plan_path: str | Path, expected_plan_digest: str,
    state_directory: str | Path, execution_client_path: str | Path,
    expected_execution_client_digest: str,
    standard_path: str | Path | None = None,
) -> PowerShellPreparation:
    """Return bounded operator text; perform no filesystem or process effect."""

    subject_text = str(subject).strip()
    if not subject_text:
        raise PowerShellPreparationError("subject is required")
    if _DIGEST.fullmatch(expected_plan_digest) is None:
        raise PowerShellPreparationError("expected plan digest is invalid")
    if _DIGEST.fullmatch(expected_execution_client_digest) is None:
        raise PowerShellPreparationError("expected execution client digest is invalid")
    plan_input = Path(plan_path)
    if not plan_input.is_absolute():
        raise PowerShellPreparationError("plan_path must be absolute")
    plan = str(plan_input.resolve())
    if standard_path is None:
        standard_path = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "execution"
            / "DAG_AUTHORING_STANDARD_V2.md"
        )
    standard_input = Path(standard_path)
    if not standard_input.is_absolute():
        raise PowerShellPreparationError("standard_path must be absolute")
    state_input = Path(state_directory)
    if not state_input.is_absolute():
        raise PowerShellPreparationError("state_directory must be absolute")
    standard = str(standard_input.resolve())
    state = str(state_input.resolve())
    client_input = Path(execution_client_path)
    if not client_input.is_absolute():
        raise PowerShellPreparationError("execution_client_path must be absolute")
    try:
        client_path = client_input.resolve(strict=True)
        client_bytes = client_path.read_bytes()
    except OSError as error:
        raise PowerShellPreparationError(
            "execution_client_path must name a readable file"
        ) from error
    if not client_path.is_file():
        raise PowerShellPreparationError("execution_client_path must name a file")
    client_digest = "sha256:" + sha256(client_bytes).hexdigest()
    if client_digest != expected_execution_client_digest:
        raise PowerShellPreparationError(
            "execution client bytes do not match the caller-authenticated digest"
        )
    text = "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            "$plan = " + _quote(plan),
            "$standard = " + _quote(standard),
            "$state = " + _quote(state),
            "$subject = " + _quote(subject_text),
            "$digest = " + _quote(expected_plan_digest),
            "$client = " + _quote(str(client_path)),
            "$clientDigest = " + _quote(client_digest),
            "function Assert-BoundExecutionClient {",
            "    if (-not (Test-Path -LiteralPath $client -PathType Leaf)) { throw 'Bound execution client is missing.' }",
            "    $observedClientDigest = 'sha256:' + (Get-FileHash -LiteralPath $client -Algorithm SHA256).Hash.ToLowerInvariant()",
            "    if ($observedClientDigest -cne $clientDigest) { throw 'Bound execution client digest changed.' }",
            "}",
            "Assert-BoundExecutionClient",
            "& $client 'dag' 'validate' '--plan' $plan '--standard' $standard '--subject' $subject '--expected-plan-digest' $digest",
            "if ($LASTEXITCODE -ne 0) { throw 'Bound validation client failed.' }",
            "Assert-BoundExecutionClient",
            "& $client 'dag' 'rounds' '--plan' $plan '--standard' $standard '--subject' $subject '--expected-plan-digest' $digest",
            "if ($LASTEXITCODE -ne 0) { throw 'Bound rounds client failed.' }",
            "Assert-BoundExecutionClient",
            "& $client 'dag' 'status' '--plan' $plan '--state-directory' $state '--expected-plan-digest' $digest",
            "if ($LASTEXITCODE -ne 0) { throw 'Bound status client failed.' }",
            "Write-Output 'Preparation complete. No activation, signature, credential, push, merge, deployment, or production effect was attempted.'",
            "# STOP: execution requires a separately authenticated one-run activation capability.",
            "",
        )
    )
    return PowerShellPreparation(
        subject_text,
        plan,
        standard,
        expected_plan_digest,
        state,
        str(client_path),
        client_digest,
        text,
    )
