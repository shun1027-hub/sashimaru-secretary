#!/usr/bin/env python3
"""編集プラン（JSON）のカットを、CapCut に読み込む用の短いクリップに切り出す。

使い方:
    python3 tools/cut_clips.py plan.json outdir

- カットごとに `01_素材名.mp4` のような番号付きクリップを書き出す。CapCut に番号順で読み込めば並びがそろう。
- 前後に少し余白（既定0.4秒）を付けるので、CapCut で微調整できる。
- 色補正なし、元の音声つき。画質は元素材に近い設定（4K素材は縦1920に縮める）。
- 同じフォルダに、全カットを1枚にまとめた絵コンテ画像（storyboard.jpg）も作る。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "MPLUSRounded1c-ExtraBold.ttf"
HANDLE = 0.4


def esc(text):
    """ffmpeg drawtext 用のエスケープ。"""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def cut(src, start, dur, out):
    s = max(0.0, start - HANDLE)
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-t", f"{dur + HANDLE * 2:.3f}", "-i", str(src),
        "-vf", "scale=-2:'min(1920,ih)'",  # 4K素材は縦1920に縮める（スマホに送りやすくするため）
        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
    ], check=True)


def thumb(src, at, label, text, out):
    lines = [label] + [line for line in text.split("\n") if line]
    draws = []
    for i, line in enumerate(lines):
        size = 26 if i == 0 else 22
        y = 10 + i * 30
        draws.append(
            f"drawtext=fontfile={FONT}:text='{esc(line)}':x=(w-text_w)/2:y=h-{20 + (len(lines) - i) * 30}:"
            f"fontsize={size}:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=6"
        )
    vf = "scale=300:-2," + ",".join(draws)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", str(src),
                    "-frames:v", "1", "-vf", vf, str(out)], check=True)


def main(plan_path, outdir):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    outdir.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for i, c in enumerate(plan["cuts"], 1):
        src = Path(c["src"])
        src = src if src.is_absolute() else plan_path.parent / src
        name = f"{i:02d}_{src.stem}.mp4"
        cut(src, c["start"], c["dur"], outdir / name)
        t = outdir / f".thumb_{i:02d}.jpg"
        thumb(src, c["start"] + c["dur"] / 2, f"{i:02d}  {c['dur']:.1f}秒", c.get("text", ""), t)
        thumbs.append(t)
        print(name)

    # 絵コンテ: サムネを4列で並べる（全サムネが同じ大きさなので、列×幅・行×高さで配置）
    cols = 4
    inputs = sum((["-i", str(t)] for t in thumbs), [])
    layout = "|".join(
        f"{'+'.join(['w0'] * (k % cols)) or '0'}_{'+'.join(['h0'] * (k // cols)) or '0'}" for k in range(len(thumbs))
    )
    graph = "".join(f"[{k}:v]" for k in range(len(thumbs))) + f"xstack=inputs={len(thumbs)}:layout={layout}:fill=black"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph,
                    "-frames:v", "1", str(outdir / "storyboard.jpg")], check=True)
    for t in thumbs:
        t.unlink()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
