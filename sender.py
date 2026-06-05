#!/usr/bin/env python3

import subprocess
import json
import requests
import sys

RENDER_INGEST_URL = "https://music-of-the-bears.onrender.com/ingest"

detector = subprocess.Popen(
    ["python3", "detector.py"],
    stdout=subprocess.PIPE,
    stderr=sys.stderr,
    text=True
)

print("🐻 Sender running...")
print(f"Sending bear JSON to: {RENDER_INGEST_URL}")

for line in detector.stdout:
    line = line.strip()

    if not line.startswith("{"):
        continue

    try:
        payload = json.loads(line)

        r = requests.post(
            RENDER_INGEST_URL,
            json=payload,
            timeout=5
        )

        if r.status_code != 200:
            print("Upload failed:", r.status_code, r.text)

    except Exception as e:
        print("Sender error:", e)