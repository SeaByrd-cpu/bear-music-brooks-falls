#!/usr/bin/env python3

import subprocess
import json
import requests
import sys
import signal

RENDER_INGEST_URL = "https://music-of-the-bears.onrender.com/ingest"

detector = None
running = True


def stop_cleanly(*args):
    global running

    running = False
    print("\n🐻 Sender stopping...")

    if detector:
        try:
            detector.terminate()
        except Exception:
            pass

    sys.exit(0)


signal.signal(signal.SIGINT, stop_cleanly)
signal.signal(signal.SIGTERM, stop_cleanly)


detector = subprocess.Popen(
    ["python3", "detector.py"],
    stdout=subprocess.PIPE,
    stderr=sys.stderr,
    text=True
)

print("🐻 Sender running...")
print(f"Sending bear JSON to: {RENDER_INGEST_URL}")

try:
    for line in detector.stdout:
        if not running:
            break

        line = line.strip()

        if not line.startswith("{"):
            continue

        try:
            payload = json.loads(line)

            r = requests.post(
                RENDER_INGEST_URL,
                json=payload,
                timeout=1
            )

            if r.status_code != 200:
                print("Upload failed:", r.status_code, r.text)

        except requests.exceptions.RequestException as e:
            print("Upload error:", e)

        except json.JSONDecodeError:
            print("Bad JSON:", line)

except KeyboardInterrupt:
    stop_cleanly()

finally:
    if detector:
        try:
            detector.terminate()
        except Exception:
            pass

    print("🐻 Sender stopped.")