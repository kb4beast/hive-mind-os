import json
import unittest
from pathlib import Path
from hive_mind_os.campaign_contracts import *
from hive_mind_os.runtime_contracts import canonical_digest
D="sha256:"+"0"*64; S="0"*40; T="2026-09-14T01:00:00Z"
O=canonical_digest("objective")
def pkg(*,deps=(),target="src",req=("R01",),state=PackageState.READY,authority=D):
 a=AcceptanceBinding("A01","test","receipt", "passed","curator",ClaimLevel.RUNTIME)
 return WorkPackage(1,1,"PKG-one","MISSION-one","objective",target,req,deps,("test",),(a,),"T2",ResourceAllocation(1,1,1),("receipt",),"rollback",authority,state,T)
def mission(*,packages=None,req=("R01",),target="src",parent=None,revision=1):
 return CampaignMission(1,revision,"MISSION-one","objective",target,req,(pkg(),) if packages is None else packages,D,CampaignState.READY,T,parent)
class TestCampaign(unittest.TestCase):
 def test_paths_coverage_cycle_and_authority_close(self):
  self.assertEqual(pkg(target="src\\one").target_boundary,"src/one")
  with self.assertRaises(CampaignContractError):mission(packages=(pkg(target="other"),))
  with self.assertRaises(CampaignContractError):mission(req=("R01","R02"))
  with self.assertRaises(CampaignContractError):mission(packages=(pkg(deps=("PKG-two",)),pkg()))
  with self.assertRaises(CampaignContractError):mission(packages=(pkg(authority="sha256:"+"1"*64),))
 def test_exact_nested_acceptance_and_receipts(self):
  with self.assertRaises(CampaignContractError):ResourceAllocation(True,1,1)
  with self.assertRaises(CampaignContractError):pkg().__class__(1,1,"PKG-x","MISSION-one","o","src",("R01",),(),("test",),(object(),),"T",ResourceAllocation(1,1,1),("receipt",),"r",D,PackageState.READY,T)
  c=CandidateCompletion("MISSION-one","PKG-one",D,S,D,S,D,(("receipt",D),),(("A01",D),),"implemented",1,O)
  self.assertEqual(c.disposition,"implemented")
  with self.assertRaises(CampaignContractError):CandidateCompletion("MISSION-one","PKG-one",D,S,D,"1"*40,"sha256:"+"1"*64,(("receipt",D),),(("A01",D),),"no-change",1,O)
 def test_kernel_adapter_and_historical_gate(self):
  self.assertEqual(campaign_state_event(CampaignState.READY),("mission.transition",{"status":"READY"}))
  self.assertEqual(package_state_event(PackageState.VERIFYING),("work.transition",{"status":"AWAITING_VERIFICATION"}))
  raw=b'{"schema_version":0,"historical_inert_plan":true,"fixture_id":"N04-HISTORICAL-V0","candidate":"candidate/app.txt"}'
  self.assertEqual(parse_historical_inert_plan(raw,fixture_mode=True)["schema_version"],0)
  with self.assertRaises(CampaignContractError):parse_historical_inert_plan(raw)
  root=Path(__file__).parent/"fixtures"/"campaign_contracts"
  self.assertEqual(parse_historical_inert_plan((root/"historical-v0.json").read_bytes(),fixture_mode=True)["fixture_id"],"N04-HISTORICAL-V0")
  with self.assertRaises(CampaignContractError):parse_historical_inert_plan((root/"historical-v0-invalid-extra.json").read_bytes(),fixture_mode=True)
 def test_successor_authenticated(self):
  p=mission(); child=mission(parent=p.digest,revision=2)
  SuccessorContract(p,child)
  with self.assertRaises(CampaignContractError):SuccessorContract(p,mission(parent=p.digest,revision=1))
 def test_completion_pairs_are_deep_immutable_and_serialized(self):
  c=CandidateCompletion("MISSION-one","PKG-one",D,S,D,S,D,(("receipt",D),),(("A01",D),),"implemented",1,O)
  p=WorkPackage(1,1,"PKG-one","MISSION-one","objective","src",("R01",),(),("test",),(AcceptanceBinding("A01","test","receipt","passed","curator",ClaimLevel.RUNTIME),),"T2",ResourceAllocation(1,1,1),("receipt",),"rollback",D,PackageState.COMPLETED,T,c)
  self.assertEqual(p.to_document()["completion"]["commit_sha"],S)
  self.assertIsInstance(c.output_receipts[0],tuple)
 def test_terminal_claim_consistency(self):
  c=CandidateCompletion("MISSION-one","PKG-one",D,S,D,S,D,(("receipt",D),),(("A01",D),),"implemented",1,O)
  bad=AcceptanceBinding("A01","test","receipt","failed","curator",ClaimLevel.RUNTIME)
  with self.assertRaises(CampaignContractError):WorkPackage(1,1,"PKG-one","MISSION-one","objective","src",("R01",),(),("test",),(bad,),"T2",ResourceAllocation(1,1,1),("receipt",),"rollback",D,PackageState.COMPLETED,T,c)
if __name__=="__main__":unittest.main()
