#!/bin/bash
# stream.sh — Bear motion detector

YOUTUBE_URL="https://www.youtube.com/watch?v=4qSRIIaOnLI"
BLACKFRAME_THRESH=10
BLACKFRAME_PCT=32
FRAMESTEP=2

# ── Pre-flight checks ──────────────────────────────────────────
echo "🐻 Bear motion stream starting..." >&2

if ! command -v yt-dlp &>/dev/null; then
  echo "❌ yt-dlp not found. Install: pip install yt-dlp" >&2
  exit 1
fi

if ! command -v ffmpeg &>/dev/null; then
  echo "❌ ffmpeg not found." >&2
  exit 1
fi

echo "✅ yt-dlp:  $(yt-dlp --version 2>&1)" >&2
echo "✅ ffmpeg:  $(ffmpeg -version 2>&1 | head -1)" >&2

# ── Main loop ──────────────────────────────────────────────────
while true; do
  echo "📡 Resolving stream URL..." >&2

  STREAM_URL=$(yt-dlp -f "best[height<=720]" -g --no-warnings "$YOUTUBE_URL" 2>/dev/null)

  if [[ -z "$STREAM_URL" ]]; then
    echo "⚠️  yt-dlp could not resolve URL. Retrying in 15s..." >&2
    sleep 15
    continue
  fi

  echo "🎬 URL resolved. Starting motion detection..." >&2

  ffmpeg \
    -hide_banner \
    -loglevel info \
    -multiple_requests 0 \
    -i "$STREAM_URL" \
    -vf "fps=10,scale=320:-1,format=gray,tblend=all_mode=difference,boxblur=4:1,eq=contrast=2:brightness=0.05,blackframe=5:32" \
    -f null - \
    2>&1 | \
  while IFS= read -r line; do

    # Motion
    if [[ "$line" =~ pblack:([0-9]+) ]]; then
      pblack="${BASH_REMATCH[1]}"
      echo "Y:$((100 - pblack))"
      continue
    fi

    # Surface real errors
    if [[ "$line" =~ (Error|Invalid|Failed|Could\ not|moov\ atom|Connection\ refused) ]]; then
      echo "⚠️  ffmpeg: $line" >&2
    fi

  done

  echo "⚠️  Pipeline exited. Restarting in 5s..." >&2
  sleep 5
done