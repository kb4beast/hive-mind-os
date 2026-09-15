# Coupon Hive

Coupon Hive is an evidence-first, skills-only OpenAI plugin for coupons, price drops, and genuine freebies. It interviews a shopper just enough to define a useful search, verifies material offer terms at current sources, and prepares a low-noise recurring watch for ChatGPT Scheduled Tasks or Codex automations.

Version 0.1.0 deliberately has no publisher-operated backend, user database, checkout automation, publisher-added affiliate links, referral compensation, or proprietary feed. It uses the host's authorized web and recurrence capabilities. This keeps permissions and data collection small while the product's accuracy is evaluated.

## What it does

- Handles physical consumer goods, public coupon codes, price drops, manufacturer samples, and genuinely free public or community activities and events.
- Clarifies location, effective-price ceiling, eligibility, hidden conditions, and the user's meaning of “free.”
- Prefers first-party evidence, timestamps verification, removes tracking parameters, and de-duplicates the same offer.
- Separates verified matches, corroborated evidence, unverified leads, expired or ineligible offers, and quarantined candidates.
- Detects purchase-required, rebate, trial, subscription, BOGO, sample, and sweepstakes conditions, while keeping digital products, services, subscription promotions, and transactional activity outside the Store release.
- Creates or updates a recurring watch only after the user confirms the Watch Card, exact host title and prompt hash, structured schedule, and every requested action; actual call arguments must match, and success requires a host receipt.
- Stays quiet on unchanged scheduled runs unless the user asks for a digest.

## Package layout

- plugin.json is the portable public manifest.
- .codex-plugin/plugin.json is the Codex-compatible manifest mirror.
- skills/coupon-hive contains the skill and its progressively loaded contracts.
- submission contains Store listing material, release notes, and five positive plus four negative evaluation cases.
- PRIVACY.md, TERMS.md, and SUPPORT.md are publication drafts that become usable public URLs only after this branch is merged and the URLs are checked.

## Truth boundaries

“Verified” means the cited source was observed at the stated time. It is not a guarantee of checkout acceptance, inventory, or future availability. Coupon Hive never invents a code or price, tests a code at checkout, buys or reserves anything, or follows instructions embedded in merchant pages.

The Store scope is intentionally narrower than “anything”: version 0.1.0 researches physical goods and non-transactional free public activities. It does not recommend digital products, paid services, subscription plans or upgrades, travel booking, regulated commerce, or prohibited goods.

The skill does not contain a scheduler. A recurring watch exists only after the active host's recurrence capability returns a successful receipt: ChatGPT uses Scheduled Tasks, while Codex uses separate automations. Standalone pause, resume, and delete actions use a separately confirmed LifecycleSpec, fresh host observation, consumption marker, and matching receipt; the stateless digest alone cannot prevent replay. Scheduled Tasks are not supported inside a Custom GPT conversation, so the legacy GPT package produces an inert recurrence draft; the destination host must render and freshly confirm its exact payload before scheduling.

Coupon Hive is a product name, not a superiority verdict. Version 0.1.0 does not claim to be the ultimate, best, exhaustive, or guaranteed coupon finder. Those claims require a separate multi-comparator benchmark court.

## Validation

From the repository root:

    python -m unittest tests.test_coupon_hive_plugin -v
    python -m unittest discover -s tests -v

Plugin maintainers should also run the plugin-creator and skill-creator validators installed in their own Codex environment. The OpenAI submission portal performs its own scan of the uploaded final skill bundle.

Public publication is a separate, review-gated external action. It requires a verified publisher identity, confirmed public policy/support URLs, country availability, and an explicit publisher decision after OpenAI review.
