#!/usr/bin/env python3
"""Bir videonun kurgu DNA'sını çıkarır.

Kullanım:
  python3 analiz.py video.mp4 --out klasor/ [--esik 0.3] [--kare-sayisi 16]

Çıktılar (klasor/):
  ozet.json   -> süre, çözünürlük, kesim zamanları, çekim süreleri, ilk 3 sn kesim sayısı, ses seviyesi
  kontak.jpg  -> videodan eşit aralıklı karelerin zaman damgalı ızgarası (Read ile bakılabilir)
  kesimler/   -> her kesimden hemen sonraki kare (en fazla 40)
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path])
    if r.returncode != 0:
        sys.exit(f"ffprobe hatası: {r.stderr}")
    return json.loads(r.stdout)


def detect_cuts(path, threshold):
    # select'in scene skoru 0-1 aralığında; eşiği geçen kareler kesim sayılır
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vf",
             f"scale=320:-2,select='gt(scene,{threshold})',metadata=print", "-an", "-f", "null", "-"])
    times = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    # birbirine 0.15 sn'den yakın tespitleri birleştir
    out = []
    for t in times:
        if not out or t - out[-1] > 0.15:
            out.append(round(t, 3))
    return out


def loudness(path):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"])
    m = re.findall(r"I:\s*(-?[0-9.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


def contact_sheet(path, duration, out_jpg, n):
    cols = 4
    rows = (n + cols - 1) // cols
    interval = max(duration / n, 0.04)
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    vf = (f"fps=1/{interval:.4f},scale=270:-2,"
          f"drawtext=fontfile={font}:text='%{{pts\\:hms}}':x=6:y=6:fontsize=20:"
          f"fontcolor=yellow:box=1:boxcolor=black@0.6,"
          f"tile={cols}x{rows}:padding=4:color=gray")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", path, "-vf", vf,
         "-frames:v", "1", "-q:v", "3", out_jpg])


def cut_frames(path, cuts, folder, limit=40):
    os.makedirs(folder, exist_ok=True)
    for i, t in enumerate(cuts[:limit]):
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t + 0.05:.3f}",
             "-i", path, "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4",
             os.path.join(folder, f"{i:02d}_{t:07.2f}s.jpg")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="analiz")
    ap.add_argument("--esik", type=float, default=0.25, help="sahne değişim eşiği 0-1 (düşük = daha hassas)")
    ap.add_argument("--kare-sayisi", type=int, default=16)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    info = probe(a.video)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    duration = float(info["format"]["duration"])
    w, h = (int(v["width"]), int(v["height"])) if v else (0, 0)
    # dönme meta verisi (telefon videoları)
    rot = 0
    for sd in (v or {}).get("side_data_list", []):
        if "rotation" in sd:
            rot = abs(int(sd["rotation"]))
    if rot in (90, 270):
        w, h = h, w
    num, den = (v or {}).get("avg_frame_rate", "0/1").split("/")
    fps = round(float(num) / float(den), 2) if float(den) else None

    cuts = detect_cuts(a.video, a.esik)
    bounds = [0.0] + cuts + [duration]
    shots = [round(bounds[i + 1] - bounds[i], 3) for i in range(len(bounds) - 1)]

    ozet = {
        "dosya": os.path.basename(a.video),
        "sure_sn": round(duration, 2),
        "cozunurluk": f"{w}x{h}",
        "dikey_mi": h > w,
        "fps": fps,
        "ses_var_mi": has_audio,
        "loudness_lufs": loudness(a.video) if has_audio else None,
        "kesim_sayisi": len(cuts),
        "kesim_zamanlari": cuts,
        "cekim_sureleri": shots,
        "ortalama_cekim_sn": round(statistics.mean(shots), 2) if shots else None,
        "medyan_cekim_sn": round(statistics.median(shots), 2) if shots else None,
        "en_uzun_cekim_sn": max(shots) if shots else None,
        "ilk_3sn_kesim": sum(1 for c in cuts if c <= 3.0),
        "dakikada_kesim": round(len(cuts) / duration * 60, 1) if duration else None,
        "not": "Kesim tespiti sahne değişimine dayanır; hızlandırılmış/aynı kadraj kesimleri kaçabilir. "
               "Kontak sayfasıyla doğrula.",
    }
    with open(os.path.join(a.out, "ozet.json"), "w", encoding="utf-8") as f:
        json.dump(ozet, f, ensure_ascii=False, indent=2)

    contact_sheet(a.video, duration, os.path.join(a.out, "kontak.jpg"), a.kare_sayisi)
    cut_frames(a.video, cuts, os.path.join(a.out, "kesimler"))

    kisa = {k: ozet[k] for k in ozet if k not in ("kesim_zamanlari", "cekim_sureleri", "not")}
    print(json.dumps(kisa, ensure_ascii=False, indent=2))
    print(f"\nKontak sayfası: {os.path.join(a.out, 'kontak.jpg')}")


if __name__ == "__main__":
    main()
