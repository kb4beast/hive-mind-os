# Whole-OS adversarial failure matrix

`whole_os_qualification.FailurePoint` defines the mandatory interruption points for
every durable effect: before intent, after intent, after effect before receipt,
after receipt before transition, lease expiry, and stale worker return.

`AdversarialReport` rejects incomplete matrices, cross-candidate evidence, failed
healthy controls, accepted negative controls, and more than one resulting effect.
Reports separately retain real-backend evidence and residual risks.

The implemented test artifact is synthetic. Disposable-real-service probes, OS
isolation attestations, secret/egress probes, and an independent exact-candidate
disposition remain unexecuted qualification work.
