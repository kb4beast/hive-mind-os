[CmdletBinding()]
param(
    [string]$RepoRoot = (Join-Path $PSScriptRoot "..\.."),
    [string]$Node = "ARCH-100",
    [string]$Owner = "codex:arch-100"
)

$ErrorActionPreference = "Stop"

# QUARANTINED: this script used to dispatch a release and then invoke the local
# claim CLI as though that created an attended Codex task.  The attended host is
# deliberately a card/receipt adapter; it cannot authenticate, launch, inspect,
# or bind a cloud session.  Consequently a release could be published even
# though no usable worker authority existed.  It also read a target-branch path
# that is not the singleton release authority.
#
# Do not restore any side effect here until recovery has a host integration that
# atomically authenticates the host task and binds its capability to the exact
# release before dispatch publication.  This guard intentionally runs before
# repository resolution, Git, snapshotting, doctor, dispatch, or claim actions.
throw (
    "Singleton recovery is quarantined: no authenticated attended-host launch/bind " +
    "flow exists for node '$Node'. No release, claim, Git, or repository action " +
    "was attempted. Preserve this blocker and use the normal capability-bound " +
    "dispatcher path after host authority is available."
)
