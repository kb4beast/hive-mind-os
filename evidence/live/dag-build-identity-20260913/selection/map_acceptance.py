"""Static Git-blob audit only; never imports product code or executes tests."""
import ast, hashlib, json, pathlib, subprocess
O=pathlib.Path(__file__).parent;R='C:/h/continuity-draft1';C='b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac'
def git(*a):return subprocess.check_output(['git','-C',R,*a])
files=set(git('ls-tree','-r','--name-only',C).decode().splitlines());inventory={}
def load(path):
 if path in inventory:return (O/'pinned'/path).read_bytes()
 raw=git('show',C+':'+path);target=O/'pinned'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 record={'path':path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'git_blob_oid':git('rev-parse',C+':'+path).decode().strip()}
 if path.startswith('tests/') and path.endswith('.py'):
  record['test_methods']=[]
  for n in ast.walk(ast.parse(raw)):
   if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'):
    assertions=[ast.unparse(v) for v in ast.walk(n) if isinstance(v,ast.Call) and isinstance(v.func,ast.Attribute) and v.func.attr.startswith('assert')]
    record['test_methods'].append({'name':n.name,'line':n.lineno,'assertions':assertions})
 inventory[path]=record;return raw
v3p='docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json';v4p='docs/execution/dags/generic-hive-mind-product-v4/plan.json'
v3=json.loads(load(v3p));v4=json.loads(load(v4p));rows=[]
extra={
 'BASELINE-000':['tests/test_generic_dag_v4_plan.py','tests/test_v4_source_provenance.py','evidence/audits/v4-successor-recovery/SOURCE-INTAKE.json'],
 'DOCTOR-PREFLIGHT-005':['src/hive_mind_os/activation_bundle.py','tests/test_generic_dag_v4_activation.py','scripts/Collect-V4ActivationEvidence.ps1','tests/test_collect_v4_activation_evidence.py'],
 'FOUNDATION-010':['src/hive_mind_os/brain_kernel/store.py','tests/test_brain_kernel_store.py','tests/test_hive_cortex_durability.py'],
 'PUBLIC-RUNTIME-500':['tests/test_public_dag_cli.py','docs/execution/PUBLIC_DAG_RUNTIME.md'],
 'FAILURE-QUALIFICATION-610':['docs/execution/GENERIC_DAG_FAILURE_MATRIX.md'],
 'TOKEN-BENCHMARK-620':['src/hive_mind_os/token_benchmark.py','docs/execution/TOKEN_BENCHMARK.md','evidence/audits/v4-successor-recovery/TOKEN-BENCHMARK.json'],
 'QUALIFICATION-PREP-625':['scripts/Collect-V4ActivationEvidence.ps1','tests/test_collect_v4_activation_evidence.py'],
 'CANDIDATE-CI-627':['.github/workflows/ci.yml','tests/test_ci_contract.py','evidence/audits/v4-successor-recovery/PRE-CANDIDATE-FULL-GATE-ATTEMPT-8.json'],
 'GENERIC-QUALIFICATION-630':['evidence/courts/CASE-V4-SUCCESSOR-RECOVERY-2026-09-02.json','tests/test_generic_dag_v4_plan.py'],
 'HANDOFF-700':['docs/execution/PUBLIC_DAG_RUNTIME.md','docs/execution/dags/generic-hive-mind-product-v4/README.md','tests/test_powershell_preparation.py']}
assess={
'BASELINE-000':'Plan tests assert exact canonical builder bytes, request/subject/base bindings, topology and no external authority. Source-intake checks are not current owner-request accepted baseline receipts.',
'DOCTOR-PREFLIGHT-005':'Activation and collector tests exercise malformed bytes, distinct identities, nonce/expiry and inert evidence preparation. They do not establish an external signing custodian, frozen-host deployment or one-run activation for this owner scope.',
'FOUNDATION-010':'Existing store/durability suites assert replay, idempotency and crash recovery with bounded fixtures. No exact current-generation foundation provider receipt is supplied by file presence.',
'PLAN-CORE-100':'Lineage/generation suites assert request/subject/parent identity, carry-forward versus requalification, cycles, complete activation material and fail-closed substitution. No host authentication deployment is inferred.',
'RUNTIME-CONTRACTS-150':'Portable/runtime contract tests assert closed schemas, validation and decision-memory fields. Historical fixed ownership/durability counts are plan-specific, not completion of a later plan.',
'BUILD-SYSTEM-200':'Compiler/workflow/planner tests cover lint, topology, standard pins and inert generation. A downstream public build path drops user-supplied request/subject expectations; selected local gap spans this node and PUBLIC-RUNTIME-500.',
'ADAPTER-INDEX-210':'Subject/resource/registry/index tests assert capability selection, snapshot binding, cache invalidation and unsafe inputs. These are implementation/fixture results, not arbitrary third-party host qualification.',
'WAVE-HOST-300':'Wave/host/integration tests assert durable state, bounded host operation handling, candidate sealing, conflict/target drift and one CAS integration with fake adapters. Real external effect enforcement is not established.',
'TASK-REUSE-310':'Tests distinguish exact reuse, repair/resume/stale/conflict and invalidate changed fingerprints/dependencies/authority. Current-generation accepted dependencies still required.',
'RUNTIME-TOKEN-320':'Role/token suites assert role dispositions, bounded contexts and measured/unavailable accounting. No universal savings or current-run usage is inferred.',
'GENERIC-EXECUTOR-400':'Executor tests exercise fake-host rounds, exact requests, concurrency/resource conflicts, replay/patch/cancellation and failure persistence. Current activation/journal is external.',
'CONTROL-TOKEN-410':'Context/cache/compaction/calibration tests compare exact fingerprints, preserve failure evidence and refuse unmeasured/negative calibration claims. Fixture benefit is not general superiority.',
'PUBLIC-RUNTIME-500':'CLI tests assert absolute-path inspection, missing status inertness, default external execute refusal, canonical build and inert preparation. No build test supplies expected_request_id or expected_subject_id. CLI accepts both flags but discards them in build dispatch; service build_file has no parameters for them. Generic guide paths remain absent and existing start page still describes obsolete bootstrap bundle.',
'GENERIC-FIXTURES-600':'Tests assert the named cross-language and nonrepository fixture inventory, public contracts, snapshots and fake-host deterministic runs. Fixtures create language-shaped files; they are not proof of native compiler/toolchain or live delivery execution for every language.',
'FAILURE-QUALIFICATION-610':'Failure-matrix test source covers silent host deadlines, completion ordering, target drift, hidden dependencies, stale/resource/conflict scenarios with local doubles. Renamed doc exists; original V3 receipt path is absent and cannot be replaced by test existence.',
'TOKEN-BENCHMARK-620':'Controlled fixture tests and retained benchmark JSON support bounded equal-control comparisons and reported input savings; no current-candidate or universal claim is closed. Renamed documentation exists.',
'QUALIFICATION-PREP-625':'Collector code/tests support absolute outside-candidate preparation, clean/exact identity and timeout/path refusal. Actual fresh freeze receipt bound to current intended generation remains external/missing.',
'CANDIDATE-CI-627':'Workflow contract tests and historical CI records exist. They do not satisfy the exact independently frozen doctor+CI observations for a new generation; continuity PR177 checks are a separate subject.',
'GENERIC-QUALIFICATION-630':'Open historical V4 court and plan tests exist; no accepted current-generation independent verdict or per-node ledger is established. Owner waiver is not a fabricated successful court receipt.',
'HANDOFF-700':'Public runtime/PowerShell implementation and tests provide inert preparation. Required complete generic user guide lacks its planned entry paths; current draft-PR authority and exact evidence lineage remain separate obligations.'}
for n in v4['nodes']:
 prior=next(x for x in v3['nodes'] if x['id']==n['node_id']);planned=prior['write_scope'];actual=sorted(set([p for p in planned if p in files]+extra.get(n['node_id'],[])))
 for p in actual:load(p)
 rows.append({'node_id':n['node_id'],'acceptance_criteria':n['acceptance_criteria'],'planned_v3_paths':planned,'actual_mapped_artifacts':actual,'absent_planned_literal_paths':[p for p in planned if p not in files],
 'assessment':assess[n['node_id']],'acceptance_disposition':'partial_static_mapping_not_node_completion','tests_executed':False})
for p in ['USER_GUIDE/00_START_HERE.md','USER_GUIDE/02_ONE_PROMPT_FOREVER.md','docs/execution/PLAN_LINEAGE.md','docs/execution/dags/generic-hive-mind-product-v4/manifest.json','src/hive_mind_os/dag_standard.py']:load(p)
# Machine-visible static proof of the selected dropped-binding path.
cli=ast.parse(load('src/hive_mind_os/dag_cli.py'));service=ast.parse(load('src/hive_mind_os/subject_execution.py'))
calls=[n for n in ast.walk(cli) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='build_file']
method=next(n for n in ast.walk(service) if isinstance(n,ast.FunctionDef) and n.name=='build_file')
validation=next(n for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='validate_files')
proof={'cli_build_call_line':calls[0].lineno,'cli_build_forwarded_keywords':[k.arg for k in calls[0].keywords],
 'service_build_line':method.lineno,'service_build_parameters':[a.arg for a in method.args.kwonlyargs],
 'build_validation_call_line':validation.lineno,'build_validation_forwarded_keywords':[k.arg for k in validation.keywords],
 'expected_identity_flags_accepted_in_parser':all(x in load('src/hive_mind_os/dag_cli.py').decode() for x in ['--expected-request-id','--expected-subject-id']),
 'build_identity_flags_dropped':all(x not in [k.arg for k in calls[0].keywords] for x in ['expected_request_id','expected_subject_id'])}
out={'schema_version':1,'mapping_id':'V4-MAIN-ACCEPTANCE-MAPPING-B19B2A1-V1','reviewer':'/root/delivery_curator','subject_commit':C,'subject_tree':git('rev-parse',C+'^{tree}').decode().strip(),'plan_id':v4['plan_id'],'node_count':len(rows),'runtime_completion_claim':False,'source_inventory':list(inventory.values()),'nodes':rows,'selected_gap_static_proof':proof}
(O/'V4-ACCEPTANCE-MAPPING-V1.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'nodes':len(rows),'source_artifacts':len(inventory),'static_proof':proof}))
