# Source Register

## User-supplied governing sources

1. `SOURCE_GENERICPROMPT.txt` — exact specialized GenericPrompt used as the execution method.
2. `SOURCE_HIVE_CLASSIC_INSTRUCTIONS.txt` — truthful single-model role-simulation and evidence rules.
3. User subject statement — self-operating Hive Mind OS; all roles wired; role-first help before human questions; anti-cheating confirmation.

## Current repository sources inspected at baseline

- `AGENTS.md`
- `README.md`
- `pyproject.toml`
- `.github/workflows/ci.yml`
- `src/hive_mind_os/runtime.py`
- `src/hive_mind_os/roles.py`
- `src/hive_mind_os/model_backend.py`
- `src/hive_mind_os/model_provider.py`
- `src/hive_mind_os/mission.py`
- `src/hive_mind_os/mission_loop.py`
- `src/hive_mind_os/mission_store.py`
- `src/hive_mind_os/autonomous_os.py`
- `src/hive_mind_os/scheduler.py`
- `src/hive_mind_os/workers.py`
- `src/hive_mind_os/brain_kernel/*`
- `src/hive_mind_os/cortex/repository/*`
- `src/hive_mind_os/recursive_improvement.py`
- `src/hive_mind_os/learning.py`
- current plans, ADRs, evidence, merged PR lineage, open PR #114, and current branch protection.

## External architecture sources used as pattern evidence

- Temporal workflow/event-history documentation — https://docs.temporal.io/workflows
- DBOS durable workflows — https://docs.dbos.dev/
- Restate durable execution — https://docs.restate.dev/
- Kubernetes controllers — https://kubernetes.io/docs/concepts/architecture/controller/
- OpenAI Agents SDK handoffs and guardrails — https://openai.github.io/openai-agents-python/
- Microsoft AutoGen teams — https://microsoft.github.io/autogen/stable/
- LangGraph persistence — https://langchain-ai.github.io/langgraph/concepts/persistence/
- OpenHands runtime/sandbox — https://docs.openhands.dev/
- SWE-agent agent-computer interface — https://swe-agent.com/
- Open Policy Agent — https://www.openpolicyagent.org/docs/latest/
- in-toto — https://in-toto.io/
- SLSA — https://slsa.dev/
- Sigstore/Rekor — https://docs.sigstore.dev/
- OpenTelemetry — https://opentelemetry.io/docs/
- Hypothesis property testing — https://hypothesis.readthedocs.io/
- TLA+ — https://lamport.azurewebsites.net/tla/tla.html
- ReAct, Reflexion, Tree of Thoughts, Self-Refine, and multi-agent debate research papers.

## Current model-routing sources

- OpenAI official GPT-5.6 announcement/model guidance, accessed 2026-08-09.
- Anthropic official Fable 5, Sonnet 5, Opus 4.8, and model-system-card pages, accessed 2026-08-09.

External patterns were evaluated for architecture suitability. No external code was copied into the generated controller.
