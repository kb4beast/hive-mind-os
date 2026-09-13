# Independent diagnostic alternative assessment

Reviewer: `/root/continuity_repair_builder`. This supplements, without changing,
the sealed original Windows collector examination.

The builder's actual frozen-module control passed all 23 methods in 2.904s on
Python3.12.10, with clean terminal receipt, actual/effective exit0 and no timeout.
The two external stress variants modify only the diagnostic interval from15s
to0.01s/0.001s. Both exit with3221225477 (0xC0000005) after6/5 diagnostic dumps,
without a terminal marker. The retained output again ends mid-frame. This is
strong reproduction evidence for a native watchdog/frame-walk failure mechanism;
the original CI numeric exit is still unavailable and must not be retroactively
invented. The successful control alone would not establish robustness, since its
duration is shorter than the unmodified first diagnostic interval.

Root's retained CPython3.12.10 source shows `faulthandler_thread` invokes the
thread traceback walker from its native watchdog, whereas the ordinary Python
`dump_traceback` entry point does not release the GIL before that walk. A Python
timer thread calling ordinary `dump_traceback(all_threads=True)` is therefore
a justified candidate correction for GIL-enabled builds. This conclusion draws
on retained primary source, not copied third-party implementation.

Acceptance conditions:

- Keep the independent parent process deadline300s/module and900s/overall,
  tree termination, code124, partial logs, actual exit and failure metadata.
- Stop and join the diagnostic thread before emitting the terminal success
  marker, including test exceptions. No orphan or later post-receipt dump.
- Preserve all original count, terminal-marker, warning, skip, source binding,
  no-activation and negative timeout assertions. Diagnostic exceptions must be
  surfaced in a way that cannot produce a falsely clean success receipt.
- Exercise the candidate diagnostic loop while frames change, along with a
  normal completion/cleanup case and the existing externally enforced timeout
  cases. An accelerated diagnostic interval is a stress parameter only, not a
  relaxed acceptance threshold or a substitute for real deadlines.

Known limit: a Python timer cannot obtain the GIL while another thread holds it
indefinitely in native code. It therefore cannot promise a stack dump in that
case. The independently running PowerShell parent still enforces the timeout
and preserves partial logs/process state; absence of a stack must be explicit
diagnostic incompleteness, never a pass or an unbounded wait. This trades an
unsafe asynchronous stack sampler for best-effort cooperative diagnostics while
retaining execution and authority gates. It does not establish guarantees for
free-threaded Python builds or arbitrary native extensions.

This is review guidance, not approval of an unseen implementation. Exact repair
source and its executable regression evidence require the separately pinned
follow-up review requested by root.
