# Coupon Hive 0.1.0

Initial review candidate.

## Included

- Adaptive interview and user-confirmed Watch Card.
- Search workflow for physical goods, free public activities and events, coupons, manufacturer samples, and clearly classified free offers.
- First-party verification, timestamps, canonical links, and duplicate suppression.
- Explicit free-offer and verification classifications.
- Low-noise ChatGPT Scheduled Task or Codex automation handoff with a digest-bound host surface, exact title, versioned deterministic prompt and content hash, type-strict structured schedule, explicit actions, pre-dispatch comparison, and receipt boundary.
- A separate LifecycleSpec that scopes fresh confirmation to one intended pause, resume, or delete call, checks a fresh host observation and receipt, and requires update-plus-pause/resume sequences to stop on primary failure and report partial state.
- Prompt-injection, scam, privacy, prohibited-commerce, and coupon-abuse controls.
- No publisher backend, publisher-added affiliate links, referral compensation, advertising, checkout, or stored user profiles.
- Digital goods, paid services, subscription promotions, travel booking, regulated commerce, and prohibited goods are excluded from the Store scope.
- Portable plugin manifest plus Codex compatibility manifest.
- Five positive and four negative Store evaluation cases, including unauthorized source access.

## Known limitations

- Coverage is bounded by the host's available search tools and accessible current sources.
- Merchant inventory, prices, and codes can change after verification.
- Best-effort duplicate suppression uses retained same-chat context; there is no remote cross-chat watch database.
- ChatGPT Scheduled Tasks and Codex automations are host- and plan-dependent; Scheduled Tasks are not supported inside Custom GPT conversations.
- A task is not created or changed when the deterministic authority validator/renderer is unavailable or when the host would normalize the confirmed payload.
- Approval digests are stateless integrity evidence, not proof of consent or first use; action-time confirmation and retained host/session consumption tracking remain required.
- Public publication remains pending verified publisher identity, public URL verification, evaluation receipts, OpenAI review, and an explicit publisher decision.

## Deferred

- Remote MCP persistence and proprietary deal feeds.
- Affiliate monetization.
- Automated checkout or code testing.
- Any “ultimate,” “best,” exhaustive-coverage, or guaranteed-savings claim.
