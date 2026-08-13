"""GRANT-1020: delivery grants are attributable and finite.

Every test here is in-process.  No socket is opened, no credential is read,
and the REST and push seams are stand-ins that fail the test if a refusal ever
reaches them.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from hive_mind_os.brain_kernel.authority import AuthorityRegistry, RootProvenance
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import Budget, ConstraintEnvelope
from hive_mind_os.cortex.github import grants
from hive_mind_os.cortex.github.delivery_adapter import ControlledGitHubDelivery
from hive_mind_os.cortex.github.grants import (
    DEFAULT_GRANT_LIFETIME,
    MAX_GRANT_LIFETIME,
    SELF_ISSUED,
    DeliveryGrant,
    DeliveryGrantError,
    DeliveryGrantLedger,
)

DIGEST = "sha256:" + "0" * 64
OWNER = "octo"
REPOSITORY = "repo"
BASE_BRANCH = "main"
BRANCH_PREFIX = "grant-1020/"
RUN_BRANCH = "grant-1020/work"
ISSUED = "2030-01-01T00:00:00Z"
EXPIRES = "2030-01-02T00:00:00Z"
ALL_ACTIONS = (
    "push",
    "open_draft_pr",
    "post_comment",
    "close_own_pr",
    "delete_own_branch",
)


def _envelope(authority_id: str = "AUTH-grant-1020") -> ConstraintEnvelope:
    return ConstraintEnvelope(
        authority_id,
        "MISSION-grant-1020",
        "WORK-grant-1020",
        None,
        "builder",
        "R1",
        ("push", "open_draft_pr", "post_comment"),
        ("merge", "deploy"),
        ("workspace",),
        ("workspace",),
        (),
        (),
        (),
        (),
        Budget(30, 0, 0, 0, 0, 0, 1, 1),
        "2030-01-02T00:00:00Z",
        DIGEST,
        DIGEST,
    ).sealed()


def _minted_root(
    *,
    authority_id: str = "AUTH-grant-1020",
    issuer: str = "repository-owner",
    authority_ref: str = "OWNER-DELEGATION-1020",
) -> RootProvenance:
    """Return a root provenance the kernel registry actually recorded."""

    return AuthorityRegistry().mint_root(
        _envelope(authority_id),
        issuer=issuer,
        authority_ref=authority_ref,
        recorded_at="2029-12-31T00:00:00Z",
    )


def _outside_grant(**overrides: object) -> DeliveryGrant:
    """Mint a complete, correctly sealed grant without touching the issuance path.

    The payload is spelled out here rather than borrowed from the module under
    test, so the grant this returns carries a digest an attacker can compute on
    their own.  This is the A5-F6 P2.1 attack in its strongest form.
    """

    fields: dict[str, object] = {
        "grant_id": "GRANT-1020-outside",
        "owner": OWNER,
        "repository": REPOSITORY,
        "base_branch": BASE_BRANCH,
        "branch_prefix": BRANCH_PREFIX,
        "allowed_actions": ALL_ACTIONS,
        "issued_at": ISSUED,
        "expires_at": EXPIRES,
        "issuer": "an-issuer-the-repository-owner-never-named",
        "authority_ref": "an-authority-the-repository-owner-never-recorded",
    }
    fields.update(overrides)
    digest = canonical_digest(
        dict(fields, allowed_actions=list(fields["allowed_actions"]))  # type: ignore[arg-type]
    )
    return DeliveryGrant(
        fields["grant_id"],  # type: ignore[arg-type]
        fields["owner"],  # type: ignore[arg-type]
        fields["repository"],  # type: ignore[arg-type]
        fields["base_branch"],  # type: ignore[arg-type]
        fields["branch_prefix"],  # type: ignore[arg-type]
        fields["allowed_actions"],  # type: ignore[arg-type]
        fields["issued_at"],  # type: ignore[arg-type]
        digest,
        fields["expires_at"],  # type: ignore[arg-type]
        fields["issuer"],  # type: ignore[arg-type]
        fields["authority_ref"],  # type: ignore[arg-type]
    )


class _RefusingRest:
    """A REST seam that fails the test if a denial ever reaches the network."""

    def __init__(self) -> None:
        self.owner = OWNER
        self.repository = REPOSITORY

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"an unissued grant reached the REST gateway: {name}")


class _RefusingPush:
    def push(self, branch: str) -> str:
        raise AssertionError(f"an unissued grant reached the push executor: {branch}")


class _LedgerFixture(unittest.TestCase):
    """Each test runs against its own ledger; the process ledger is restored."""

    def setUp(self) -> None:
        self.addCleanup(setattr, grants, "LEDGER", grants.LEDGER)
        grants.LEDGER = DeliveryGrantLedger()

    @staticmethod
    def issue(**overrides: object) -> DeliveryGrant:
        parameters: dict[str, object] = {
            "grant_id": "GRANT-1020",
            "owner": OWNER,
            "repository": REPOSITORY,
            "base_branch": BASE_BRANCH,
            "branch_prefix": BRANCH_PREFIX,
            "allowed_actions": ALL_ACTIONS,
            "issued_at": ISSUED,
        }
        parameters.update(overrides)
        return DeliveryGrant.issue(**parameters)  # type: ignore[arg-type]


class UnissuedGrantTests(_LedgerFixture):
    def test_a_grant_the_ledger_never_admitted_authorizes_nothing(self) -> None:
        outside = _outside_grant()

        self.assertIsNone(grants.LEDGER.issuance(outside.grant_digest))
        for call in (
            lambda: outside.require("push", now=ISSUED),
            lambda: outside.require_push_branch(RUN_BRANCH, now=ISSUED),
            lambda: outside.require_own_run_branch(
                RUN_BRANCH, "delete_own_branch", now=ISSUED
            ),
        ):
            with self.subTest(call=call):
                with self.assertRaisesRegex(
                    DeliveryGrantError, "has no recorded issuance"
                ):
                    call()

    def test_a_grant_from_the_issuance_path_is_honoured(self) -> None:
        issued = self.issue(
            grant_id="GRANT-1020-outside",
            expires_at=EXPIRES,
        )

        issued.require("push", now=ISSUED)
        issued.require_push_branch(RUN_BRANCH, now=ISSUED)
        issued.require_own_run_branch(RUN_BRANCH, "delete_own_branch", now=ISSUED)
        self.assertIsNotNone(grants.LEDGER.issuance(issued.grant_digest))

    def test_every_delivery_adapter_refuses_an_unissued_grant(self) -> None:
        push_executor = _RefusingPush()
        delivery = ControlledGitHubDelivery(
            _outside_grant(),
            rest=_RefusingRest(),
            push_executor=push_executor,
        )
        intent = object()

        for adapter in (
            delivery.push_adapter,
            delivery.draft_pr_adapter,
            delivery.comment_adapter,
            delivery.close_pr_adapter,
            delivery.delete_branch_adapter,
        ):
            with self.subTest(adapter=adapter.__name__):
                with self.assertRaisesRegex(
                    DeliveryGrantError, "has no recorded issuance"
                ):
                    adapter(intent)  # type: ignore[arg-type]

    def test_an_issuance_recorded_under_other_fields_does_not_carry(self) -> None:
        issued = self.issue(expires_at=EXPIRES)
        forged = _outside_grant(
            grant_id=issued.grant_id,
            issuer=issued.issuer,
            authority_ref=issued.authority_ref,
            branch_prefix="anything/",
        )

        self.assertNotEqual(issued.grant_digest, forged.grant_digest)
        with self.assertRaisesRegex(DeliveryGrantError, "has no recorded issuance"):
            forged.require("push", now=ISSUED)


class AttributionTests(_LedgerFixture):
    def test_issuance_records_the_authority_the_grant_was_issued_under(self) -> None:
        root = _minted_root()
        grant = self.issue(provenance=root, expires_at=EXPIRES)
        record = grants.LEDGER.issuance(grant.grant_digest)

        assert record is not None
        self.assertEqual(root.issuer, record.issuer)
        self.assertEqual(root.authority_ref, record.authority_ref)
        self.assertEqual(root.record_digest, record.anchor_digest)
        self.assertEqual(root.issuer, grant.issuer)
        self.assertEqual(root.authority_ref, grant.authority_ref)
        self.assertEqual(
            canonical_digest(
                {
                    "grant": grant.grant_digest,
                    "issuer": root.issuer,
                    "authority_ref": root.authority_ref,
                    "recorded_at": record.recorded_at,
                    "anchor": root.record_digest,
                }
            ),
            record.record_digest,
        )

    def test_a_self_issued_grant_is_refused_once_the_owner_authority_is_anchored(
        self,
    ) -> None:
        self_issued = self.issue(expires_at=EXPIRES)
        self_issued.require("push", now=ISSUED)
        self.assertEqual(SELF_ISSUED, self_issued.issuer)

        grants.LEDGER.anchor(_minted_root())

        with self.assertRaisesRegex(
            DeliveryGrantError, "not issued under the recorded owner authority"
        ):
            self_issued.require("push", now=ISSUED)
        with self.assertRaisesRegex(
            DeliveryGrantError, "not issued under the recorded owner authority"
        ):
            self_issued.require_push_branch(RUN_BRANCH, now=ISSUED)

    def test_an_anchored_owner_still_issues_usable_grants(self) -> None:
        root = _minted_root()
        grants.LEDGER.anchor(root)
        grant = self.issue(provenance=root, expires_at=EXPIRES)

        grant.require("push", now=ISSUED)
        grant.require_push_branch(RUN_BRANCH, now=ISSUED)

    def test_self_issuance_is_refused_outright_while_an_anchor_stands(self) -> None:
        grants.LEDGER.anchor(_minted_root())

        with self.assertRaisesRegex(
            DeliveryGrantError, "not anchored to the recorded owner authority"
        ):
            self.issue(expires_at=EXPIRES)

    def test_issuance_under_a_foreign_authority_is_refused(self) -> None:
        grants.LEDGER.anchor(_minted_root())
        foreign = _minted_root(
            authority_id="AUTH-grant-1020-foreign",
            issuer="an-agent",
            authority_ref="AGENT-SELF-DELEGATION",
        )

        with self.assertRaisesRegex(
            DeliveryGrantError, "not anchored to the recorded owner authority"
        ):
            self.issue(provenance=foreign, expires_at=EXPIRES)

    def test_a_fabricated_owner_authority_record_is_refused(self) -> None:
        root = _minted_root()
        fabricated = RootProvenance(
            root.envelope_digest,
            "repository-owner",
            "OWNER-DELEGATION-1020",
            root.recorded_at,
            DIGEST,
        )

        for candidate in (fabricated, object(), None):
            with self.subTest(candidate=type(candidate).__name__):
                with self.assertRaises(DeliveryGrantError):
                    grants.LEDGER.anchor(candidate)  # type: ignore[arg-type]
        with self.assertRaisesRegex(
            DeliveryGrantError, "does not seal its fields"
        ):
            self.issue(provenance=fabricated, expires_at=EXPIRES)

    def test_the_anchored_owner_authority_cannot_be_replaced(self) -> None:
        root = _minted_root()
        grants.LEDGER.anchor(root)
        grants.LEDGER.anchor(_minted_root())

        with self.assertRaisesRegex(DeliveryGrantError, "cannot be replaced"):
            grants.LEDGER.anchor(
                _minted_root(
                    authority_id="AUTH-grant-1020-other",
                    issuer="an-agent",
                    authority_ref="AGENT-SELF-DELEGATION",
                )
            )
        self.assertEqual(root.record_digest, grants.LEDGER.anchor_digest)

    def test_a_grant_that_lies_about_its_issuer_is_never_recorded(self) -> None:
        root = _minted_root()
        claimant = _outside_grant(
            issuer=root.issuer, authority_ref=root.authority_ref
        )

        with self.assertRaisesRegex(
            DeliveryGrantError, "does not name the authority it was issued under"
        ):
            grants.LEDGER.record(claimant, provenance=None, recorded_at=ISSUED)
        self.assertIsNone(grants.LEDGER.issuance(claimant.grant_digest))


class ExpiryTests(_LedgerFixture):
    def test_an_expired_grant_is_refused_at_every_use(self) -> None:
        grant = self.issue(expires_at=EXPIRES)
        after = "2030-01-02T00:00:01Z"

        grant.require("push", now="2030-01-01T23:59:59Z")
        for call in (
            lambda: grant.require("push", now=after),
            lambda: grant.require_push_branch(RUN_BRANCH, now=after),
            lambda: grant.require_own_run_branch(
                RUN_BRANCH, "delete_own_branch", now=after
            ),
        ):
            with self.subTest(call=call):
                with self.assertRaisesRegex(DeliveryGrantError, "expired at"):
                    call()

    def test_expiry_is_refused_at_its_own_instant(self) -> None:
        grant = self.issue(expires_at=EXPIRES)

        with self.assertRaisesRegex(DeliveryGrantError, "expired at"):
            grant.require("push", now=EXPIRES)

    def test_an_elapsed_grant_is_refused_against_the_real_clock(self) -> None:
        elapsed = _stamp(datetime.now(timezone.utc) - timedelta(days=2))
        grant = self.issue(issued_at=elapsed)

        self.assertEqual(
            _stamp(_parse(elapsed) + DEFAULT_GRANT_LIFETIME), grant.expires_at
        )
        with self.assertRaisesRegex(DeliveryGrantError, "expired at"):
            grant.require("push")

    def test_a_grant_that_names_no_expiry_gets_a_finite_default(self) -> None:
        grant = self.issue()

        self.assertEqual("2030-01-02T00:00:00Z", grant.expires_at)
        self.assertEqual(
            DEFAULT_GRANT_LIFETIME, _parse(grant.expires_at) - _parse(grant.issued_at)
        )

    def test_a_lifetime_beyond_the_maximum_is_refused_at_issuance(self) -> None:
        over = _stamp(_parse(ISSUED) + MAX_GRANT_LIFETIME + timedelta(seconds=1))

        with self.assertRaisesRegex(DeliveryGrantError, "exceeds the maximum"):
            self.issue(expires_at=over)
        self.issue(expires_at=_stamp(_parse(ISSUED) + MAX_GRANT_LIFETIME))

    def test_an_expiry_that_does_not_follow_issuance_is_refused(self) -> None:
        for expiry in (ISSUED, "2029-12-31T23:59:59Z"):
            with self.subTest(expires_at=expiry):
                with self.assertRaisesRegex(
                    DeliveryGrantError, "expires_at must follow issued_at"
                ):
                    self.issue(expires_at=expiry)

    def test_an_unreadable_time_is_refused(self) -> None:
        for field, value in (
            ("expires_at", "not-a-time"),
            ("expires_at", "2030-01-02T00:00:00"),
            ("issued_at", "whenever"),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(DeliveryGrantError):
                    self.issue(**{field: value})


class SealTests(_LedgerFixture):
    def test_the_digest_seals_the_issuance_and_expiry_fields(self) -> None:
        sealed = self.issue(provenance=_minted_root(), expires_at=EXPIRES)
        replacements = (
            ("expires_at", "2030-01-07T00:00:00Z"),
            ("issuer", "an-agent"),
            ("authority_ref", "AGENT-SELF-DELEGATION"),
        )

        for field, value in replacements:
            with self.subTest(field=field):
                arguments = {
                    "expires_at": sealed.expires_at,
                    "issuer": sealed.issuer,
                    "authority_ref": sealed.authority_ref,
                }
                arguments[field] = value
                with self.assertRaisesRegex(
                    DeliveryGrantError, "digest does not seal its fields"
                ):
                    DeliveryGrant(
                        sealed.grant_id,
                        sealed.owner,
                        sealed.repository,
                        sealed.base_branch,
                        sealed.branch_prefix,
                        sealed.allowed_actions,
                        sealed.issued_at,
                        sealed.grant_digest,
                        arguments["expires_at"],
                        arguments["issuer"],
                        arguments["authority_ref"],
                    )

    def test_a_grant_carrying_no_issuance_or_expiry_fails_closed(self) -> None:
        sealed = self.issue(expires_at=EXPIRES)

        with self.assertRaises(DeliveryGrantError):
            DeliveryGrant(
                sealed.grant_id,
                sealed.owner,
                sealed.repository,
                sealed.base_branch,
                sealed.branch_prefix,
                sealed.allowed_actions,
                sealed.issued_at,
                sealed.grant_digest,
            )

    def test_two_grants_differing_only_in_authority_have_different_digests(
        self,
    ) -> None:
        self_issued = self.issue(expires_at=EXPIRES)
        owner_issued = self.issue(provenance=_minted_root(), expires_at=EXPIRES)

        self.assertNotEqual(self_issued.grant_digest, owner_issued.grant_digest)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    unittest.main()
