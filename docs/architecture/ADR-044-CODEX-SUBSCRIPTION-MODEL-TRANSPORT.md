# ADR-044: Codex subscription model transport

- **Status:** Adopted by owner authority; implementation remains subject to review
- **Date:** 2026-08-06
- **Scope:** local, structured model turns through the signed-in Codex ChatGPT subscription
- **Supersedes:** only G2's 2026-08-04 no-real-model decision in ADR-043
- **Does not supersede:** `B-OPS-03`, `B-GOV-02`, `B-GOV-03`, `B-OPS-06`, or any deployment gate

## Context

Hive Mind's two structured HTTP transports require API-key environment variables. The
repository separately contains a local, signed-in Codex host path, but that path does not
implement the `ModelProvider` contract used by the kernel and `hive-mind deliver --backend
model`. The owner has authorized use of the local ChatGPT subscription and expressly
prohibited API billing.

OpenAI's published Codex guidance distinguishes ChatGPT sign-in for subscription access from
API-key sign-in for usage-based access. The implementation relies on the local `codex exec`
interface's documented sandbox, ephemeral-session, output-schema, and final-message options.
Source locators: <https://learn.chatgpt.com/docs/hipaa-configuration#codex-local-sign-in> and
<https://learn.chatgpt.com/docs/github-action#configure-codex-exec>, retrieved through the
official OpenAI documentation service on 2026-08-06. No third-party source code, provider
credential, or API endpoint is copied or used.

## Court record

- **Advocate:** a local subscription transport makes the existing structured model boundary
  accessible without asking a contributor to create, store, or fund an API key. It covers every
  current `ModelBackend` entry point while retaining Hive Mind's policy, Git, sandbox, and
  receipt layers as the only execution authority.
- **Cross-examiner:** a ChatGPT subscription is not a substitute for GitHub, package-registry,
  signing, storage, deployment, or other external credentials. A Codex subprocess is not hard
  isolation, its local identity is not authenticated independence, and a passing turn is not
  independently verified end-to-end delivery evidence.
- **Expert testimony:** the official documentation states the billing/authentication distinction;
  the local CLI advertises `read-only`, `--ephemeral`, `--ignore-user-config`,
  `--output-schema`, and `--output-last-message`. Deterministic tests confirm the command shape,
  credential scrubbing, response bound, failure handling, and receipt fields.
- **Judge:** repository-owner authority recorded in `HUMAN_AUTHORITY_GATES.md` on 2026-08-06.
- **Disposition:** adapt the model-provider boundary to add a constrained subscription transport;
  defer any capability, security, or maturity claim beyond its tested local boundary.

## Decision

1. Add `codex_subscription` as a `ModelProvider` kind. It invokes only a locally installed,
   already signed-in `codex exec` process; it never sends an HTTP request or reads an API key.
2. The transport rejects any API-key environment configuration, starts in an empty temporary
   directory, uses `read-only` sandbox mode, requests no persistent session or user config, and
   supplies a strict Codex-compatible response wrapper. Hive Mind decodes the wrapper's single
   JSON-string field and validates the enclosed turn against the existing `model-turn` schema
   before it executes any proposed work through its normal policy and capability path.
3. Before starting Codex, the transport removes environment names that could carry an API key,
   access key, token, authorization, credential, or secret. A missing local Codex executable, absent output,
   timeout, malformed response, or non-zero command exit fails the model turn closed.
4. The default model receipt value is `subscription-default`, meaning the signed-in Codex client
   selected its subscription default. It is not a claim of a hidden model identity. An owner may
   explicitly select a subscription-eligible model through the existing non-secret model setting.
5. Model receipts record `provider_kind=codex_subscription`,
   `credential_reference=chatgpt-subscription-session`, and no API-key environment name. Token
   counts are `null` when the local host does not provide them.

## Threats and controls

| Threat | Control | Residual limit |
| --- | --- | --- |
| An inherited key silently changes billing mode | Scrub API/access-key/token/authorization/credential/secret environment names; reject an API-key configuration for this kind | Stored local Codex sign-in remains required and owner-controlled |
| Codex changes a repository directly | Run in a new empty working directory with `read-only`; return only schema-bound text | This is not a hard isolation boundary; `B-OPS-06` remains open |
| Unstructured or excessively large model output | Existing JSON contract validation plus a four-megabyte response ceiling | A valid response can still be incorrect |
| The host selection is misrepresented as a model identity | Explicit `subscription-default` label and a session-auth receipt field | Provider execution itself is not authenticated; `B-GOV-03` remains open |
| Local success is mistaken for real end-to-end maturity | Keep `B-OPS-03` open pending a separately reviewed public-repository exercise | No production, external-delivery, or independence claim is permitted |

## Acceptance evidence

- `tests/test_model_provider.py` proves the subscription path requires neither an API key nor a
  model identifier; uses a credential-scrubbed, read-only, ephemeral Codex command; and rejects
  API-key configuration or an absent response.
- `tests/test_model_backend.py` proves the standard structured backend records session
  authentication without an API-key environment.
- `tests/test_cli_provider_config.py` proves `hive-mind deliver --backend model --provider
  codex_subscription` accepts the subscription transport without a key or model identifier.
- The existing HTTP API transports and their key-redaction tests remain unchanged.

## Consequences and deferred limits

All current structured model consumers can select the subscription transport: the kernel through
`HIVE_MIND_MODEL_PROVIDER=codex_subscription`, and the delivery command through
`--provider codex_subscription`. The existing autonomous local-host path remains independently
available and does not gain broader authority from this ADR.

This ADR does not authorize credentials outside the local Codex sign-in, live API spend, remote
pushes, pull-request creation, merges, deployments, real-provider provider-authentication
claims, external retention, hostile-code execution, or a production claim. `B-OPS-03` remains
open until its stated independent end-to-end exit condition is met. P14–P20 remain historical and
unscheduled.

## Rollback

Revert the subscription provider and this authority amendment. The API transports, scripted
backends, existing autonomous host adapter, historical P05 receipts, and open blocker record
remain intact. Do not delete any live-exercise or adverse-result receipt produced before rollback.
