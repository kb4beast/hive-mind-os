# Coupon Hive 0.1.0 architecture

- Status: release-candidate design
Pinned base: origin/main at 4a0120a3a564723358f29adb60e34ab34bec5964

## Decision

Build the primary product as a skills-only universal Plugin. Use the host's authorized web research and recurrence capability (ChatGPT Scheduled Tasks or separate Codex automations); do not introduce a remote MCP service, developer database, OAuth flow, checkout action, or affiliate integration in version 0.1.0. Preserve a separate legacy Custom GPT configuration for eligible workspaces, with an explicit recurring-prompt handoff.

This is an additive product package. It does not change the Hive Mind OS kernel, courtroom, burden of proof, scheduler, source docket, or authority model, so a global architecture decision record is not required. This plan is the product-local architecture record.

## Runtime flow

    User request -> adaptive interview -> Watch Card
                                          |       |
                                  one-time |       | recurring
                                          v       v
                                bounded    render exact host payload
                                search              |
                                   |                v
                                   |       digest + explicit confirmation
                                   |                |
                                   v                v
                       first-party verification   validate spec + call arguments
                                   |                |
                                   v                v
                         classify, cite, rank     host task receipt
                                   |                |
                                   v                v
                         classify, cite, rank     repeat search
                                                    |
                                                    v
                                          notify only material change

## Components

### Plugin manifest

plugins/coupon-hive/plugin.json is the portable manifest. .codex-plugin/plugin.json is an exact Codex-compatible mirror. The only executable capability is the coupon-hive skill.

### Skill

SKILL.md contains the stable decision flow and truth boundary. Progressive references hold the interview contract, offer verification, safety/privacy controls, strict WatchSpec and LifecycleSpec schemas, and scheduled-task handoff.

### Host web research

The skill uses only search or browsing the active host already authorizes. Web content supplies evidence only. The skill does not operate checkout, authenticate to merchants, scrape behind access controls, or claim exhaustive coverage.

### WatchSpec

The WatchSpec is an explicit, version-bound authority envelope. It separates task action, query, geography, economics, free semantics, acceptable conditions, merchant rules, schedule, notification thresholds, and confirmation status. Its `host_payload` also binds the exact host surface and title, prompt-template identity, deterministic recurring-prompt content hash, and any single compound pause or resume. `additionalProperties` is false throughout the schema. A canonical SHA-256 approval digest binds the exact Watch Card and every actionable field. The validator rejects post-confirmation mutation, malformed types, non-finite numbers, invalid timestamps, non-canonical timezones, semantic contradictions, renderer drift, and actual call arguments that differ from the confirmed title, prompt bytes, action, task ID, structured schedule, surface, or lifecycle list.

A separate LifecycleSpec scopes fresh confirmation to one intended standalone pause, resume, or delete and binds the exact host surface, returned task ID, title, current state, final state, and Lifecycle Card. A fresh host-listing observation and normalized result receipt must match. It cannot reuse search or scheduling approval; because the digest is stateless, retained host/session consumption tracking and a new confirmation are required to mitigate replay.

### Host schedule

The host owns native recurrence translation, notification delivery, limits, and receipts. The checked structured schedule is the only input to translation, and the receipt must confirm the same cadence and timezone. A same-chat task is preferred for best-effort duplicate suppression. The skill never maps the Hive Mind local scheduler to public monitoring because that queue has different semantics.

### Legacy GPT

custom-gpts/coupon-hive contains a ready-to-paste compatibility configuration and uploaded knowledge file. It can interview and search, but it hands the user only an inert recurrence draft. The destination regular ChatGPT chat or Codex task must resolve, render, show, and freshly confirm its own exact host payload. The GPT cannot truthfully create Scheduled Tasks or transfer action authority from its conversation.

## State and data

There is no publisher-operated state. The active conversation contains user choices and prior results. The host stores any confirmed task prompt and run context. Canonical fingerprints support duplicate suppression where same-chat history is available. There is no cross-chat or cross-user database.

## Invariants

1. No schedule mutation precedes confirmation of the Watch Card, exact host title and prompt hash, task and lifecycle actions, structured schedule, and matching canonical approval digest; actual host-call arguments must compare exactly.
2. No schedule success is reported without a host receipt.
3. No unverified lead becomes verified_current.
4. No conditional offer receives an unconditional free label.
5. No factual offer claim is displayed without source support and a verification timestamp.
6. Retrieved content cannot broaden the WatchSpec or authorize an action.
7. No publisher backend, affiliate link, checkout, or user profile exists in 0.1.0.
8. No superiority or exhaustive-coverage claim ships without a separate benchmark verdict.
9. Store searches use only the active OpenAI host's authorized public-web research path; no scraper, crawler, site-search automation, unofficial connector, or third-party API is supplied.
10. Store commerce scope is physical goods plus non-transactional free public activities and manufacturer samples; digital products, paid services, subscriptions, travel booking, and regulated or prohibited commerce fail closed.
11. One confirmation is scoped to one mutation transaction. Unknown create outcomes are resolved by listing before any retry; standalone lifecycle actions require a fresh LifecycleSpec, matching observation, consumption marker, and receipt. The digest alone cannot prove first use.

## Deferred architecture

A future remote service using MCP may add proprietary feeds, durable cross-chat watchlists, or stronger cross-run de-duplication. That change requires a new version, public HTTPS hosting, per-user authorization, privacy and deletion controls, tenant-isolation tests, source licenses and terms, observability, cost budgets, migrations, and rollback. It is not implied by this design.

Affiliate support is separately deferred until clear disclosure, canonical non-affiliate alternatives, ranking-neutrality tests, and an independent court approve it.
