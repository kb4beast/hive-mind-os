# Autonomous repository service

1. Create a host-owned repository profile and mission binding descriptor. Store
   credential handles—not credential values—in that descriptor.
2. Compile the desired `OutcomeGraphSpec` and configure a private state directory.
3. Implement `WholeOSHost.execute_package` using the admitted execution,
   verification, delivery, and learning adapters, then register its sealed
   `WholeOSHostFactoryRegistration` from trusted launcher code in the same process.
   The `run_registered_whole_os` helper is the supported launcher API. Configuration
   must contain no import paths, commands, credential values, or secrets.
4. Invoke the deployment's launcher with `start --config <service.json>`. The same
   launcher may be resumed with `resume --config <service.json>`; the durable service
   executes only work not already receipted. A standalone stock `hive-mind whole-os
   start` has an empty registry and truthfully returns `blocked_capability`.
5. On restart, reconstruct the same descriptor, graph, state directory, and host.
   The scheduler resumes completed and retryable work without copied chat context.

External effects remain subject to the profile's authority grant and operation-ID
reconciliation. Missing authority or runtime access is a typed blocked result, never
permission to widen scope.
