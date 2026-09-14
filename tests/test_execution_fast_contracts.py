import tempfile, unittest
from pathlib import Path
from hive_mind_os.outcome_graph import *
from hive_mind_os.discovery_backlog import *
from hive_mind_os.role_coverage import *
from hive_mind_os.builder_session import *
from hive_mind_os.candidate_qualification import *
from hive_mind_os.pr_feedback import *
from hive_mind_os.self_upgrade import *

class ExecutionContractsTests(unittest.TestCase):
    def test_graph_orders_and_rejects_cycles(self):
        a=OutcomeWorkPackage("a",("o",),allowed_paths=("src",)); b=OutcomeWorkPackage("b",("p",),("a",),allowed_paths=("tests",))
        self.assertEqual([p.package_id for p in ready_packages(compile_outcome_graph((a,b),base_snapshot="base"))],["a"])
        with self.assertRaises(GraphError): compile_outcome_graph((OutcomeWorkPackage("x",("o",),("y",)),OutcomeWorkPackage("y",("o",),("x",))),base_snapshot="b")
    def test_backlog_is_tenant_scoped_and_deterministic(self):
        q=DiscoveryBacklog(); s=DiscoverySignal("t","r","h","bug",("e",),"d",.9); self.assertTrue(q.ingest(s)); self.assertFalse(q.ingest(s)); q.add(BacklogCandidate("i",("claim",),10,"test",1,.1)); self.assertEqual(q.select().selected_ids,("i",))
    def test_eight_role_receipt(self):
        p=RoleCoveragePlan("m","c","g","p",tuple(RoleRow(r,r) for r in ROLES)); self.assertTrue(build_coverage(p,{r:("ok","e") for r in ROLES}).complete)
    def test_builder_scope_and_qualification(self):
        s=BuilderSession(BuilderSessionSpec("p","a","t","base",("src",))); s.checkpoint("cand",("src/a.py",)); self.assertEqual(s.run().disposition,BuilderDisposition.READY_FOR_VERIFICATION)
        with self.assertRaises(PermissionError): s.validate_paths(("secrets.txt",))
        self.assertEqual(CandidateQualifier(lambda _:1).qualify(QualificationRequest("c","b",("unit",),(),"low","s","t","e","curator")).disposition,QualificationDisposition.PASSED)
    def test_feedback_and_upgrade_fail_closed(self):
        o=FeedbackObservation("gh","1","h","e","bot",1,"test failed","d"); f=FeedbackObserver(); self.assertEqual(f.observe(o,"h").decision,FeedbackDecision.ACTIONABLE); self.assertEqual(f.observe(o,"h").decision,FeedbackDecision.DUPLICATE)
        c=RuntimeChallenger("v","d","p","src","dep","mig","rb","plan","pass","same","same","judge","none"); self.assertEqual(UpgradeController().decide(c,qualification_passed=True,heldout_passed=True,rollback_valid=True).decision,UpgradeDecision.QUARANTINE)
