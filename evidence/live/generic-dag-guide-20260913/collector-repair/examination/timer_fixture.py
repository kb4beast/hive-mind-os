import faulthandler, sys, time
print(sys.version, flush=True)
faulthandler.dump_traceback_later(15, repeat=True)
try:
    time.sleep(15.2)
finally:
    faulthandler.cancel_dump_traceback_later()
print("SURVIVED_DIAGNOSTIC_INTERVAL", flush=True)
