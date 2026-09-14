# Autonomous repository service

1. Create a host-owned repository profile and mission binding descriptor. Store
   credential handles—not credential values—in that descriptor.
2. Compile the desired `OutcomeGraphSpec` and configure a private state directory.
3. Implement `WholeOSHost.execute_package` using the admitted execution,
   verification, delivery, and learning adapters.
4. Construct `WholeOSService`, then call `run_once()` from the host supervisor until
   `observe().status` is `complete`, `blocked`, or `dependency_wait`.
5. On restart, reconstruct the same descriptor, graph, state directory, and host.
   The scheduler resumes completed and retryable work without copied chat context.

External effects remain subject to the profile's authority grant and operation-ID
reconciliation. Missing authority or runtime access is a typed blocked result, never
permission to widen scope.
