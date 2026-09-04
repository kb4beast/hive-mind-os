from __future__ import annotations

from .agents import AGENT_TYPES, RoleContract, canonical_roles
from .models import Role

# This facade remains independent of the optional extension catalog.  The role
# contracts themselves are owned by their direct implementation classes.
ROLE_CONTRACTS: dict[Role, RoleContract] = {
    agent_type.role: agent_type.contract for agent_type in AGENT_TYPES
}

DEFAULT_LIFECYCLE: tuple[Role, ...] = canonical_roles()

# The architecture retains all eight specialist contracts.  Only these roles have
# executable repository-mission capabilities today; the remainder are planned.
IMPLEMENTED_REPOSITORY_ROLES: tuple[Role, ...] = (
    Role.EXPLORER,
    Role.BUILDER,
    Role.CURATOR,
)
PLANNED_ROLES: tuple[Role, ...] = tuple(
    role for role in Role if role not in IMPLEMENTED_REPOSITORY_ROLES
)
