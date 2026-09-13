"""Independent repaired-commit probes; no real authority or campaign launch."""
import ast
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
from dataclasses import replace
from unittest.mock import patch

sys.dont_write_bytecode = True
SOURCE = pathlib.Path('C:/h/continuity-draft1')
OUT = pathlib.Path(__file__).parent
COMMIT = '511850802afe2b58c0609f12d469f3751be4a3cb'
sys.path[:0] = [str(SOURCE/'src'), str(SOURCE/'tests')]
from hive_mind_os.campaign_continuity import CampaignContinuityController, ContinuityError, Phase
from test_campaign_continuity import CampaignContinuityDraftTests, MemoryAdapter

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

results = {}
case = CampaignContinuityDraftTests()
case.setUp()
try:
    case.ready()
    case.controller.step(case.adapter)
    with patch.object(case.adapter,'inspect',side_effect=ContinuityError('authority-denied','fixture denial')):
        denied=case.controller.step(case.adapter)
    original=case.controller.events()
    last=original[-1]
    # Append a self-consistent but impossible terminal->reconciling checkpoint.
    # This is a semantic validator test, not an authenticated-custody claim.
    state={**last['checkpoint'],'phase':'reconciling','blocker':None}
    event={'schema_version':2,'sequence':last['sequence']+1,'previous_digest':last['event_digest'],
           'kind':'reconciliation-receipt','payload':{},'checkpoint':state}
    event['event_digest']='sha256:'+digest(canonical(event))
    (case.root/f"event-{event['sequence']:08d}.json").write_bytes(canonical(event)+b'\n')
    reopened=case.reopen()
    returned=reopened.step(case.adapter)
    results['illegal_terminal_regression']={'prior_phase':denied['phase'],'prior_blocker':denied['blocker'],
        'accepted_phase':returned['phase'],'launches':len(case.adapter.launches),
        'reconciliations':returned['reconciliations']}
finally:
    case.doCleanups()

case = CampaignContinuityDraftTests()
case.setUp()
try:
    case.ready()
    selected=case.controller.step(case.adapter)
    last=case.controller.events()[-1]
    state={**last['checkpoint'],'phase':'launched','reconciliations':1}
    event={'schema_version':2,'sequence':last['sequence']+1,'previous_digest':last['event_digest'],
           'kind':'reconciliation-receipt','payload':{},'checkpoint':state}
    event['event_digest']='sha256:'+digest(canonical(event))
    (case.root/f"event-{event['sequence']:08d}.json").write_bytes(canonical(event)+b'\n')
    returned=case.reopen().step(case.adapter)
    results['success_without_receipt_payload']={'phase':returned['phase'],
        'inspections':len(case.adapter.inspections),'launches':len(case.adapter.launches)}
finally:
    case.doCleanups()

# Independent controls of repaired boundary behavior, using original fixture
# inputs but exercising recover directly rather than running repository tests.
case=CampaignContinuityDraftTests()
case.setUp()
try:
    case.ready()
    case.controller.step(case.adapter)
    case.adapter.raise_after_effect=True
    pending=case.controller.step(case.adapter)
    case.controller.clock=lambda: case.scope.expires_at
    blocked=case.controller.step(case.adapter)
    recovered=case.controller.recover(case.adapter)
    results['expired_pending_recovery_control']={'pending':pending['outcome_pending'],
        'blocker':blocked['blocker'],'recovered_phase':recovered['phase'],
        'recovered_pending':recovered['outcome_pending'],'launches':len(case.adapter.launches)}
finally:
    case.doCleanups()

manifest=json.loads((SOURCE/'docs/architecture/CONTINUITY-QUALIFICATION-MANIFEST.json').read_bytes())
rows=[]
for item in manifest['artifacts']:
    path=item['path']; raw=subprocess.check_output(['git','-C',str(SOURCE),'show',COMMIT+':'+path])
    working=(SOURCE/path).read_bytes()
    rows.append({'path':path,'declared_sha256':item['sha256'],'declared_bytes':item['bytes'],
        'git_blob_sha256':digest(raw),'git_blob_bytes':len(raw),
        'working_tree_sha256':digest(working),'working_tree_bytes':len(working),
        'matches_git_blob':digest(raw)==item['sha256'],'matches_working_tree':digest(working)==item['sha256'],
        'line_ending_normalization_only':raw==working.replace(b'\r\n',b'\n')})
results['manifest_artifacts']=rows
original_review=pathlib.Path('C:/h/continuity-qualification/review')
copied=[]
for original in sorted(original_review.iterdir()):
    if not original.is_file(): continue
    name=original.name+'.txt' if original.suffix=='.py' else original.name
    path='docs/architecture/continuity-qualification-review/'+name
    copied_blob=subprocess.check_output(['git','-C',str(SOURCE),'show',COMMIT+':'+path])
    copied.append({'original':str(original),'copy':path,'original_sha256':digest(original.read_bytes()),
        'git_copy_sha256':digest(copied_blob),'byte_identical':original.read_bytes()==copied_blob})
results['copied_original_evidence']=copied

# Confirm every original test method AST remains identical, not just assertion count.
path='tests/test_campaign_continuity.py'
old=subprocess.check_output(['git','-C',str(SOURCE),'show','1a28b0c0587cc9a576c8f0aa2c287df3e3d2f366:'+path])
new=subprocess.check_output(['git','-C',str(SOURCE),'show',COMMIT+':'+path])
def test_methods(raw):
    tree=ast.parse(raw)
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(tree)
            if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
oldmethods,newmethods=test_methods(old),test_methods(new)
results['original_test_methods']={'original_count':len(oldmethods),'current_count':len(newmethods),
    'missing_or_changed':[k for k,v in oldmethods.items() if newmethods.get(k)!=v]}
print(json.dumps(results,indent=2))
