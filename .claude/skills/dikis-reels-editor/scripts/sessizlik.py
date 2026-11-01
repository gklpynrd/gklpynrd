#!/usr/bin/env python3
"""Ham çekimde ölü bölümleri bulur: sessiz kısımlar + görüntünün neredeyse donduğu kısımlar.

Kullanım:
  python3 sessizlik.py ham.mp4 [--db -35] [--min-sessiz 0.8] [--min-donuk 2.0]

Çıktı: JSON -> sessiz aralıklar, donuk aralıklar, ve "tut" önerisi (atılacak yerler dışındaki aralıklar).
Not: Dikişte makine sesi sürekli olabilir; o durumda donuk-görüntü tespiti daha anlamlıdır.
"""
import argparse
import json
import re
import subprocess


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(r.stdout.strip())


def has_audio(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path])
    return bool(r.stdout.strip())


def pairs(starts, ends, total):
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else total
        out.append([round(s, 2), round(e, 2)])
    return out


def silences(path, db, mind, total):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
             f"silencedetect=noise={db}dB:d={mind}", "-vn", "-f", "null", "-"])
    s = [float(x) for x in re.findall(r"silence_start:\s*(-?[0-9.]+)", r.stderr)]
    e = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", r.stderr)]
    return pairs([max(0, x) for x in s], e, total)


def frozen(path, mind, total):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vf",
             f"scale=320:-2,freezedetect=n=-45dB:d={mind}", "-an", "-f", "null", "-"])
    s = [float(x) for x in re.findall(r"freeze_start:\s*([0-9.]+)", r.stderr)]
    e = [float(x) for x in re.findall(r"freeze_end:\s*([0-9.]+)", r.stderr)]
    return pairs(s, e, total)


def merge(ranges):
    ranges = sorted(ranges)
    out = []
    for s, e in ranges:
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--db", type=float, default=-35)
    ap.add_argument("--min-sessiz", type=float, default=0.8)
    ap.add_argument("--min-donuk", type=float, default=2.0)
    a = ap.parse_args()

    total = duration(a.video)
    sil = silences(a.video, a.db, a.min_sessiz, total) if has_audio(a.video) else []
    frz = frozen(a.video, a.min_donuk, total)
    # sadece hem sessiz hem donuk değil; ikisinden biri yeterince uzunsa at
    drop = merge(sil + frz)
    keep, cur = [], 0.0
    for s, e in drop:
        if s - cur > 0.3:
            keep.append([round(cur, 2), round(s, 2)])
        cur = max(cur, e)
    if total - cur > 0.3:
        keep.append([round(cur, 2), round(total, 2)])

    print(json.dumps({
        "sure_sn": round(total, 2),
        "sessiz_araliklar": sil,
        "donuk_araliklar": frz,
        "tut_onerisi": keep,
        "tut_toplam_sn": round(sum(e - s for s, e in keep), 2),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
