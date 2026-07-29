# Phase 1 Primary-Source Register

- Register status: intake complete; every source group has an explicit Phase 1
  disposition in `evidence/courts/P1-SOURCE-ADMISSION.md`
- Retrieval instant: `2026-07-29T00:36:27.865Z`
- Explorer/Clerk: `/root/phase1_sources`
- Originating mission brief SHA-256:
  `dbd73add9f47aa98a30d19f1538179e5e961c1452a70b9ce54b7403b4e387a46`
- Availability result: 37 of 38 distinct URL strings returned HTTP 200 or an
  official redirect; the AgentTelemetry OpenReview PDF returned HTTP 403

This register preserves locators and verified pins where available. The source
court, not HTTP availability, decides admission. Mutable documentation,
unknown documentation licenses, unavailable bytes, and unreviewed reuse terms
remain explicit obligations under narrowed `defer`, `reject`, or `quarantine`
dispositions.

## `P1SRC-OBSIDIAN-HELP`

- Publisher: Obsidian
- Original locators:
  `https://obsidian.md/help/data-storage`,
  `https://obsidian.md/help/Files%20and%20folders/Manage%20vaults`,
  `https://obsidian.md/help/import/markdown`,
  `https://obsidian.md/help/file-formats`,
  `https://obsidian.md/help/updates`,
  `https://obsidian.md/help/community-plugins`,
  `https://obsidian.md/help/Obsidian%20Sync/Introduction%20to%20Obsidian%20Sync`,
  `https://obsidian.md/help/sync/settings`,
  `https://obsidian.md/help/Extending%2BObsidian/Obsidian%2BURI`,
  `https://obsidian.md/help/properties`,
  `https://obsidian.md/help/bases`,
  `https://obsidian.md/help/bases/syntax`,
  `https://obsidian.md/help/plugins/graph`,
  `https://obsidian.md/help/plugins/canvas`, and
  `https://obsidian.md/help/cli`
- Redirect locators retained:
  `https://help.obsidian.md/Extending%2BObsidian/Obsidian%2BURI` and
  `https://help.obsidian.md/Obsidian%20Sync/Introduction%20to%20Obsidian%20Sync`
- Pin: official `obsidianmd/obsidian-help` commit
  `29e89022c6aeb0a9e9971b6f0c98733dbc2eb716`
- Content SHA-256 receipts in locator order:
  `add03088da7be4ab2fd364918c17b006d646eafedffada5440db83217f6942e6`,
  `c57c9d0d93ce60b805a0419584ff3aa7ecd2a35315e6c79c81207aab60585ee3`,
  `7ec4dcdb50b3aba69c8318e6f7a4552aad666f6aa8928d52a1df9e956261caa4`,
  `95ede78937600de68ad15ade8cf5044f05261eac9f72187c2880f6a7c71b517e`,
  `0f2bfe7ca73d99790ebb0ff7e3dc1294b4d6c010f3e12cc468f957c0fa2eaf58`,
  `a85b0f88c26b433489a4f4bcb81c072397ad6561b6bf4c1a17fa3557f63bccda`,
  `a48cb81454c74ee909e9578e92c09828f66779da665302eb28f6f107440427b4`,
  `040d233c7ba6e3f674aed22bbfaddd18c7af783a1e74be5dd7b79301cf83dac4`,
  `d401a97319322d3d3abf993dc18ab859c127060a54927b01a901781addecd5c1`,
  `6107332a41a95cea07b993da173cdf83ff1291543169ee4c0c1b63ce9e116af5`,
  `3cfa5fdd36ed75fe7999f88d1c6fd120ca52058f53517d12e2b5b3b0e136f978`,
  `7fabd5f8fc3dadc45cdac2cac687016e9fdd9bc5e97f6879ef6beb4d26aac8e7`,
  `4dc8b65df8d67062a71ba56b91a39a97850b141e5b2cb8c851089030d431f61b`,
  `3beb6e9974e596f6b4dd5b09141657dcbe8a29cab64f6178d651857fbdcccf26`,
  and
  `1544d5de218c9a84bb44666c6a19e35b6635532c0a853cd3721f2f6912207c75`
- License: unresolved. The official help repository has no root license file.
  The application license page is not a documentation reuse grant.
- Status: `adapt`; factual interoperability claims admitted by reference only;
  documentation copying/redistribution remains blocked

## `P1SRC-OBSIDIAN-LICENSE`

- Locator: `https://obsidian.md/license`
- Publisher: Obsidian
- Version/digest: mutable page; immutable publisher version not supplied
- Use: application-use context only
- Status: `reject` as documentation-reuse or architecture authority; locator
  retained for application-use context

## `P1SRC-JSON-CANVAS`

- Locator: `https://jsoncanvas.org/spec/1.0/`
- Official repository pin:
  `456f843cb293df4f4ab1763e22ccb46a80b307c8`
- `spec/1.0.md` SHA-256:
  `41d75005394f3ed43a53031ff9d07c5d49c47e897971e7afb2972cc8af67469a`
- `LICENSE` SHA-256:
  `5dc8a82e5f93308e31b729297b027d1aafbaae3b9b73696371a975a3b4a2cd5d`
- License: MIT
- Status: `adapt`; optional projection-format claims admitted

## `P1SRC-OTEL-GENAI`

- Locators:
  `https://github.com/open-telemetry/semantic-conventions-genai/tree/799e014b68f0e786dc44d9117c30758c5f864510`,
  `https://github.com/open-telemetry/semantic-conventions-genai/blob/799e014b68f0e786dc44d9117c30758c5f864510/docs/gen-ai/gen-ai-metrics.md`,
  `https://github.com/open-telemetry/semantic-conventions-genai/blob/799e014b68f0e786dc44d9117c30758c5f864510/docs/gen-ai/gen-ai-spans.md`, and
  `https://github.com/open-telemetry/semantic-conventions-genai/blob/799e014b68f0e786dc44d9117c30758c5f864510/docs/gen-ai/gen-ai-agent-spans.md`
- Pin: `799e014b68f0e786dc44d9117c30758c5f864510`
- Document SHA-256 receipts:
  `de1f85e056dfe773eee27549f72e8e38ddbe5fee1ad5531b0320b7dd2f2e8a57`,
  `fa96ac94d260343bb09710adb29e0199a94ca725626b01e354f6d22797231627`,
  and
  `3540a19cdce5a36ade213b259f12685533c35698cd7dffccd49b1a9025f8f395`
- License: Apache-2.0; license SHA-256
  `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`
- Limitation: the pinned GenAI conventions label themselves `Development`.
  They are an observability reference, not accounting authority.
- Status: `adapt`; vocabulary admitted as a replaceable development reference,
  not accounting authority

## `P1SRC-PROMETHEUS`

- Locators: `https://prometheus.io/docs/practices/naming/` and
  `https://prometheus.io/docs/practices/instrumentation/`
- Official source commit observed:
  `406d17b1625f4f30182c06e28c6bec83c66f40ad`
- License: Apache-2.0
- Status: `defer`; no Phase 1 architecture claim depends on this source

## `P1SRC-PROVIDER-DOCS`

- Locators:
  `https://developers.openai.com/codex/config-advanced#observability-and-telemetry`
  (currently redirects to official `learn.chatgpt.com` documentation),
  `https://code.claude.com/docs/en/monitoring-usage`,
  `https://platform.claude.com/docs/en/api/admin/usage_report/retrieve_messages`,
  `https://platform.claude.com/docs/en/build-with-claude/task-budgets`, and
  `https://ai.google.dev/api/generate-content`
- Publishers: OpenAI, Anthropic, and Google
- Version/digest/license: mutable publisher pages without immutable publisher
  version in the handoff; documentation-terms review required
- Status: `quarantine`; locators remain discovery evidence only

## `P1SRC-MLFLOW`

- Locators:
  `https://mlflow.org/docs/latest/api_reference/python_api/mlflow.models.html#mlflow.models.MetricThreshold`
  and `https://mlflow.org/docs/latest/genai/eval-monitor/`
- Official source commit observed:
  `1a8e76c4956c122e8246f8867486b16efcc2e9ec`
- License: Apache-2.0
- Status: `defer`; no MLflow-specific implementation or threshold is adopted

## `P1SRC-LM-EVAL-HARNESS`

- Locator:
  `https://github.com/EleutherAI/lm-evaluation-harness/blob/f4d4b3de3ee6741a7151a9fe74945ee515262f4c/docs/task_guide.md`
- Pin: `f4d4b3de3ee6741a7151a9fe74945ee515262f4c`
- Guide SHA-256:
  `b16a131beac02ef7a2569494a7f45f13763fa60d459ef8343910f4d418e79cf9`
- License: MIT; license SHA-256
  `a806e42547620dffbc2ec0333322c8b3523b4af11e059be14ef81aa5b1ae021f`
- Status: `adapt`; reproducible evaluation-design claims admitted

## `P1SRC-LIVEBENCH`

- Locator: `https://arxiv.org/abs/2406.19314`
- Pin: `arXiv:2406.19314v2`, revised 2025-04-18
- PDF SHA-256:
  `38207db0331896e9558cc803d04188f32dddda1709139c53f985680d1b78e06c`
- License: arXiv non-exclusive distribution license; not an implementation-code
  license
- Status: `adapt`; freshness/contamination concern admitted while external
  validity and superiority remain unproven

## `P1SRC-AGENTTELEMETRY`

- Locator: `https://openreview.net/pdf?id=owdmAYFk6k`
- Retrieval: HTTP 403
- Version/digest/license: unavailable
- Status: `quarantine`; title discovery is retained, while content, numeric
  claims, authorship, review state, code, and license remain unadmitted

## `P1SRC-W3C-PROV-O`

- Original locator: `https://www.w3.org/TR/prov-o/`
- Immutable Recommendation:
  `https://www.w3.org/TR/2013/REC-prov-o-20130430/`
- Version: W3C Recommendation, 2013-04-30
- SHA-256:
  `6b96671ab84faf12ce3f041aca12c3f93a6df2ed242348810743179a68e69555`
- License: W3C document-use rules
- Status: `adapt`; optional provenance-export reference only

## `P1SRC-W3C-JSON-LD`

- Original locator: `https://www.w3.org/TR/json-ld11/`
- Immutable Recommendation:
  `https://www.w3.org/TR/2020/REC-json-ld11-20200716/`
- Version: W3C Recommendation, 2020-07-16
- SHA-256:
  `9e2c9972d0f60bc744e975731643a9a63d410afc6b682eb8898ad2720e452866`
- License: W3C document-use rules
- Status: `defer`; no demonstrated Phase 2 internal-format need

## `P1SRC-PR27-PROCESS-EVIDENCE`

- Locator: `https://github.com/kb4beast/hive-mind-os/pull/27`
- Type: repository/process evidence, not redesign research evidence
- Exact merge commit:
  `b032a9f32f48889e0889fae8d6dd04eb03f46b63`
- Governing court: `evidence/courts/PR27-ci-test-contract-repair.md`
- Status: `adopt` as internal baseline/process evidence only; Phase 0 already
  adjudicated its bounded repair and preserved external governance obligations

## Retained obligations after disposition

- `P1-SRC-B01`: Obsidian help copying/redistribution remains prohibited unless
  reuse terms are resolved; factual citation and independent implementation
  are adapted.
- `P1-SRC-B02`: Mutable provider pages remain quarantined until a provider
  conformance implementation pins exact versions, bytes, and terms.
- `P1-SRC-B03`: AgentTelemetry remains quarantined; no adopted contract depends
  on it.
- `P1-SRC-B04`: Prometheus and MLflow remain deferred; no adopted contract
  depends on their unpinned pages.
- `P1-SRC-B05`: Exact Armory semantics remain quarantined and cannot be claimed
  without an exact source.
- `P1-SRC-B06`: Registration alone remains nonauthoritative; the source court
  records the bounded dispositions.
