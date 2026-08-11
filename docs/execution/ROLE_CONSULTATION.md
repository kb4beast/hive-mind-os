# Role-first consultation

Status: version 1, bounded and fail-closed.

Before a worker asks a human a question, it creates a typed
`ConsultationRequest` and routes it to at least two applicable roles. The
request classifies one of: ambiguous design, missing evidence, missing
external authority, unsafe effect, independence concern, suspected cheating,
or no progress. Role identities are procedural/model identities; they are not
independent humans and cannot claim to be one.

## Decisions

The role council may return `RESOLVED`, `REMAND`, `REPLAN`,
`BLOCKED_EVIDENCE`, `QUARANTINE`, or `TRUE_AUTHORITY_REQUIRED`. Only the last
decision sets `human_escalation` to true. It is valid only for a declared
genuine authority class (credential or secret, legal or regulatory signoff,
financial spend, production access, protected-branch merge, owner value choice,
personal consent, or an external contractual commitment) and retained
evidence. A software defect, ambiguity, missing repository evidence, or
reversible implementation choice is never converted into a human question.

## Anti-cheating boundary

Suspected cheating is evidence-bound. Confirmed cheating quarantines the work;
unresolved cheating also quarantines it. Disproved cheating may resolve only
when the council retains evidence supporting the disproof. The protocol rejects
role testimony that claims credentials, consent, legal approval, production
authority, or external facts without evidence. It also rejects identity records
that present a model/procedural role as an independent human.

## Bounded loop and provenance

`ConsultationLoop` retains every immutable result in order and permits at most
three contiguous rounds. Exhaustion is a stop condition, not permission to ask
the owner to adjudicate a software defect. Every result retains consulted roles,
identity records, evidence references, dissent, decision, and cheating
disposition. Rejected or dissenting testimony is not discarded.

Rollback is to revert the exact node commit while preserving the consultation
records and adverse evidence.

## Active execution blocker

CONSULT-210 was paused when the singleton advanced from
`fabfa1e7532a2e7da81d5dc0b792f28238cd692f` to
`cef89b42044febb078a4d5e767917a940c153dbe`. The approved snapshot source at
`C:\Repos\HiveMind\hive-mind-os-singleton-release-r2\.autopilot\state\github-state.json`
still binds the old target. Blocker packet:
`sha256:26558d4b414bdd0a6875f05640a79b1a42df8ff09bddfdb93860bd44ef4a510d`.

Retry only after the controller refreshes that approved snapshot with the exact
new target, the unchanged file is copied and installed, reconciliation and
doctor/status pass, a fresh dispatch assigns `START NOW`, and the untouched
stale remote claim branch is verified/released before a new claim. TLS,
certificate revocation, provenance, authority, and protected-branch controls
must remain enabled.

The global `python -m unittest discover -s tests -v` attempt on the refreshed
claim was stopped when the controller reported that ACCEPT-240 owned the
repository-wide validation lease. This is a non-verdict timeout/lease receipt,
not a test result. CONSULT-210 remains ready for the next granted global CI
slot; focused consultation tests and static checks remain the applicable local
evidence until then.
