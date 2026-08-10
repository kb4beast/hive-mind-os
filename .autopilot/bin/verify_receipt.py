#!/usr/bin/env python3
from autopilot import main

if __name__ == "__main__":
    raise SystemExit(main(["verify-receipt", *(__import__("sys").argv[1:])]))
