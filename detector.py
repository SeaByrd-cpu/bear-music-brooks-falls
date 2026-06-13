#!/usr/bin/env python3
"""
detector.py — Brooks Falls bear detector + multi-blob tracker

Outputs JSON like:

{
  "bears": [
    {
      "id": 1,
      "x": 0.42,
      "y": 0.61,
      "area": 0.18,
      "speed": 0.012,
      "state": "bear"
    }
  ]
}

REQUIRES:
    pip install opencv-python yt-dlp numpy

USAGE:
    python3 detector.py
    python3 detector.py --debug
"""

import cv2
import sys
import time
import subprocess
import argparse
import numpy as np
import json


# ── Config ─────────────────────────────────────────────────────────────────────

DEFAULT_URL = "https://www.youtube.com/watch?v=4qSRIIaOnLI&t=276s"

MORPH_KERNEL = 5
MIN_BEAR_AREA = 2500

ROI = (0.0, 0.0, 1.0, 1.0)

WARMUP_FRAMES = 5
EMIT_INTERVAL = 0.07

MAX_BLOBS = 5

# ── Tracking config ────────────────────────────────────────────────────────────

NEXT_ID = 1
tracks = {}

MAX_TRACK_DISTANCE = 0.12
MAX_TRACK_AGE = 45

SMOOTH_POS = 0.12
SMOOTH_AREA = 0.08

MASS_SPEED_THRESHOLD = 0.006
MASS_AREA_THRESHOLD = 0.18


# ── Args ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--url", default=DEFAULT_URL, help="YouTube URL")
parser.add_argument("--debug", action="store_true", help="Show live debug window")
args = parser.parse_args()


# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"🐻 {msg}", file=sys.stderr, flush=True)


def error(msg):
    print(f"❌ {msg}", file=sys.stderr, flush=True)


def resolve_url(youtube_url):
    log("Resolving stream URL via yt-dlp...")

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m"
                "yt_dlp",
                "-f",
                "best[height<=480]",
                "-g",
                "--no-warnings",
                youtube_url
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        url = result.stdout.strip()

        if result.stderr.strip():
            error(result.stderr.strip())

        if not url:
            error("yt-dlp returned empty URL.")
            return None

        log("Stream URL resolved.")
        return url

    except FileNotFoundError:
        error("yt-dlp not found. Install with: pip install yt-dlp")
        sys.exit(1)

    except subprocess.TimeoutExpired:
        error("yt-dlp timed out.")
        return None



def update_tracks(detections):
    global NEXT_ID, tracks

    # age existing tracks
    for track in tracks.values():
        track["matched"] = False
        track["age"] += 1

    tracked_bears = []

    for bear in detections:

        best_id = None
        best_dist = MAX_TRACK_DISTANCE

        # find closest existing track
        for track_id, track in tracks.items():

            if track["matched"]:
                continue

            dx = bear["x"] - track["x"]
            dy = bear["y"] - track["y"]

            dist = (dx * dx + dy * dy) ** 0.5

            if dist < best_dist:
                best_dist = dist
                best_id = track_id

        # new track
        if best_id is None:

            track_id = NEXT_ID
            NEXT_ID += 1

            speed = 0.0

            smooth_x = bear["x"]
            smooth_y = bear["y"]
            smooth_area = bear["area"]

            life = 1

            old = {}

        # existing track
        else:

            track_id = best_id
            old = tracks[track_id]

            dx = bear["x"] - old["x"]
            dy = bear["y"] - old["y"]

            speed = (dx * dx + dy * dy) ** 0.5

            smooth_x = (
                old["x"] * (1.0 - SMOOTH_POS)
                + bear["x"] * SMOOTH_POS
            )

            smooth_y = (
                old["y"] * (1.0 - SMOOTH_POS)
                + bear["y"] * SMOOTH_POS
            )

            smooth_area = (
                old["area"] * (1.0 - SMOOTH_AREA)
                + bear["area"] * SMOOTH_AREA
            )

            life = old.get("life", 1) + 1

        # proposed state
        proposed_state = (
            "mass"
            if (
                speed < MASS_SPEED_THRESHOLD
                and smooth_area > MASS_AREA_THRESHOLD
            )
            else "bear"
        )

        # hysteresis / anti-flicker
        old_state = old.get("state", proposed_state)

        if old_state != proposed_state:
            state_counter = old.get("state_counter", 0) + 1
        else:
            state_counter = 0

        if state_counter < 8:
            state = old_state
        else:
            state = proposed_state

        # behavior
        if state == "mass":
            behavior = "mass"

        elif speed < 0.004:
            behavior = "still"

        elif speed < 0.018:
            behavior = "moving"

        else:
            behavior = "active"

        # save track
        tracks[track_id] = {
            "id": track_id,
            "x": smooth_x,
            "y": smooth_y,
            "area": smooth_area,
            "speed": round(speed, 4),
            "state": state,
            "age": 0,
            "life": life,
            "behavior": behavior,
            "state_counter": state_counter,
            "matched": True
        }

        # output payload
        tracked_bears.append({
            "id": track_id,
            "x": round(smooth_x, 4),
            "y": round(smooth_y, 4),
            "area": round(smooth_area, 4),
            "speed": round(speed, 4),
            "state": state,
            "life": life,
            "behavior": behavior
        })

    # remove dead tracks
    old_ids = [
        track_id
        for track_id, track in tracks.items()
        if track["age"] > MAX_TRACK_AGE
    ]

    for track_id in old_ids:
        del tracks[track_id]

    return tracked_bears


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    while True:
        stream_url = resolve_url(args.url)

        if not stream_url:
            log("Retrying in 15s...")
            time.sleep(15)
            continue

        width = 960
        height = 540

        ffmpeg_cmd = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            stream_url,
            "-vf",
            f"scale={width}:{height}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-"
        ]

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        log(f"FFmpeg stream opened: {width}x{height}")

        rx1 = int(ROI[0] * width)
        ry1 = int(ROI[1] * height)
        rx2 = int(ROI[2] * width)
        ry2 = int(ROI[3] * height)

        roi_w = rx2 - rx1
        roi_h = ry2 - ry1

        log(f"ROI: ({rx1},{ry1}) → ({rx2},{ry2})")

        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (MORPH_KERNEL, MORPH_KERNEL)
        )

        frame_count = 0
        last_emit = 0.0

        log("Detector running...")

        while True:
            raw_frame = proc.stdout.read(width * height * 3)

            if len(raw_frame) != width * height * 3:
                error("Frame read failed — ffmpeg stream ended or dropped.")
                break

            frame = np.frombuffer(
                raw_frame,
                np.uint8
            ).reshape((height, width, 3))

            frame_count += 1

            roi_frame = frame[ry1:ry2, rx1:rx2]

            # ── Bear appearance mask ──────────────────────────────────────

            blur = cv2.GaussianBlur(
                roi_frame,
                (11, 11),
                0
            )

            hsv = cv2.cvtColor(
                blur,
                cv2.COLOR_BGR2HSV
            )

            # Warm brown / tan bears
            lower_bear_warm = np.array([5, 20, 20])
            upper_bear_warm = np.array([35, 230, 230])

            bear_mask_warm = cv2.inRange(
                hsv,
                lower_bear_warm,
                upper_bear_warm
            )

            # Dark brown / almost black bears
            lower_bear_dark = np.array([0, 25, 10])
            upper_bear_dark = np.array([45, 255, 120])

            bear_mask_dark = cv2.inRange(
                hsv,
                lower_bear_dark,
                upper_bear_dark
            )

            # Pale / blonde bears
            lower_bear_light = np.array([0, 5, 120])
            upper_bear_light = np.array([45, 120, 255])

            bear_mask_light = cv2.inRange(
                hsv,
                lower_bear_light,
                upper_bear_light
            )

            bear_mask = cv2.bitwise_or(
                bear_mask_warm,
                bear_mask_dark
            )

            bear_mask = cv2.bitwise_or(
                bear_mask,
                bear_mask_light
            )

            # Remove blue/cyan water
            water_lower = np.array([70, 20, 40])
            water_upper = np.array([140, 255, 255])

            water_mask = cv2.inRange(
                hsv,
                water_lower,
                water_upper
            )

            fg_mask = cv2.bitwise_and(
                bear_mask,
                cv2.bitwise_not(water_mask)
            )

            # Remove green vegetation before contours
            green_lower = np.array([28, 35, 20])
            green_upper = np.array([95, 255, 255])

            green_mask = cv2.inRange(
                hsv,
                green_lower,
                green_upper
            )

            green_mask = cv2.dilate(
                green_mask,
                None,
                iterations=2
            )

            fg_mask = cv2.bitwise_and(
                fg_mask,
                cv2.bitwise_not(green_mask)
            )

            # Clean up mask
            fg_mask = cv2.morphologyEx(
                fg_mask,
                cv2.MORPH_OPEN,
                kernel,
                iterations=2
            )

            fg_mask = cv2.morphologyEx(
                fg_mask,
                cv2.MORPH_CLOSE,
                kernel,
                iterations=3
            )

            # Break thin water bridges between bears and land
            bridge_kernel = np.ones((7, 7), np.uint8)

            fg_mask = cv2.erode(
                fg_mask,
                bridge_kernel,
                iterations=1
            )

            fg_mask = cv2.dilate(
                fg_mask,
                np.ones((5, 5), np.uint8),
                iterations=1
            )

            # Extra horizontal cleanup for water streaks / shoreline threads
            horizontal_kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (13, 3)
            )

            horizontal_threads = cv2.morphologyEx(
                fg_mask,
                cv2.MORPH_OPEN,
                horizontal_kernel,
                iterations=1
            )

            fg_mask = cv2.subtract(
                fg_mask,
                horizontal_threads
            )

            # Remove image-border junk
            fg_mask[:, 0:20] = 0
            fg_mask[:, -20:] = 0
            fg_mask[0:20, :] = 0
            fg_mask[-20:, :] = 0

            # ── Contours → raw bears ──────────────────────────────────────

            contours, _ = cv2.findContours(
                fg_mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            bears = []

            for c in contours:
                area = cv2.contourArea(c)

                if area < MIN_BEAR_AREA:
                    continue

                x, y, w, h = cv2.boundingRect(c)

                bottom_y = y + h
                aspect = w / max(h, 1)

                if (
                    bottom_y > roi_h * 0.88
                    and w > roi_w * 0.25
                    and aspect > 2.0
                ):
                    continue

                # Reject long horizontal water / shoreline bands
                if (
                    area > roi_w * roi_h * 0.08
                    and aspect > 4.0
                ):
                    continue

                # Reject truly enormous background regions,
                # but allow close-up bears
                if (
                    area > roi_w * roi_h * 0.65
                    and aspect > 2.5
                ):
                    continue

                touches_left = x <= 2
                touches_right = x + w >= roi_w - 2
                touches_top = y <= 2
                touches_bottom = y + h >= roi_h - 2

                edge_touches = sum([
                    touches_left,
                    touches_right,
                    touches_top,
                    touches_bottom
                ])

                # Reject green vegetation / moss / land masses
                contour_mask = np.zeros(fg_mask.shape, dtype=np.uint8)
                cv2.drawContours(contour_mask, [c], -1, 255, -1)

                mean_hsv = cv2.mean(hsv, mask=contour_mask)
                mean_h = mean_hsv[0]
                mean_s = mean_hsv[1]
                mean_v = mean_hsv[2]

                if (
                     35 <= mean_h <= 85
                        and mean_s > 35
                        and (
                            aspect > 1.8
                            or y < roi_h * 0.35
                        )
                ):
                    continue

                # Allow large close-up bears, reject smaller edge junk
                if edge_touches >= 2 and area < roi_w * roi_h * 0.12:
                    continue

                if aspect > 5.5:
                    continue

                if aspect < 0.25:
                    continue

                density = area / max(w * h, 1)

                if density < 0.12:
                    continue

                M = cv2.moments(c)

                if M["m00"] == 0:
                    continue

                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]

                norm_x = cx / roi_w
                norm_y = cy / roi_h

                norm_area = min(
                    1.0,
                    area / ((roi_w * roi_h) * 0.25)
                )

                bears.append({
                    "x": round(norm_x, 4),
                    "y": round(norm_y, 4),
                    "area": round(norm_area, 4)
                })

            bears = sorted(
                bears,
                key=lambda b: b["area"],
                reverse=True
            )

            bears = bears[:MAX_BLOBS]

            if len(bears) == 0: 
                tracks.clear()

            print(
                f"Contours={len(contours)} Accepted={len(bears)}",
                flush=True
            )

            tracked_bears = update_tracks(bears)

            payload = {
                "bears": tracked_bears
            }

            # ── Debug window ──────────────────────────────────────────────

            if args.debug:
                debug_frame = roi_frame.copy()

                for bear in tracked_bears:
                    bx = int(bear["x"] * roi_w)
                    by = int(bear["y"] * roi_h)

                    radius = int(20 + bear["area"] * 120)

                    color = (0, 255, 100)

                    if bear["state"] == "mass":
                        color = (255, 120, 40)

                    cv2.circle(
                        debug_frame,
                        (bx, by),
                        radius,
                        color,
                        2
                    )

                    cv2.circle(
                        debug_frame,
                        (bx, by),
                        5,
                        (0, 255, 255),
                        -1
                    )

                    label = (
                        f"ID:{bear['id']} "
                        f"{bear['state']} "
                        f"S:{bear['speed']:.3f} "
                        f"A:{bear['area']:.2f}"
                    )

                    cv2.putText(
                        debug_frame,
                        label,
                        (bx + 12, by - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        1
                    )

                scene_label = f"{len(tracked_bears)} entities"

                cv2.putText(
                    debug_frame,
                    scene_label,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 100),
                    2
                )

                cv2.imshow(
                    "Bear Detector — ROI (press Q to quit)",
                    debug_frame
                )

                cv2.imshow(
                    "Foreground Mask",
                    fg_mask
                )

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    log("Debug window closed.")
                    proc.kill()
                    proc.wait()
                    cv2.destroyAllWindows()
                    sys.exit(0)

            # ── Emit JSON ─────────────────────────────────────────────────

            now = time.time()

            if frame_count >= WARMUP_FRAMES and (now - last_emit) >= EMIT_INTERVAL:
                print(json.dumps(payload), flush=True)
                last_emit = now

        proc.kill()
        proc.wait()

        if args.debug:
            cv2.destroyAllWindows()

        log("Restarting in 5s...")
        time.sleep(5)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log("Stopped.")
        sys.exit(0)