#!/usr/bin/env python3
import sys
import httpx

try:
    r = httpx.get("http://localhost:8000/health", timeout=5)
    if r.status_code == 200:
        print("OK")
        sys.exit(0)
    print(f"UNHEALTHY: {r.status_code}")
    sys.exit(1)
except Exception as e:
    print(f"UNREACHABLE: {e}")
    sys.exit(1)
