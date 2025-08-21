#!/usr/bin/env python3
import argparse
import csv
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path
from typing import List, Tuple, Optional

def parse_args():
    ap = argparse.ArgumentParser(
        description="Probe M3U streams (resolution & FPS), export CSV, and emit filtered/renamed M3U."
    )
    ap.add_argument("m3u", help="Input M3U file (e.g., playlist.m3u)")
    ap.add_argument("--csv", default="playlist_quality.csv", help="Output CSV path")
    ap.add_argument("--out-m3u", default="filtered_quality.m3u", help="Output filtered M3U path")
    ap.add_argument("--ffprobe", default="ffprobe",
                    help="Path to ffprobe (e.g. /opt/homebrew/bin/ffprobe on Apple Silicon)")
    ap.add_argument("--workers", type=int, default=10, help="Concurrent probes (default: 10)")
    ap.add_argument("--timeout", type=int, default=10, help="ffprobe timeout seconds (default: 10)")
    ap.add_argument("--min-width", type=int, default=1280, help="Min width to keep (default: 1280 ~ 720p)")
    ap.add_argument("--min-height", type=int, default=720, help="Min height to keep (default: 720)")
    ap.add_argument("--min-fps", type=float, default=50.0, help="Min FPS to keep (default: 50.0)")
    ap.add_argument("--log-every", dest="log_every", type=int, default=50,
                    help="Print progress every N probes (default: 50)")
    ap.add_argument("--no-line-log", action="store_true",
                    help="Disable per-channel line-by-line logging to console")
    return ap.parse_args()

def read_m3u_blocks(m3u_path: str) -> List[Tuple[str, str]]:
    """Return list of (EXTINF line, URL line) pairs."""
    pairs = []
    with open(m3u_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\r\n")
        if line.startswith("#EXTINF"):
            url = lines[i+1].strip() if i + 1 < len(lines) else ""
            pairs.append((line, url))
            i += 2
        else:
            i += 1
    return pairs

def parse_name_from_extinf(extinf: str) -> str:
    # Channel name is after the last comma
    return extinf.rsplit(",", 1)[-1].strip()

def run_ffprobe(ffprobe: str, url: str, timeout: int):
    """
    Return: (width, height, fps_float, codec_name, exit_code, error_string_or_None)
    exit_code 0 -> OK, non-zero -> FAIL. On timeout returns exit_code 124.
    """
    cmd = [
        ffprobe,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate",
        "-of", "default=nw=1",
        url
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        exit_code = proc.returncode
        if exit_code != 0:
            return None, None, None, None, exit_code, f"ffprobe_exit_{exit_code}: {proc.stderr.strip()}"
        width = height = None
        codec = None
        fps_val: Optional[float] = None
        for line in proc.stdout.splitlines():
            if line.startswith("width="):
                try: width = int(line.split("=", 1)[1])
                except: pass
            elif line.startswith("height="):
                try: height = int(line.split("=", 1)[1])
                except: pass
            elif line.startswith("codec_name="):
                codec = line.split("=", 1)[1].strip()
            elif line.startswith("avg_frame_rate="):
                fr = line.split("=", 1)[1].strip()
                try:
                    if fr and fr != "0/0":
                        fps_val = float(Fraction(fr))
                except Exception:
                    fps_val = None
        if width is None and height is None and fps_val is None and codec is None:
            return None, None, None, None, 1, "no_video_stream"
        return width, height, fps_val, codec, 0, None
    except subprocess.TimeoutExpired:
        return None, None, None, None, 124, "timeout"
    except FileNotFoundError:
        return None, None, None, None, 127, "ffprobe_not_found"
    except Exception as e:
        return None, None, None, None, 1, f"exception:{type(e).__name__}:{e}"

def classify_resolution(width: Optional[int], height: Optional[int]) -> Optional[str]:
    if width is None or height is None:
        return None
    h = height if height >= width else width
    if h >= 2160: return "4K"
    if h >= 1440: return "1440P"
    if h >= 1080: return "1080P"
    if h >= 720:  return "720P"
    return "SD"

def main():
    args = parse_args()
    pairs = read_m3u_blocks(args.m3u)
    total = len(pairs)
    if total == 0:
        print("No channels found in M3U.", file=sys.stderr)
        sys.exit(2)

    print(f"Found {total} channels in {args.m3u}")
    print(f"Probing with {args.workers} workers, timeout {args.timeout}s each...")
    sys.stdout.flush()

    # Prepare outputs
    csv_path = Path(args.csv)
    filtered_m3u_path = Path(args.out_m3u)
    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=["name", "url", "width", "height", "fps", "codec", "status"])
    writer.writeheader()

    keep_blocks: List[Tuple[str, str]] = []
    completed = 0
    kept = 0

    def work(item):
        extinf, url = item
        name = parse_name_from_extinf(extinf)
        width, height, fps, codec, exit_code, err = run_ffprobe(args.ffprobe, url, args.timeout)
        return (extinf, url, name, width, height, fps, codec, exit_code, err)

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(work, p) for p in pairs]
            for fut in as_completed(futures):
                extinf, url, name, width, height, fps, codec, exit_code, err = fut.result()

                # Decide keep/discard
                keep = (
                    err is None and
                    width is not None and height is not None and fps is not None and
                    (width >= args.min_width or height >= args.min_height) and
                    fps >= args.min_fps
                )
                if keep:
                    res_name = classify_resolution(width, height) or "UNK"
                    fps_disp = f"{int(round(fps))}FPS"
                    new_extinf = extinf.rsplit(",", 1)[0] + f", {name} [{res_name} {fps_disp}]"
                    keep_blocks.append((new_extinf, url))
                    kept += 1

                # CSV row
                writer.writerow({
                    "name": name,
                    "url": url,
                    "width": "" if width is None else width,
                    "height": "" if height is None else height,
                    "fps": "" if fps is None else f"{fps:.2f}",
                    "codec": "" if codec is None else codec,
                    "status": "ok" if err is None else err
                })
                csv_file.flush()

                # Per-channel console line
                if not args.no_line_log:
                    w = "" if width is None else str(width)
                    h = "" if height is None else str(height)
                    f = "" if fps is None else f"{fps:.2f}"
                    c = "" if codec is None else codec
                    code_label = "OK" if exit_code == 0 else "FAIL"
                    emoji = "✅" if keep else "❌"
                    print(f"[{code_label}] {emoji} {name} -> {w}x{h} @ {f} fps ({c})", flush=True)

                completed += 1
                if args.log_every and completed % args.log_every == 0:
                    print(f"Progress: {completed}/{total} probed | kept {kept}", flush=True)

    finally:
        csv_file.close()

    # Write filtered M3U
    with open(filtered_m3u_path, "w", encoding="utf-8") as fm3u:
        fm3u.write("#EXTM3U\n")
        for extinf, url in keep_blocks:
            fm3u.write(extinf + "\n")
            fm3u.write(url + "\n")

    print(f"Done. Probed {completed} streams.")
    print(f"Wrote CSV: {csv_path.resolve()}")
    print(f"Kept {kept} streams meeting {args.min_width}x{args.min_height}+ and {args.min_fps} FPS.")
    print(f"Wrote filtered M3U: {filtered_m3u_path.resolve()}")

if __name__ == "__main__":
    main()
