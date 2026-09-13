"""Seal read-only review evidence; git operations are read-only."""
import datetime
import hashlib
import json
import pathlib
import subprocess

root = pathlib.Path(__file__).parent
repo = pathlib.Path('C:/h/continuity-draft1')
commit = '511850802afe2b58c0609f12d469f3751be4a3cb'
run = pathlib.Path('C:/h/continuity-qualification/state/run-20260913-012909-3fecfe58')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(repo), *args])

def file_record(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}

head = git('rev-parse', 'HEAD').decode().strip()
tree = git('rev-parse', commit + '^{tree}').decode().strip()
status = git('status', '--porcelain=v1').decode()
assert head == commit
assert tree == '48824828bb2c571c0ae4f25ad85361bda5bedffd'
assert status == '', status
sources = []
paths = [
    'src/hive_mind_os/campaign_continuity.py',
    'tests/test_campaign_continuity.py',
    'docs/architecture/ADR-CAMPAIGN-CONTINUITY-QUALIFICATION.md',
    'docs/architecture/CONTINUITY-QUALIFICATION-MANIFEST.json',
    '.gitattributes',
]
paths += [row['path'] for row in json.loads((root/'probe-results.json').read_bytes())['manifest_artifacts']]
for path in dict.fromkeys(paths):
    raw = git('show', commit+':'+path)
    target = root/'immutable-git-blobs'/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    working = (repo/path).read_bytes()
    sources.append({'repository_path':path, 'commit':commit,
        'git_blob_oid':git('rev-parse', commit+':'+path).decode().strip(),
        'git_blob_sha256':sha(raw), 'git_blob_bytes':len(raw),
        'working_tree_sha256':sha(working), 'working_tree_bytes':len(working),
        'normalized_working_tree_matches_blob':working.replace(b'\r\n', b'\n') == raw,
        'retained_exact_blob':str(target)})
receipts = []
for name in ['20260913-014401-unittest-ce463543', '20260913-014404-ruff-b49cc393', '20260913-014405-pyright-1e225c35']:
    path = run/(name+'.receipt.json')
    doc = json.loads(path.read_bytes())
    row = {'receipt':file_record(path), 'exit_code':doc['exitCode'], 'timed_out':doc['timedOut']}
    for stream in ['stdout', 'stderr']:
        record = file_record(pathlib.Path(doc[stream]))
        record['matches_receipt_hash'] = record['sha256'] == doc[stream+'Sha256']
        assert record['matches_receipt_hash']
        row[stream] = record
    receipts.append(row)
blocked = pathlib.Path('C:/h/continuity-qualification/state/run-20260913-104731-71436f55/independent-review-d07aebaf3cf242ccbf4a5bab666e3e9e.json')
manifest = {
    'schema_version':1,
    'reviewer':'/root/delivery_curator',
    'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status':'revise',
    'subject':{'repository':str(repo),'commit':head,'tree':tree,
        'base':git('rev-parse','b19b2a1').decode().strip(),'worktree_status_porcelain':status},
    'scope':'Read-only independent repaired-source review and bounded external in-memory-adapter probes; no full suite, production authority, repository edits or publication.',
    'immutable_source_artifacts':sources,
    'independent_artifacts':[file_record(root/name) for name in ['REVIEW.md','status.json','probe.py','probe-results.json','probe.stderr.txt','seal_manifest.py']],
    'attributed_runner_receipts_with_verified_log_hashes':receipts,
    'blocked_cli_review':file_record(blocked),
    'limitations':['Unsigned local evidence is not externally authenticated.','No full-suite execution by this reviewer.','Historical Windows process result was inspected, not rerun against the repair.','Preexisting-warning status is parent attribution.'],
}
(root/'REVIEW-MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'head':head,'tree':tree,'clean':not status,'status':'revise','manifest':file_record(root/'REVIEW-MANIFEST.json'),'report':file_record(root/'REVIEW.md'),'status_document':file_record(root/'status.json')}, indent=2))
