import math,unittest
from pathlib import Path
from hive_mind_os.campaign_metrics import *
D="sha256:"+"a"*64
class T(unittest.TestCase):
 def test_json_closed_and_deep_frozen(self):
  with self.assertRaises(CampaignMetricsError):load_match_protocol(Path("docs/benchmarks/whole-os-match-protocol.json"))
  p=load_match_protocol_for_inspection(Path("docs/benchmarks/whole-os-match-protocol.json"));self.assertTrue(p.blockers)
  self.assertFalse(hasattr(p,"schedule"));self.assertFalse(hasattr(p,"entrant_recipes"))
 def test_nan_interval_and_margin_fail_closed(self):
  with self.assertRaises(CampaignMetricsError):AttemptMetric("f","t","v",D,D,D,D,"eligible","success",math.nan,0,0,None,"unknown",None,"unknown")
  with self.assertRaises(CampaignMetricsError):PairedInterval(0,1,-1,2)
  self.assertFalse(noninferior(PairedInterval(0,-.05,.1,30),hard_gates_pass=True))
  with self.assertRaises(CampaignMetricsError):noninferior(PairedInterval(0,0,.1,30),hard_gates_pass=1)
 def test_bootstrap_and_decisions(self):
  pairs={f"f{x}":(1.,) for x in range(12)};a=paired_family_bootstrap(pairs,seed=1);self.assertEqual(a,paired_family_bootstrap(pairs,seed=1))
  with self.assertRaises(CampaignMetricsError):paired_family_bootstrap({"a":()},seed=1)
  with self.assertRaises(CampaignMetricsError):paired_family_bootstrap({"a":(1.,)},seed=1)
  n=PairedInterval(0,-.04,.04,30);cheap=PairedInterval(.8,.7,.9,30);fast=PairedInterval(.8,.7,.9,30)
  self.assertEqual(decide_match(n,cheap,fast,left_hard_gates=True,right_hard_gates=True),"LEFT")
  self.assertEqual(decide_match(n,PairedInterval(1.2,1.15,1.3,30),PairedInterval(1.05,1.0,1.09,30),left_hard_gates=True,right_hard_gates=True),"RIGHT")
  self.assertEqual(decide_match(n,cheap,fast,left_hard_gates=False,right_hard_gates=True),"QUARANTINE_LEFT")
  self.assertEqual(decide_match(n,cheap,fast,left_hard_gates=False,right_hard_gates=False),"QUARANTINE_BOTH")
 def test_bracket_track_bye_inconclusive_lease(self):
  pairs=schedule_round(("MB0","MB1"),{"MB0":0,"MB1":0},{},round_number=1,inconclusive_meetings={frozenset(("MB0","MB1")):2})
  self.assertEqual(pairs[0].right,None)
 def test_summary_keeps_not_attempted(self):
  r=AttemptMetric("f","t","v",D,D,D,D,"eligible","not_attempted",None,None,None,None,"unknown",None,"unknown")
  self.assertEqual(summarize_attempts([r])["eligible_not_attempted"],1)
 def test_negative_partial_and_state_mutations_reject(self):
  with self.assertRaises(CampaignMetricsError):AttemptMetric("f","t","v",D,D,D,D,"eligible","success",-1,0,0,None,"unknown",None,"unknown")
  with self.assertRaises(CampaignMetricsError):PairedInterval(None,None,1,0)
  with self.assertRaises(CampaignMetricsError):PairedInterval(None,None,None,1)
  p=load_match_protocol_for_inspection("docs/benchmarks/whole-os-match-protocol.json");m={"MB0":0};s=BracketState(p.protocol_digest,"original","builder-component",losses=m);m["MB0"]=3
  self.assertEqual(s.losses["MB0"],0)
 def test_fixture_signed_stage_evidence_and_receipt_replay(self):
  key=b"fixture-only"; payload=D; sig=__import__("hmac").new(key,("eval|evaluator|"+payload+"|1").encode(),"sha256").hexdigest()
  envelope=SignedCustodyEnvelope("eval","evaluator",payload,sig,1);self.assertTrue(envelope.verify_fixture_hmac(key))
  evidence=StageEvidence("final",D,D,D,D,envelope,REQUIRED_STRATA,30,3,7);self.assertEqual(evidence.repetitions,3)
  receipt=IssuedReceipt("final",1,"MC0","MH1",D,"task",7,"eval",D)
  with self.assertRaises(CampaignMetricsError):reject_receipt_replay((receipt,receipt))
  with self.assertRaises(CampaignMetricsError):StageEvidence("final",D,D,D,D,envelope,REQUIRED_STRATA,12,1,7)
if __name__=="__main__":unittest.main()
