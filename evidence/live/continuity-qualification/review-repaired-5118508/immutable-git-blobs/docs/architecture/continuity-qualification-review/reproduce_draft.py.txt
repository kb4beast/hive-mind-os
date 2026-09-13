"""Independent bounded draft reproductions; disposable local adapters only."""
import json
import os
import pathlib
import sys
import tempfile
from dataclasses import replace
from unittest.mock import patch

sys.dont_write_bytecode = True
SUBJECT = pathlib.Path('C:/h/continuity-draft1')
sys.path[:0] = [str(SUBJECT / 'src'), str(SUBJECT / 'tests')]
from hive_mind_os.campaign_continuity import (
    CampaignContinuityController, CampaignCandidate, CompletedDelivery,
    ContinuityScope, ContinuityError, EvidenceReference, RepositorySubject,
)
from test_campaign_continuity import MemoryAdapter

def digest(c):
    return 'sha256:' + c * 64

def fixture(root, *, scope=None, now=None):
    subject = RepositorySubject('repo:fixture', 'worktree:fixture', 'a' * 40, 'b' * 40)
    evidence = (EvidenceReference('source:fixture', digest('c')),)
    scope = scope or ContinuityScope('campaign', 'delivery', subject, 'owner',
        digest('a'), digest('b'), evidence, ('alpha',), 1000)
    clock = now if now is not None else [100]
    controller = CampaignContinuityController(root, scope, clock=lambda: clock[0])
    delivery = CompletedDelivery(scope.delivery_id, scope.subject, scope.scope_digest,
                                 True, True, scope.evidence)
    candidate = CampaignCandidate('alpha', digest('d'), scope.subject,
        scope.scope_digest, scope.authority_digest, 10, True, 'adapt', scope.evidence)
    controller.record_delivery(delivery)
    controller.record_candidate(candidate)
    return controller, scope, candidate, clock

results = {}
with tempfile.TemporaryDirectory(prefix='continuity-review-') as directory:
    root = pathlib.Path(directory)
    controller, scope, candidate, now = fixture(root / 'expired')
    adapter = MemoryAdapter()
    controller.step(adapter)
    adapter.raise_after_effect = True
    controller.step(adapter)
    now[0] = scope.expires_at
    result = controller.step(adapter)
    results['lost_effect_then_expiry'] = dict(phase=result['phase'], blocker=result['blocker'],
        real_operations=len(adapter.operations), inspections=len(adapter.inspections), launches=len(adapter.launches))

    controller, scope, _, now = fixture(root / 'scope-for-budget')
    controller, scope, _, now = fixture(root / 'budget', scope=replace(scope, maximum_reconciliations=1))
    adapter = MemoryAdapter()
    controller.step(adapter)
    adapter.raise_after_effect = True
    controller.step(adapter)
    result = controller.step(adapter)
    results['lost_effect_on_final_reconciliation'] = dict(phase=result['phase'], blocker=result['blocker'],
        real_operations=len(adapter.operations), inspections=len(adapter.inspections), launches=len(adapter.launches))

    controller, scope, _, _ = fixture(root / 'typed-observe')
    adapter = MemoryAdapter()
    before = len(controller.events())
    raised = []
    with patch.object(adapter, 'observe', side_effect=ContinuityError('authority-denied', 'test denial')) as observation:
        for _ in range(2):
            try:
                controller.step(adapter)
            except ContinuityError as error:
                raised.append(error.code)
    results['typed_observer_denial'] = dict(raised=raised, observe_calls=observation.call_count,
        added_events=len(controller.events()) - before, phase=controller.checkpoint()['phase'])

    controller, scope, _, _ = fixture(root / 'malformed-observer')
    adapter = MemoryAdapter()
    adapter.observation_changes = {'observer_id': ['not-an-identifier']}
    controller.step(adapter)
    result = controller.step(adapter)
    results['malformed_observer_accepted'] = dict(phase=result['phase'], launches=len(adapter.launches))

    target, scope, _, _ = fixture(root / 'journal-target')
    foreign_scope = replace(scope, campaign_id='foreign-campaign', scope_digest=digest('e'),
        authority_digest=digest('f'), subject=replace(scope.subject, worktree_id='foreign-worktree'))
    foreign, _, _, _ = fixture(root / 'journal-foreign', scope=foreign_scope)
    foreign.step(MemoryAdapter())
    # Simulate accidentally restoring a valid wrong-scope journal while a
    # controller object remains alive. All files are disposable temp fixtures.
    for path in (root / 'journal-target').glob('event-*.json'):
        path.unlink()
    for path in (root / 'journal-foreign').glob('event-*.json'):
        (root / 'journal-target' / path.name).write_bytes(path.read_bytes())
    class CapturingAdapter(MemoryAdapter):
        def launch(self, operation_id, candidate, scope):
            self.launch_binding = (candidate.subject.worktree_id, scope.subject.worktree_id,
                                   candidate.scope_digest, scope.scope_digest)
            return super().launch(operation_id, candidate, scope)
    adapter = CapturingAdapter()
    result = target.step(adapter)
    results['wrong_scope_journal_after_construction'] = dict(phase=result['phase'],
        launch_binding=adapter.launch_binding, launches=len(adapter.launches))

    controller, scope, _, _ = fixture(root / 'array-json')
    (root / 'array-json' / 'event-00000001.json').write_text('[]\n', encoding='utf-8')
    try:
        controller.step(MemoryAdapter())
    except Exception as error:
        results['malformed_journal_root'] = dict(type=type(error).__name__, code=getattr(error, 'code', None))

    external = root / 'outside-lock-target'
    external.write_bytes(b'')
    linked = root / 'linked-state'
    linked.mkdir()
    os.link(external, linked / '.writer.lock')
    fixture(linked)
    results['linked_lock_writes_outside_state'] = dict(outside_bytes=external.read_bytes().hex())

    controller, scope, _, _ = fixture(root / 'detached-return')
    checkpoint = controller.checkpoint()
    checkpoint['phase'] = 'launched'
    checkpoint['candidates'].clear()
    events = controller.events()
    events[-1]['checkpoint']['launches'] = 999
    results['returned_state_is_detached_control'] = dict(phase=controller.checkpoint()['phase'],
        candidates=list(controller.checkpoint()['candidates']), launches=controller.checkpoint()['launches'])

print(json.dumps(results, indent=2))
