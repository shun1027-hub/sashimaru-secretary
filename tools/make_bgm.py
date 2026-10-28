#!/usr/bin/env python3
"""リール用のオリジナルBGM（著作権フリー）を作る。明るいウクレレ風ポップ。

使い方:
    python3 tools/make_bgm.py out.wav 23.0 [--bpm 112] [--seed 1]

- 長さ（秒）ぴったりで書き出し、最後の1.5秒はフェードアウトする。
- --seed を変えるとメロディが変わる。
"""
import argparse
import wave

import numpy as np

SR = 44100

# 1小節ずつのコード（ルート音のMIDI番号と構成音）。I - V - vi - IV（ハ長調）
PROGRESSION = [
    (48, [60, 64, 67]),  # C
    (43, [59, 62, 67]),  # G
    (45, [57, 60, 64]),  # Am
    (41, [57, 60, 65]),  # F
]
PENTATONIC = [72, 74, 76, 79, 81, 84]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def envelope(n, attack, decay):
    t = np.arange(n) / SR
    env = np.exp(-t / decay)
    a = max(1, int(attack * SR))
    env[:a] *= np.linspace(0, 1, a)
    r = min(n, int(0.015 * SR))  # 音の終わりをなめらかに（プチッというノイズを防ぐ）
    env[n - r:] *= np.linspace(1, 0, r)
    return env


def soft_noise(rng, n):
    """シャカシャカ音用のノイズ。高すぎる成分を少し丸める。"""
    noise = np.diff(rng.standard_normal(n + 1))
    return np.convolve(noise, np.ones(4) / 4, mode="same")


def pluck(midi, length, decay=0.35, bright=1.0):
    """ウクレレ風のはじく音（倍音を足して減衰させる）。"""
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(midi)
    tone = sum((bright / k ** 1.6) * np.sin(2 * np.pi * f * k * t) for k in range(1, 7))
    return tone * envelope(n, 0.004, decay)


def bell(midi, length):
    """グロッケン風のメロディ音。"""
    n = int(length * SR)
    t = np.arange(n) / SR
    f = hz(midi)
    tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) + 0.15 * np.sin(2 * np.pi * f * 5.4 * t)
    return tone * envelope(n, 0.002, 0.45)


def bass(midi, length):
    n = int(length * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * hz(midi) * t) * envelope(n, 0.01, 0.5)


def kick(length=0.3):
    n = int(length * SR)
    t = np.arange(n) / SR
    freq = 110 * np.exp(-t * 18) + 45
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * envelope(n, 0.001, 0.12)


def shaker(rng, length=0.08):
    n = int(length * SR)
    return soft_noise(rng, n) * envelope(n, 0.003, 0.025)


def clap(rng, length=0.2):
    n = int(length * SR)
    return soft_noise(rng, n) * envelope(n, 0.002, 0.06)


def add(buf, sound, at, gain):
    i = int(at * SR)
    if i >= len(buf):
        return
    end = min(len(buf), i + len(sound))
    buf[i:end] += gain * sound[: end - i]


def make(duration, bpm, seed):
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    bar = beat * 4
    total = int((duration + 2) * SR)
    mix = np.zeros(total)

    # メロディ: 2小節のモチーフを作って繰り返す（少しずつ変える）
    motif = [(step, rng.choice(PENTATONIC)) for step in range(0, 16) if rng.random() < 0.45]

    n_bars = int(np.ceil(duration / bar)) + 1
    for b in range(n_bars):
        start = b * bar
        root, chord = PROGRESSION[b % len(PROGRESSION)]
        # ウクレレのストローク（8分音符: ダウン・ダウンアップ・アップダウンアップ）
        for step, (on, strength) in enumerate([(1, 1.0), (0, 0), (1, 0.8), (1, 0.6), (0, 0), (1, 0.6), (1, 0.8), (1, 0.6)]):
            if not on:
                continue
            t0 = start + step * beat / 2
            for k, note in enumerate(chord + [chord[0] + 12]):
                add(mix, pluck(note, beat * 1.5), t0 + k * 0.008, 0.10 * strength)
        # ベース
        add(mix, bass(root, beat * 1.8), start, 0.35)
        add(mix, bass(root + 7, beat * 1.2), start + beat * 2.5, 0.25)
        # ドラム（最初の1小節はキックなしで軽く入る）
        for q in range(4):
            if b > 0 and q in (0, 2):
                add(mix, kick(), start + q * beat, 0.55)
            if b > 0 and q in (1, 3):
                add(mix, clap(rng), start + q * beat, 0.06)
        for e in range(8):
            add(mix, shaker(rng), start + e * beat / 2, 0.025 if e % 2 else 0.015)
        # メロディ（2小節目から）
        if b >= 1:
            for step, note in motif:
                if (b % 2 == 1) == (step < 8):
                    shift = 0 if b % 4 < 2 else (2 if note < 84 else 0)
                    add(mix, bell(note + shift, beat), start + (step % 8) * beat / 2, 0.09)

    out = mix[: int(duration * SR)]
    # フェードイン（少し）とフェードアウト（1.5秒）
    fade_in = int(0.05 * SR)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    fade_out = int(1.5 * SR)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)
    out = out / np.max(np.abs(out)) * 0.8
    return out


def write_wav(path, samples):
    data = (samples * 32767).astype(np.int16)
    stereo = np.column_stack([data, data]).ravel()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("duration", type=float)
    ap.add_argument("--bpm", type=float, default=112)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    write_wav(args.out, make(args.duration, args.bpm, args.seed))
