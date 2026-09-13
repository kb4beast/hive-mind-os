"""Windows spawned-process lock control; no real campaign execution."""
import json
import multiprocessing as mp
import pathlib
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path[:0] = ['C:/h/continuity-draft1/src', 'C:/h/continuity-draft1/tests']
from hive_mind_os.campaign_continuity import (
    CampaignContinuityController, CampaignCandidate, CompletedDelivery,
    ContinuityScope, ContinuityError, EvidenceReference, RepositorySubject,
)
from test_campaign_continuity import MemoryAdapter

def scope():
    ref = EvidenceReference('source:fixture', 'sha256:' + 'c' * 64)
    subject = RepositorySubject('repo', 'worktree', 'a' * 40, 'b' * 40)
    return ContinuityScope('campaign', 'delivery', subject, 'owner', 'sha256:' + 'a' * 64,
        'sha256:' + 'b' * 64, (ref,), ('alpha',), 1000)

def hold(root, entered, release, results):
    controller = CampaignContinuityController(root, scope(), clock=lambda: 100)
    class HeldAdapter(MemoryAdapter):
        def observe(self, bound_scope, evidence):
            entered.set()
            if not release.wait(10):
                raise RuntimeError('probe release timed out')
            return super().observe(bound_scope, evidence)
    adapter = HeldAdapter()
    state = controller.step(adapter)
    results.put({'first_phase': state['phase'], 'launches': len(adapter.launches)})

def compete(root, results):
    try:
        CampaignContinuityController(root, scope(), clock=lambda: 100)
    except ContinuityError as error:
        results.put({'second_constructor': error.code})

if __name__ == '__main__':
    context = mp.get_context('spawn')
    with tempfile.TemporaryDirectory(prefix='continuity-concurrency-') as root:
        bound = scope()
        controller = CampaignContinuityController(root, bound, clock=lambda: 100)
        controller.record_delivery(CompletedDelivery('delivery', bound.subject, bound.scope_digest,
            True, True, bound.evidence))
        controller.record_candidate(CampaignCandidate('alpha', 'sha256:' + 'd' * 64,
            bound.subject, bound.scope_digest, bound.authority_digest, 1, True, 'adapt', bound.evidence))
        controller.step(MemoryAdapter())
        entered, release, results = context.Event(), context.Event(), context.Queue()
        first = context.Process(target=hold, args=(root, entered, release, results))
        second = context.Process(target=compete, args=(root, results))
        try:
            first.start()
            if not entered.wait(10):
                raise RuntimeError('first process did not enter observe')
            second.start()
            second.join(10)
            if second.is_alive():
                raise RuntimeError('competing process did not finish')
            release.set()
            first.join(10)
            if first.is_alive():
                raise RuntimeError('first process did not finish')
            print(json.dumps({'process_exit_codes': [first.exitcode, second.exitcode],
                'results': [results.get(timeout=5), results.get(timeout=5)],
                'final_phase': controller.checkpoint()['phase']}, indent=2))
        finally:
            release.set()
            for process in (first, second):
                if process.pid is not None and process.is_alive():
                    process.kill()
                    process.join(5)
