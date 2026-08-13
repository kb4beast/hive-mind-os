#!/usr/bin/env python3
"""Fail-closed utility for the corrected-source FPCR v2 court."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, tempfile, time
from pathlib import Path
from specs import EVALUATED_COMMIT, EVALUATED_TREE, REJECTED_TUPLES, CLAIMED_DISCOVERY_COUNT, RUNNER_TIMEOUT_SECONDS

ROOT = Path(__file__).resolve().parents[3]
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":"), allow_nan=False).encode()
def digest(value): return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()
def finalize(receipt):
    body=dict(receipt); body.pop("receipt_digest",None); body["receipt_digest"]=digest(body); return body
def tuple_is_allowed(commit, tree):
    if (commit, tree) in REJECTED_TUPLES: raise ValueError("explicitly rejected source tuple")
    if (commit, tree) != (EVALUATED_COMMIT, EVALUATED_TREE): raise ValueError("source tuple is not the sole evaluated source")
def git_tree(repo: Path, commit: str) -> str:
    # Deliberately use the immutable commit expression, never HEAD.
    run=subprocess.run(["git","-C",str(repo),"rev-parse",f"{commit}^{{tree}}"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    return run.stdout.strip()
def require_source(repo: Path, commit=EVALUATED_COMMIT, tree=EVALUATED_TREE):
    tuple_is_allowed(commit,tree)
    actual=git_tree(repo,commit)
    if actual != EVALUATED_TREE: raise ValueError(f"immutable source tree mismatch: {actual}")
    return {"commit":EVALUATED_COMMIT,"tree":EVALUATED_TREE}
def verify(receipt, phase):
    body=dict(receipt); got=body.pop("receipt_digest",None)
    if got != digest(body): raise ValueError("receipt digest mismatch")
    if receipt.get("phase") != phase: raise ValueError("receipt phase mismatch")
    tuple_is_allowed(*(receipt.get("source",{}).get(key) for key in ("commit","tree")))
    if phase == "discovery" and receipt.get("discovery",{}).get("tests_discovered") not in {CLAIMED_DISCOVERY_COUNT, None}: raise ValueError("discovery count must be observed or explicit blocker")
    if phase == "execution":
        execution=receipt.get("execution",{}); environment=receipt.get("environment",{})
        if execution.get("attempts") != 1 or execution.get("timeout_seconds") != RUNNER_TIMEOUT_SECONDS: raise ValueError("execution must be exactly one 2700-second attempt")
        if environment.get("PYTHONNOUSERSITE") != "1" or environment.get("PYTHONPATH") is not None: raise ValueError("non-hermetic environment")
        if not receipt.get("transcript_digest"): raise ValueError("durable transcript missing")
    if phase in {"cross","integration"} and not receipt.get("conclusion"): raise ValueError("missing conclusion")
def write_receipt(path, receipt):
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(finalize(receipt),sort_keys=True,indent=2)+"\n",encoding="utf-8")
def discover_ids(repo):
    import unittest
    suite=unittest.defaultTestLoader.discover(str(repo / "tests")); ids=[]
    def walk(value):
        if isinstance(value,unittest.TestSuite):
            for child in value: walk(child)
        else: ids.append(value.id())
    walk(suite); return ids
def discovery_receipt(repo):
    source=require_source(repo); ids=discover_ids(repo)
    return finalize({"schema_version":1,"kind":"fpcr-discovery-v2","phase":"discovery","source":source,"discovery":{"tests_discovered":len(ids),"test_id_digest":"sha256:"+hashlib.sha256("\n".join(ids).encode()).hexdigest(),"claimed_count":CLAIMED_DISCOVERY_COUNT,"claim_reproduced":len(ids)==CLAIMED_DISCOVERY_COUNT},"conclusion":"discovery only; no execution or implementation authority"})
def execute_once(repo, receipt_path, transcript_path):
    source=require_source(repo); transcript={"schema_version":1,"source":source,"timeout_seconds":RUNNER_TIMEOUT_SECONDS,"attempts":1,"started_at_epoch":time.time()}
    with tempfile.TemporaryDirectory(prefix="fpcr-execute-") as temporary:
        venv=Path(temporary)/"venv"; interpreter=venv/"Scripts"/"python.exe"; environment=dict(os.environ); environment["PYTHONNOUSERSITE"]="1"; environment.pop("PYTHONPATH",None)
        setup=[[sys.executable,"-E","-s","-m","venv",str(venv)],[str(interpreter),"-E","-s","-m","pip","install","--disable-pip-version-check","--no-deps","-e",str(repo)]]; transcript["setup"]=[]
        for command in setup:
            run=subprocess.run(command,cwd=repo,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=RUNNER_TIMEOUT_SECONDS); transcript["setup"].append({"command":command,"returncode":run.returncode,"output":run.stdout})
            if run.returncode: break
        else:
            command=[str(interpreter),"-E","-s","-m","unittest","discover","-s","tests","-v"]
            try:
                run=subprocess.run(command,cwd=repo,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=RUNNER_TIMEOUT_SECONDS); transcript["root_ci"]={"command":command,"returncode":run.returncode,"output":run.stdout,"timed_out":False}
            except subprocess.TimeoutExpired as error: transcript["root_ci"]={"command":command,"returncode":124,"output":error.stdout or "","timed_out":True}
    transcript["finished_at_epoch"]=time.time(); write_receipt(transcript_path,transcript)
    write_receipt(receipt_path,{"schema_version":1,"kind":"fpcr-execution-v2","phase":"execution","source":source,"environment":{"PYTHONNOUSERSITE":"1","PYTHONPATH":None},"execution":{"attempts":1,"timeout_seconds":RUNNER_TIMEOUT_SECONDS,"command":"<venv>/Scripts/python.exe -E -s -m unittest discover -s tests -v"},"transcript_digest":digest(json.loads(Path(transcript_path).read_text())),"conclusion":"one execution receipt only; no implementation authority"})
def self_test():
    # The two invalid historical tuples must be rejected before any discovery/execution path.
    for bad in REJECTED_TUPLES:
        try: tuple_is_allowed(*bad)
        except ValueError: continue
        raise AssertionError("bad tuple was accepted")
    require_source(ROOT)
    receipt=finalize({"schema_version":1,"kind":"fpcr-discovery-v2","phase":"discovery","source":{"commit":EVALUATED_COMMIT,"tree":EVALUATED_TREE},"discovery":{"tests_discovered":CLAIMED_DISCOVERY_COUNT,"claim_reproduced":True},"conclusion":"self-test"}); verify(receipt,"discovery")
def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True); sub.add_parser("self-test")
    discover=sub.add_parser("discover"); discover.add_argument("--receipt",required=True); discover.add_argument("--source",type=Path,default=ROOT)
    execute=sub.add_parser("execute-once"); execute.add_argument("--receipt",required=True); execute.add_argument("--transcript",required=True); execute.add_argument("--source",type=Path,default=ROOT)
    check=sub.add_parser("source-check"); check.add_argument("--source",type=Path,default=ROOT)
    verifier=sub.add_parser("verify"); verifier.add_argument("--receipt",required=True); verifier.add_argument("--phase",required=True); args=parser.parse_args()
    try:
        if args.command == "self-test": self_test(); output={"self_test":"passed","source":require_source(ROOT)}
        elif args.command == "source-check": output={"source":require_source(args.source)}
        elif args.command == "discover": write_receipt(args.receipt,discovery_receipt(args.source)); output={"receipt":args.receipt}
        elif args.command == "execute-once": execute_once(args.source,args.receipt,args.transcript); output={"receipt":args.receipt,"transcript":args.transcript,"attempts":1}
        else: verify(json.loads(Path(args.receipt).read_text()),args.phase); output={"verified":True,"receipt":args.receipt}
        print(json.dumps(output,sort_keys=True)); return 0
    except (OSError,ValueError,subprocess.SubprocessError,json.JSONDecodeError) as error: print(json.dumps({"verified":False,"error":str(error)},sort_keys=True)); return 2
if __name__ == "__main__": raise SystemExit(main())
