# Independent Windows collector failure examination

Reviewer: `/root/continuity_repair_builder`, independent of the repair builder.
Pinned candidate: `3bfd4edd504a1c1dc6b4448941dc38f4fdfcdbba`, tree
`b94944774c9cd08386eecd4822ae6e7f8e3457a0`. Historical nested fixture:
`1038b5a7d2eb49904c59957ad3e989af8bb2fcc5`. No candidate edits or full gates.

## Evidence-supported conclusion

The log does **not** show a 15-second process deadline. The collector bootstrap
calls `faulthandler.dump_traceback_later(15, repeat=True)` at line 344; the
15-second banner is the diagnostic timer. Actual deadlines are 300 seconds per
module and 900 seconds overall. The process runner only invokes tree termination
after its bounded WaitForExit returns false, preserving timeout state and code124.

The outer fixture's adjacent completion timestamps span approximately 23.817
seconds (19:10:08.0558906 to 19:10:31.8733610 UTC), including worktree setup,
collector startup and four modules. Its exception is the generic failed-validation
throw at line850. Typed timeout throws at lines845/847 precede that branch, so
the pinned script had not classified this as a deadline expiration. The retained
transcript stops in the fourth module, after fourteen passing methods, at an
incomplete timer stack dump. No terminal marker exists for that module.

The module loop breaks early on a nonzero child effective exit or a timeout.
Together these facts support an early non-timeout child failure. The numeric
exit code and underlying cause cannot be recovered from this transcript.
Native failure during diagnostic dumping is a hypothesis, not an established
root cause. Increasing the existing time limits is unsupported by this evidence.

The sampled `_json_depth` line119 is an iterative walk over parsed bounded JSON;
a single interrupted stack sample does not establish an infinite loop or a DAG
recovery defect. The same-named top-level test passed later in the job, but that
test ran current code rather than necessarily the historical nested fixture;
it does not by itself prove historical nested correctness.

## Evidence gap and repair acceptance

The collector writes evidence.json before throwing. That file includes actual
and effective exit codes, timed_out, timeout_scope, per-module durations/PIDs,
terminal-receipt validity and termination results. The fixture's failure branch
prints only focused-test-output.txt; TemporaryDirectory cleanup then discards
the structured metadata. Preserve these fields and raw artifact hashes in
failure diagnostics so a future failure is classifiable. Do not invent the
missing original numeric exit code or label the present event a confirmed crash.

A nonweakening repair must retain the finite 300s/900s process limits and owned
tree cleanup; preserve all negative timeout tests, unrelated-process survival,
nonzero exit propagation, module/count completion and terminal-receipt checks.
It must retain `activation_authorized=false`, `qualification_eligible=false`
for this dirty review fixture, inert manifest/template checks, exact source
binding and warning/skip rejection. No retry-to-success or ignored receipt is
acceptable. If changing diagnostic dumping is proposed, establish its mechanism
with a bounded reproduction and preserve failure observability independently
of the execution deadline.

`diagnostic_probe.py` supplies a narrow control: the exact repeating 15-second
faulthandler call is allowed to fire in an otherwise inert Python3.12 process;
the process then emits a completion marker. It neither reproduces nor rules out
the interrupted CI dump. Its purpose is only to distinguish timer output from
process termination. Full probe receipts and source pins accompany this report.
