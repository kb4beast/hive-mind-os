"""Distinguish diagnostic faulthandler timer from actual process deadline."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

out = Path(__file__).resolve().parent
python = r'C:\Users\beesp\AppData\Local\Programs\Python\Python312\python.exe'
source = '''import faulthandler, sys, time
print(sys.version, flush=True)
faulthandler.dump_traceback_later(15, repeat=True)
try:
    time.sleep(15.2)
finally:
    faulthandler.cancel_dump_traceback_later()
print("SURVIVED_DIAGNOSTIC_INTERVAL", flush=True)
'''
(out / 'timer_fixture.py').write_text(source, encoding='utf-8')
start = time.monotonic()
result = subprocess.run([python, '-I', '-B', str(out / 'timer_fixture.py')],
                        capture_output=True, timeout=30)
(out / 'timer.stdout.txt').write_bytes(result.stdout)
(out / 'timer.stderr.txt').write_bytes(result.stderr)
report = dict(purpose='Diagnostic timer alone does not terminate this interpreter',
              exit_code=result.returncode, seconds=time.monotonic() - start,
              stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
              stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),
              stdout=result.stdout.decode(), stderr=result.stderr.decode())
(out / 'TIMER-PROBE.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
assert result.returncode == 0
assert b'SURVIVED_DIAGNOSTIC_INTERVAL' in result.stdout
assert b'Timeout (0:00:15)!' in result.stderr
print(json.dumps(report, indent=2))
