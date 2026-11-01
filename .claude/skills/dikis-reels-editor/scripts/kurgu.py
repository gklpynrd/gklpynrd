#!/usr/bin/env python3
"""JSON kurgu planından dikey (9:16) Reels/TikTok videosu render eder.

Kullanım:
  python3 kurgu.py plan.json [--keep-temp]

Plan alanları (bkz. ornek_plan.json):
  output            çıktı dosyası (plan dosyasına göre göreli olabilir)
  width/height/fps  varsayılan 1080x1920 @ 30
  font              ASS font ailesi (varsayılan "Inter"; yoksa libass DejaVu'ya düşer)
  clips[]           sırayla:
      src           kaynak video (veya .jpg/.png fotoğraf -> "duration" ile)
      start, end    kaynak içindeki saniye aralığı
      speed         1 = normal, 8 = 8x hızlı, 0.7 = yavaş çekim
      zoom          başlangıç zoom (1 = kadraja sığdır)
      zoom_to       bitiş zoom (verilirse klip boyunca yumuşak zoom/punch-in)
      crop_x/crop_y 0-1 kırpma konumu (yatay videoda makine soldaysa crop_x 0.3 gibi)
      mute          true ise orijinal ses atılır. speed >= 2.5 iken varsayılan true
      volume        orijinal ses seviyesi (1 = aynı)
      text          bu klip süresince gösterilecek ekran yazısı
      text_style    hook | label | center | caption | box   (varsayılan: ilk klipte hook, sonra label)
  captions[]        zaman çizelgesine göre ek yazılar: {start, end, text, style}
  music             {src, volume (0-1), start (müzik içinde başlangıç sn), duck (bool), fade_out (sn)}
  loudnorm          true -> -14 LUFS (varsayılan true)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("KOMUT: " + " ".join(cmd) + "\n" + r.stderr[-3000:] + "\n")
        sys.exit("ffmpeg hata verdi.")
    return r


def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool(r.stdout.strip())


def media_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())


def atempo_chain(speed):
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.5f}")
    return ",".join(parts)


def render_clip(c, i, W, H, FPS, base, tmp):
    src = os.path.join(base, c["src"]) if not os.path.isabs(c["src"]) else c["src"]
    if not os.path.exists(src):
        sys.exit(f"Kaynak bulunamadı: {src}")
    is_img = os.path.splitext(src)[1].lower() in IMG_EXT
    speed = float(c.get("speed", 1.0))
    z0 = float(c.get("zoom", 1.0))
    z1 = float(c.get("zoom_to", z0))
    cx = float(c.get("crop_x", 0.5))
    cy = float(c.get("crop_y", 0.5))
    if is_img:
        in_len = float(c.get("duration", 2.0))
        speed = 1.0
    else:
        start = float(c.get("start", 0))
        end = float(c.get("end", media_duration(src)))
        in_len = end - start
    out_len = in_len / speed
    if out_len <= 0:
        sys.exit(f"Klip {i}: süre sıfır/negatif")

    # Kadrajı doldur (cover) -> zoom -> kırp. Zoom animasyonu için scale eval=frame.
    if abs(z1 - z0) > 1e-3:
        z = f"({z0}+({z1}-{z0})*min(t/{out_len:.4f},1))"
        scale = (f"scale=w='ceil({W}*{z}/2)*2':h='ceil({H}*{z}/2)*2':eval=frame")
        zmax = max(z0, z1)
        pre = (f"scale={int(W * zmax)}:{int(H * zmax)}:force_original_aspect_ratio=increase,"
               f"crop={int(W * zmax)}:{int(H * zmax)}:(iw-ow)*{cx}:(ih-oh)*{cy},")
        vf = pre + scale + f",crop={W}:{H}:(iw-{W})/2:(ih-{H})/2"
    else:
        vf = (f"scale={int(W * z0)}:{int(H * z0)}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H}:(iw-{W})*{cx}:(ih-{H})*{cy}")
    vf = f"setpts=(PTS-STARTPTS)/{speed}," + vf + f",fps={FPS},setsar=1,format=yuv420p"

    mute = c.get("mute", speed >= 2.5)
    use_audio = (not is_img) and (not mute) and has_audio(src)
    out = os.path.join(tmp, f"klip_{i:03d}.mp4")

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if is_img:
        cmd += ["-loop", "1", "-t", f"{in_len:.3f}", "-i", src]
    else:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{in_len:.3f}", "-i", src]
    cmd += ["-f", "lavfi", "-t", f"{out_len:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]

    if use_audio:
        af = (f"[0:a]asetpts=PTS-STARTPTS,{atempo_chain(speed)},volume={c.get('volume', 1.0)},"
              f"aresample=48000,aformat=channel_layouts=stereo,"
              f"afade=t=in:d=0.03,afade=t=out:st={max(out_len - 0.04, 0):.3f}:d=0.04,"
              f"apad[a]")
        fc = f"[0:v]{vf}[v];{af}"
        amap = "[a]"
    else:
        fc = f"[0:v]{vf}[v]"
        amap = "1:a"
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", amap, "-t", f"{out_len:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out]
    run(cmd)
    return out, media_duration(out)


# ---------- ASS altyazı ----------

def ass_time(t):
    t = max(t, 0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text):
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(events, W, H, font, path):
    top = int(H * 0.17)      # üst arayüzün altında
    bottom = int(H * 0.27)   # alt arayüzün (açıklama, müzik) üstünde
    ml, mr = int(W * 0.08), int(W * 0.15)
    # Style: Name,Fontname,Fontsize,Primary,Secondary,Outline,Back,Bold,Italic,Underline,StrikeOut,
    # ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
    styles = [
        f"Style: hook,{font},{int(W * 0.085)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,{int(W * 0.007)},2,8,{ml},{mr},{top},1",
        f"Style: label,{font},{int(W * 0.062)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,{int(W * 0.0055)},1,8,{ml},{mr},{top},1",
        f"Style: center,{font},{int(W * 0.08)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,{int(W * 0.007)},2,5,{ml},{mr},0,1",
        f"Style: caption,{font},{int(W * 0.058)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,{int(W * 0.005)},1,2,{ml},{mr},{bottom},1",
        f"Style: box,{font},{int(W * 0.06)},&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,0,0,3,{int(W * 0.012)},0,8,{ml},{mr},{top},1",
    ]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    pop = "{\\fscx75\\fscy75\\t(0,120,\\fscx105\\fscy105)\\t(120,200,\\fscx100\\fscy100)}"
    for e in events:
        style = e.get("style", "label")
        anim = pop if style in ("hook", "label", "center", "box") else ""
        lines.append(f"Dialogue: 0,{ass_time(e['start'])},{ass_time(e['end'])},{style},,0,0,0,,"
                     f"{anim}{ass_escape(e['text'])}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--keep-temp", action="store_true")
    a = ap.parse_args()

    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    base = os.path.dirname(os.path.abspath(a.plan))
    W, H = int(plan.get("width", 1080)), int(plan.get("height", 1920))
    FPS = int(plan.get("fps", 30))
    font = plan.get("font", "Inter")
    output = plan.get("output", "cikti.mp4")
    output = output if os.path.isabs(output) else os.path.join(base, output)

    tmp = tempfile.mkdtemp(prefix="kurgu_")
    try:
        parts, events, t = [], [], 0.0
        for i, c in enumerate(plan["clips"]):
            path, d = render_clip(c, i, W, H, FPS, base, tmp)
            parts.append(path)
            if c.get("text"):
                events.append({"start": t, "end": t + d, "text": c["text"],
                               "style": c.get("text_style", "hook" if i == 0 else "label")})
            print(f"  klip {i + 1}/{len(plan['clips'])}: {d:.2f} sn (toplam {t + d:.2f})")
            t += d
        total = t
        for e in plan.get("captions", []):
            events.append({"start": float(e["start"]), "end": float(e["end"]),
                           "text": e["text"], "style": e.get("style", "caption")})

        listfile = os.path.join(tmp, "liste.txt")
        with open(listfile, "w") as f:
            for p in parts:
                f.write(f"file '{p}'\n")
        joined = os.path.join(tmp, "birlesik.mp4")
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", listfile, "-c", "copy", joined])

        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", joined]
        vchain = "[0:v]null"
        if events:
            ass = os.path.join(tmp, "yazi.ass")
            build_ass(events, W, H, font, ass)
            vchain = f"[0:v]ass='{ass}'"
        fc = [f"{vchain}[v]"]

        music = plan.get("music")
        if music:
            msrc = music["src"] if os.path.isabs(music["src"]) else os.path.join(base, music["src"])
            cmd += ["-stream_loop", "-1", "-ss", str(music.get("start", 0)), "-i", msrc]
            fo = float(music.get("fade_out", 1.5))
            fc.append(f"[1:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,aresample=48000,"
                      f"aformat=channel_layouts=stereo,volume={music.get('volume', 0.3)},"
                      f"afade=t=in:d=0.3,afade=t=out:st={max(total - fo, 0):.3f}:d={fo}[m]")
            if music.get("duck", True):
                fc.append("[0:a]asplit=2[o][sc]")
                fc.append("[m][sc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=350[md]")
                fc.append("[o][md]amix=inputs=2:normalize=0:duration=first[mix]")
            else:
                fc.append("[0:a][m]amix=inputs=2:normalize=0:duration=first[mix]")
            alabel = "[mix]"
        else:
            fc.append("[0:a]anull[mix]")
            alabel = "[mix]"
        if plan.get("loudnorm", True):
            fc.append(f"{alabel}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
        else:
            fc.append(f"{alabel}anull[aout]")

        cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[aout]",
                "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS),
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output]
        run(cmd)
        print(f"\nHazır: {output}  ({total:.2f} sn, {W}x{H}, {len(parts)} klip, {len(events)} yazı)")
    finally:
        if a.keep_temp:
            print(f"Geçici dosyalar: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
