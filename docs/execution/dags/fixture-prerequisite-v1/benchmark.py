#!/usr/bin/env python3
"""Hermetic root-CI receipt helper; does not change repository behavior."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
FAILURE="test_autopilot_fixture_seed.FixtureSeedAPISurfaceTests.test_future_fixture_api_is_available"
def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(v): return "sha256:"+hashlib.sha256(canon(v)).hexdigest()
def verify(r, phase):
 m=dict(r); supplied=m.pop("receipt_digest",None)
 if supplied!=digest(m): raise ValueError("receipt digest mismatch")
 if r.get("phase")!=phase: raise ValueError("receipt phase mismatch")
 if r.get("environment",{}).get("PYTHONNOUSERSITE")!="1" or r.get("environment",{}).get("PYTHONPATH") is not None: raise ValueError("environment is not hermetic")
 if phase=="causality":
  result=r.get("result",{}); inv=result.get("failure_ids",[])+result.get("error_ids",[])
  if result.get("tests_run")!=1050 or result.get("skips")!=8 or inv!=[FAILURE]: raise ValueError("not the sealed fixture-only baseline inventory")
  if not r.get("import_resolution",{}).get("under_repository_src"): raise ValueError("import did not resolve under repository src")
def self_test():
 r={"phase":"causality","environment":{"PYTHONNOUSERSITE":"1","PYTHONPATH":None},"import_resolution":{"under_repository_src":True},"result":{"tests_run":1050,"skips":8,"failure_ids":[FAILURE],"error_ids":[]}};r["receipt_digest"]=digest(r);verify(r,"causality")
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True);s.add_parser("self-test");v=s.add_parser("verify");v.add_argument("--receipt",required=True);v.add_argument("--phase",required=True);a=p.parse_args()
 if a.cmd=="self-test":self_test();print(json.dumps({"self_test":"passed"}));return 0
 try:verify(json.loads(Path(a.receipt).read_text()),a.phase);print(json.dumps({"verified":True,"receipt":a.receipt}))
 except (OSError,json.JSONDecodeError,ValueError) as e:print(json.dumps({"verified":False,"error":str(e)}));return 2
if __name__=="__main__":raise SystemExit(main())
