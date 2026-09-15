# Coupon Hive threat model

- Version: 0.1.0
Assets: user intent, coarse location and preferences, task schedule, source integrity, result accuracy, task notification trust, and publisher reputation.

| Threat | Failure | Control | Verification |
|---|---|---|---|
| Merchant-page prompt injection | A page changes scope, extracts context, or triggers an action | Treat all retrieved content as evidence only; preserve confirmed WatchSpec; quarantine hostile content | NEG-001 and static instruction checks |
| Fabricated or expired code | User wastes time or trusts a nonexistent promotion | Never invent; require current final-page evidence for verified_current; timestamp every check | Offer contract and forward evaluation |
| Hidden-cost free claim | Purchase, fee, rebate, trial, renewal, or membership is concealed | Explicit free taxonomy; only verified_current plus free_now is unconditional | NEG-002 and schema checks |
| Duplicate alert amplification | Same offer appears through many aggregators or on every run | Canonical URL, stable fingerprint, same-chat comparison, silent_when_unchanged | POS-003 and POS-004 |
| Schedule authority confusion | Product claims a watch exists when unsupported or failed | Confirmation gate and host receipt gate; GPT handoff says no task created | POS-003 and legacy-file checks |
| Post-confirmation mutation | A target, threshold, task identity, cadence, title, prompt body, host surface, or alert rule changes after approval | Canonical digest binds the Watch Card and every actionable field; deterministic rendering and type-strict actual-argument comparison fail closed | WatchSpec and host-argument mutation regressions |
| Lifecycle authority replay | A pause, resume, or delete is inferred from earlier approval, replayed, or sent to another task | Fresh LifecycleSpec confirmation binds exact target and states; a fresh host observation, dispatch comparison, session/host consumption marker, and matching receipt mitigate replay. The stateless digest alone cannot prove first use | Lifecycle digest, observation-drift, hostile-type, and dispatch-plan regressions |
| Ambiguous create retry | A timeout is blindly retried and creates duplicate watches | One WatchSpec confirmation is scoped to one transaction; list and resolve exact title/receipt after an unknown outcome before any new confirmation | Transaction-scope and partial-state checks |
| Malformed WatchSpec | Hostile types, non-finite numbers, invalid timestamps, or path-like timezones crash or bypass validation | Strict schema plus exception-safe semantic validator and RFC 3339/IANA checks | Hostile-input regression matrix |
| Location or sensitive-interest leakage | Search/task reveals unnecessary personal data | Coarsest location, discreet title, no full address or sensitive credentials, no backend | Privacy and static checks |
| Coupon abuse | Code guessing, leaked codes, account farming, eligibility bypass | Publicly authorized promotions only; refuse and do not test checkout | NEG-003 |
| Phishing or malware | Lookalike site obtains credentials or executable runs | Prefer canonical official domains; quarantine redirects/downloads/credential prompts | NEG-001 and NEG-002 |
| Scam payment | Gift-card or hard-to-reverse payment is demanded for a discount | Quarantine and recommend known official contact path | Safety reference check |
| Prohibited commerce | Plugin facilitates restricted goods or unlawful services | Apply OpenAI policy and commerce restrictions; refuse | NEG-003 |
| Affiliate bias | Ranking favors publisher compensation or silently implies that source links lack attribution | Publisher adds no affiliate links, receives no referral compensation, excludes commission from ranking, strips common tracking parameters, and discloses that source or host attribution can remain | Repository string and listing review |
| Cross-user data leak | Shared backend mixes watchlists | No publisher backend in 0.1.0 | Architecture inspection |
| Tool or version drift | Scheduled run silently broadens or loses protections | Version-bound prompt; fail closed on missing or incompatible skill/tool | Template inspection |
| Unbounded or unauthorized search load | A watch becomes abusive scraping or queries a disallowed private interface | Host public-web path only, source terms/access controls, source/query caps, hourly minimum cadence, skip-on-unclear authorization | NEG-004 and schema checks |
| Overclaiming coverage | “Ultimate” or “any and all” misleads users | Concrete listing language; superiority deferred to a benchmark court | Listing and court review |

## Residual risk

Accessible source coverage, merchant accuracy, inventory, geo-targeting, and checkout behavior remain outside the plugin's control. Same-chat de-duplication is best effort because version 0.1.0 has no durable remote store. These limits are disclosed in the listing and release notes.

## Escalation

Quarantine rather than guess when evidence conflicts, a source looks hostile, authorization is unclear, or a free classification cannot be established. A future backend, affiliate program, or transaction feature is a new material scope and must return to design, privacy, threat, evaluation, and courtroom review.
