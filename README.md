# stream-check

> 🚦 Probe, filter, and clean IPTV M3U playlists by resolution & frame rate.

**stream-check** is a fast-ish*, concurrent CLI tool that uses [`ffprobe`](https://ffmpeg.org/ffprobe.html) to analyze IPTV streams.
It exports stream metadata to CSV and produces a curated M3U containing only the channels that meet your quality thresholds.

* ✅ Cleans bloated playlists down to what you actually want
* ✅ Adds `[1080P 50FPS]` style tags into channel names
* ✅ Works on macOS, Linux, and anywhere with Python 3 + ffprobe

*10 workers can analyze 15,000 streams in ~45 minutes.

## Features

- Parse `.m3u` playlists (`#EXTINF` + URL pairs)
- Probe each stream with **ffprobe**
- Export stream metadata (`width`, `height`, `fps`, `codec`, status) to CSV
- Keep only streams meeting your thresholds (default: **≥720p & ≥50fps**)
- Rename channels in output M3U with `[Resolution FPS]` tags
- Concurrency (`--workers`) for speed
- Incremental writing → you can see results in CSV/M3U while it runs
- Live console logging:

```bash
[OK] ✅ Channel A -> 1920x1080 @ 50.00 fps (h264)
[OK] ❌ Channel B -> 1920x1080 @ 30.00 fps (h264)
```

## Installation

### Requirements
- **Python 3.8+**
- **ffprobe** (comes with [FFmpeg](https://ffmpeg.org/))

### Install ffmpeg:
```bash
# macOS
brew install ffmpeg
```
```bash
# Debian/Ubuntu
sudo apt install ffmpeg
```
### Clone repo
```bash
git clone https://github.com/pipetogrep/stream-check.git
cd stream-check
python3 stream-check.py --help
```

### Check dem streams
```bash
python3 stream-check.py input.m3u \
  --csv results.csv \
  --out-m3u filtered.m3u \
  --workers 10 \
  --timeout 10 \
  --min-width 1280 \
  --min-height 720 \
  --min-fps 50 \
  --log-every 25
```

### Options
```bash
--csv : Output CSV path (default: streams_quality.csv)
--out-m3u : Output filtered playlist path (default: filtered_quality.m3u)
--ffprobe : Path to ffprobe binary (if not in $PATH)
--workers : Number of concurrent probes
--timeout : Kill probe if it takes longer than N seconds
--min-width/--min-height : Minimum resolution
--min-fps : Minimum framerate
--log-every : Progress interval
--no-line-log : Disable per-channel logs
```

### Example Output
```bash
Found 1200 channels in playlist.m3u
Probing with 10 workers, timeout 10s each...
[OK] ✅ Channel A -> 1920x1080 @ 50.00 fps (h264)
[OK] ❌ Channel B -> 1920x1080 @ 30.00 fps (h264)
Progress: 25/1200 probed | kept 12
...
Done. Probed 1200 streams.
Wrote CSV: /path/to/results.csv
Kept 500 streams meeting 1280x720+ and 50.0 FPS.
Wrote filtered M3U: /path/to/highquality.m3u
```
