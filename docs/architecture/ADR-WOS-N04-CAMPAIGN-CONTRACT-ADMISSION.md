# ADR-WOS-N04 — Campaign-contract admission and kernel event adapter

Status: implementation candidate; independent rereview required.

N04 campaign records are inert, versioned admission data. They use closed schema v1
and strict bounded JSON parsing. The sole retained historical fixture is version 0,
`tests/fixtures/campaign_contracts/historical-v0.json`; it is readable only with
explicit fixture mode and is never a production mission admission payload.

N04 does not extend kernel lifecycle enums. `campaign_state_event` emits the actual
`mission.created` or `mission.transition` event types and `MissionState` payloads;
`package_state_event` emits `work.created` or `work.transition` and `WorkState`
payloads. Rollback selects the pre-N04 admission boundary and retains all fixture,
schema, and candidate bytes as evidence.
