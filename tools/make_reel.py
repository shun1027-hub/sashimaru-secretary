#!/usr/bin/env python3
"""編集プラン（JSON）から、テロップ入りの縦型リール（1080x1920）を書き出す。

使い方:
    python3 tools/make_reel.py plan.json out.mp4

plan.json の例:
{
  "cuts": [
    {"src": "clips/a.mov", "start": 1.2, "dur": 0.9, "text": "のれんをくぐると", "color": "pink"},
    {"src": "clips/b.mov", "start": 0.0, "dur": 1.0, "text": "", "color": "pink"}
  ],
  "hook": {"label": "期間限定", "lines": ["春にやりたい", "親子で楽しむ和体験"], "area": "岐阜県"},
  "end": {"name": "長良川清流ホテル", "area": "岐阜県岐阜市"}
}
- hook は最初のカットに重ねる。end は最後のカットに重ねる。
- 音声は入れない（音楽は Instagram で付ける）。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"
FONT = "Rounded Mplus 1c ExtraBold"
W, H, FPS = 1080, 1920, 30

# ASS の色は &HAABBGGRR
COLORS = {
    "pink": "&H00B469FF",
    "blue": "&H00E0902A",
    "orange": "&H003C8CFF",
    "green": "&H0060B040",
}

ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Telop,{FONT},78,&H00FFFFFF,&H00FFFFFF,&H00B469FF,&H00000000,0,0,0,0,100,100,2,0,1,7,0,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

POP = r"\fscx70\fscy70\t(0,110,\fscx108\fscy108)\t(110,200,\fscx100\fscy100)"


def ts(sec):
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def telop(start, end, text, color, x, y, size=96):
    """縁取り＋ぼかしの光彩を下に敷いた、ポップするテロップ（2レイヤー）。改行は \\n。"""
    c = COLORS.get(color, color)
    # 横幅からはみ出さないよう、一番長い行に合わせて文字を小さくする
    longest = max(len(line) for line in text.split("\n"))
    size = min(size, int((W - 120) / max(longest, 1)))
    text = text.replace("\n", "\\N")
    glow = f"{{\\pos({x},{y})\\fs{size}{POP}\\bord16\\blur10\\3c{c}\\1a&HFF&}}{text}"
    main = f"{{\\pos({x},{y})\\fs{size}{POP}\\bord6\\3c{c}}}{text}"
    return [
        f"Dialogue: 0,{ts(start)},{ts(end)},Telop,,0,0,0,,{glow}",
        f"Dialogue: 1,{ts(start)},{ts(end)},Telop,,0,0,0,,{main}",
    ]


def build_ass(plan):
    cuts = plan["cuts"]
    events, t = [], 0.0
    starts = []
    for cut in cuts:
        starts.append(t)
        t += cut["dur"]
    total = t

    for i, cut in enumerate(cuts):
        if i == 0 and plan.get("hook"):
            continue
        if i == len(cuts) - 1 and plan.get("end"):
            continue
        if cut.get("text"):
            events += telop(starts[i], starts[i] + cut["dur"], cut["text"], cut.get("color", "pink"), W // 2, int(H * 0.40))

    hook = plan.get("hook")
    if hook:
        end = starts[0] + cuts[0]["dur"]
        y = int(H * 0.33)
        if hook.get("label"):
            events += telop(0, end, f"✿{hook['label']}✿", "pink", W // 2, y, 84)
            y += 135
        for line in hook.get("lines", []):
            events += telop(0, end, line, "pink", W // 2, y, 108)
            y += 130
        if hook.get("area"):
            events += telop(0, end, hook["area"], "pink", W // 2, y + 60, 124)

    end_card = plan.get("end")
    if end_card:
        s = starts[-1]
        events += telop(s, total, f"『{end_card['name']}』", "blue", W // 2, int(H * 0.36), 100)
        events += telop(s, total, f"{end_card['area']}", "blue", W // 2, int(H * 0.43), 84)

    return ASS_HEADER + "\n".join(events) + "\n"


def render(plan, out):
    cuts = plan["cuts"]
    # 各カットの長さをフレーム単位にそろえる（テロップと映像の切り替わりがずれないように）
    frames = [max(1, round(cut["dur"] * FPS)) for cut in cuts]
    for cut, n in zip(cuts, frames):
        cut["dur"] = n / FPS
    with tempfile.TemporaryDirectory() as tmp:
        ass = Path(tmp) / "telop.ass"
        ass.write_text(build_ass(plan), encoding="utf-8")

        args = ["ffmpeg", "-v", "error", "-y"]
        for cut in cuts:
            args += ["-ss", str(cut["start"]), "-t", str(cut["dur"] + 0.5), "-i", str(cut["src"])]

        parts = []
        for i in range(len(cuts)):
            parts.append(
                f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"fps={FPS},tpad=stop_mode=clone:stop_duration=1,trim=end_frame={frames[i]},"
                f"setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{i}]"
            )
        concat = "".join(f"[v{i}]" for i in range(len(cuts)))
        # 色補正は控えめ（本人から「色が濃すぎる」と指摘あり）。plan の "grade" で上書きできる
        grade = plan.get("grade", "eq=saturation=1.03:brightness=0.01:contrast=1.01")
        sub = f"subtitles={ass}:fontsdir={FONTS_DIR}"
        graph = ";".join(parts) + f";{concat}concat=n={len(cuts)}:v=1:a=0,{grade},{sub}[out]"

        args += ["-filter_complex", graph, "-map", "[out]", "-an",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-movflags", "+faststart", str(out)]
        subprocess.run(args, check=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    plan_path = Path(sys.argv[1])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for cut in plan["cuts"]:
        src = Path(cut["src"])
        cut["src"] = src if src.is_absolute() else plan_path.parent / src
    # 似たカット（同じ素材の近い場面）が続くと飽きるので、続いていたら知らせる
    for prev, cur in zip(plan["cuts"], plan["cuts"][1:]):
        if prev["src"] == cur["src"] and abs(prev["start"] - cur["start"]) < 5:
            print(f"注意: 似たカットが続いています: {cur['src'].name} {prev['start']}秒と{cur['start']}秒", file=sys.stderr)
    render(plan, Path(sys.argv[2]))
