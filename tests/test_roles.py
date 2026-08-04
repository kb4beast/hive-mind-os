import inspect
import unittest

from hive_mind_os.mission import RepositoryMission
from hive_mind_os.models import Role
from hive_mind_os.policy import Action
from hive_mind_os.roles import (
    IMPLEMENTED_REPOSITORY_ROLES,
    PLANNED_ROLES,
    ROLE_CONTRACTS,
)


class RoleLifecycleTests(unittest.TestCase):
    def test_repository_lifecycle_lists_only_implemented_roles(self) -> None:
        self.assertEqual(
            IMPLEMENTED_REPOSITORY_ROLES,
            (Role.EXPLORER, Role.BUILDER, Role.CURATOR),
        )
        self.assertEqual(set(IMPLEMENTED_REPOSITORY_ROLES) | set(PLANNED_ROLES), set(Role))
        self.assertFalse(set(IMPLEMENTED_REPOSITORY_ROLES) & set(PLANNED_ROLES))

    def test_role_capabilities_resolve_to_policy_actions(self) -> None:
        for contract in ROLE_CONTRACTS.values():
            for capability in contract.default_capabilities:
                with self.subTest(role=contract.role, capability=capability):
                    self.assertIsInstance(Action(capability), Action)

    def test_public_mission_entrypoint_remains_small(self) -> None:
        self.assertLess(len(inspect.getsource(RepositoryMission.run).splitlines()), 200)
