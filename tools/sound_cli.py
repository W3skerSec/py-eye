#!/usr/bin/env python3
"""Generate small robot emotion sounds for py-eye using ffmpeg."""

import argparse
import math
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "sound" / "generated"
SOUNDS = {
    "blink": [(880, 0.035), (0, 0.025), (1320, 0.035)],
    "curious": [(520, 0.08), (690, 0.08), (910, 0.10)],
    "happy": [(740, 0.07), (980, 0.07), (1220, 0.12)],
    "giggle": [(880, 0.04), (0, 0.025), (940, 0.04), (0, 0.025), (1020, 0.05)],
    "surprised": [(420, 0.05), (900, 0.08), (1500, 0.12)],
    "angry": [(170, 0.08), (145, 0.08), (210, 0.10)],
    "sleepy": [(330, 0.18), (260, 0.22)],
    "sleep": [(220, 0.25), (0, 0.08), (180, 0.35)],
    "love": [(660, 0.09), (880, 0.09), (660, 0.09), (1040, 0.16)],
    "confused": [(500, 0.06), (430, 0.08), (610, 0.06), (380, 0.08)],
    "dizzy": [(760, 0.04), (620, 0.04), (480, 0.04), (620, 0.04), (760, 0.05)],
    "bored": [(240, 0.18), (0, 0.05), (230, 0.18)],
    "talking": [(620, 0.04), (720, 0.04), (540, 0.04), (810, 0.04)],
}


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def make_filter(parts, volume):
    labels = []
    filters = []
    for idx, (freq, dur) in enumerate(parts):
        label = f"a{idx}"
        if freq <= 0:
            filters.append(f"aevalsrc=0:d={dur}[{label}]")
        else:
            filters.append(
                f"sine=frequency={freq}:duration={dur}:sample_rate=44100,"
                f"volume={volume},afade=t=in:st=0:d=0.008,"
                f"afade=t=out:st={max(0.0, dur - 0.015):.3f}:d=0.015[{label}]"
            )
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]")
    return ";".join(filters)


def generate(name, output, volume):
    if name not in SOUNDS:
        raise SystemExit(f"unknown sound: {name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not ffmpeg_available():
        raise SystemExit("ffmpeg not found; install ffmpeg or use Termux package ffmpeg")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-filter_complex", make_filter(SOUNDS[name], volume),
        "-map", "[out]", str(output),
    ]
    subprocess.run(cmd, check=True)
    print(output)


def generate_all(volume):
    for name in sorted(SOUNDS):
        generate(name, OUT_DIR / f"{name}.wav", volume)


def main():
    parser = argparse.ArgumentParser(description="Generate py-eye robot emotion sounds")
    sub = parser.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("generate")
    one.add_argument("name", choices=sorted(SOUNDS))
    one.add_argument("--output", type=Path)
    one.add_argument("--volume", type=float, default=0.18)
    all_cmd = sub.add_parser("generate-all")
    all_cmd.add_argument("--volume", type=float, default=0.18)
    args = parser.parse_args()
    if args.cmd == "generate":
        generate(args.name, args.output or OUT_DIR / f"{args.name}.wav", args.volume)
    elif args.cmd == "generate-all":
        generate_all(args.volume)


if __name__ == "__main__":
    main()
