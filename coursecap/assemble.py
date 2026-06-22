"""Config-driven video assembler for course capture.

Reads a per-lesson JSON spec and builds the final video with ffmpeg. The engine
is app-agnostic: it only sees recorded clips, slide placeholders, optional VO,
and focus boxes -- it does not care whether the clips are Excel, PowerPoint, a
browser, or anything else. Course/script specifics live entirely in the spec.

Two modes:
  * "synced"      -> VO drives the timeline. Each clip is anchor-aligned (piecewise
                     time-warp) so on-screen events land on their narration beat.
                     Slides fill non-recorded beats. Final has the VO audio track.
  * "screenshare" -> No audio. Clips are cut to the listed segments and concatenated;
                     slides get a fixed duration. A clean visual-only walkthrough.

Spec shape (see lessons/*.json):
{
  "video": {"width":1920,"height":1080,"fps":30},
  "mode": "synced" | "screenshare",
  "voice_dir": "runs/vo",                 # synced only
  "box_color": "red", "box_thickness": 6,
  "out": "runs/Lesson_X.mp4",
  "scenes": [
    {"type":"slide","label":"...","segs":[1,2]},                       # synced
    {"type":"slide","label":"...","duration":4.0},                     # screenshare
    {"type":"clip","clip":"...","segs":[3,4],                          # synced
     "align":[[clip_a,clip_b,vo_a,vo_b],...],"boxes":[[x,y,w,h,t0,t1]]},
    {"type":"clip","clip":"...","segments":[[a,b],[a,b]]}              # screenshare
  ]
}

Usage:  python -m coursecap.assemble lessons/lesson_1_1.json
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nokey=1:noprint_wrappers=1", p],
                                capture_output=True, text=True).stdout.strip())


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(" ".join(str(c) for c in cmd[:12]) + "\n" + p.stderr[-1500:])


def build(spec_path: str):
    spec = json.load(open(spec_path, encoding="utf-8"))
    v = spec.get("video", {})
    W, H, FPS = v.get("width", 1920), v.get("height", 1080), v.get("fps", 30)
    mode = spec.get("mode", "synced")
    color, th = spec.get("box_color", "red"), spec.get("box_thickness", 6)
    work = os.path.abspath(spec.get("work_dir", "runs/_assemble"))
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)
    shutil.copy(r"C:\Windows\Fonts\arial.ttf", os.path.join(work, "font.ttf"))
    font = os.path.relpath(os.path.join(work, "font.ttf")).replace("\\", "/")
    vo = os.path.abspath(spec["voice_dir"]) if spec.get("voice_dir") else None

    def slide_vf(label, d):
        lbl = label.replace(":", "").replace("'", "")
        return (f"drawtext=fontfile={font}:text='[ SLIDE / GRAPHIC ]':fontcolor=white:"
                f"fontsize=56:x=(w-text_w)/2:y=(h/2)-90,"
                f"drawtext=fontfile={font}:text='{lbl}':fontcolor=0xAAB2BD:"
                f"fontsize=36:x=(w-text_w)/2:y=(h/2)+10")

    scene_files = []
    for i, sc in enumerate(spec["scenes"]):
        name = f"s{i}"
        # ---- audio (synced only) ----
        aout, D = None, None
        if mode == "synced":
            atxt = os.path.join(work, name + "_a.txt")
            with open(atxt, "w") as f:
                for s in sc["segs"]:
                    f.write(f"file '{vo}/seg_{s:02d}.mp3'\n")
            aout = os.path.join(work, name + ".m4a")
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", atxt,
                 "-c:a", "aac", "-b:a", "192k", aout])
            D = dur(aout)

        vout = os.path.join(work, name + "_v.mp4")
        if sc["type"] == "slide":
            d = D if D is not None else sc.get("duration", 4.0)
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0E1116:s={W}x{H}:r={FPS}:d={d:.3f}",
                 "-vf", slide_vf(sc["label"], d), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", vout])
        else:
            clip = os.path.abspath(sc["clip"])
            pieces = []
            if mode == "synced":
                ranges = sc["align"]                      # [clip_a, clip_b, vo_a, vo_b]
            else:
                ranges = [[a, b, None, None] for a, b in sc["segments"]]  # cut + concat
            for j, r in enumerate(ranges):
                ca, cb = r[0], r[1]
                pj = os.path.join(work, f"{name}_p{j}.mp4")
                vf = f"scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS}"
                if mode == "synced":
                    factor = (r[3] - r[2]) / (cb - ca)
                    vf = f"scale={W}:{H}:flags=lanczos,setsar=1,setpts={factor:.5f}*PTS,fps={FPS}"
                run(["ffmpeg", "-y", "-ss", f"{ca}", "-t", f"{cb - ca}", "-i", clip,
                     "-vf", vf, "-an", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                     "-pix_fmt", "yuv420p", pj])
                pieces.append(pj)
            ptxt = os.path.join(work, name + "_p.txt")
            with open(ptxt, "w") as f:
                for pj in pieces:
                    f.write(f"file '{pj}'\n")
            raw = os.path.join(work, name + "_raw.mp4")
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", ptxt, "-c", "copy", raw])
            boxes = sc.get("boxes", [])
            if boxes:
                bf = ",".join(f"drawbox=x={b[0]}:y={b[1]}:w={b[2]}:h={b[3]}:color={color}:t={th}"
                              f":enable='between(t,{b[4]},{b[5]})'" for b in boxes)
                run(["ffmpeg", "-y", "-i", raw, "-vf", bf, "-c:v", "libx264", "-crf", "18",
                     "-preset", "medium", "-pix_fmt", "yuv420p", vout])
            else:
                vout = raw

        sout = os.path.join(work, name + ".mp4")
        if mode == "synced":
            run(["ffmpeg", "-y", "-i", vout, "-i", aout, "-map", "0:v", "-map", "1:a",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", sout])
        else:
            shutil.copy(vout, sout)
        scene_files.append(sout)
        print(f"scene {i} [{sc['type']}] -> {os.path.basename(sout)}")

    ftxt = os.path.join(work, "final.txt")
    with open(ftxt, "w") as f:
        for s in scene_files:
            f.write(f"file '{s}'\n")
    out = os.path.abspath(spec["out"])
    args = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", ftxt,
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
    if mode == "synced":
        args += ["-c:a", "aac", "-b:a", "192k"]
    args += [out]
    run(args)
    print(f"\nDONE: {out}  ({dur(out):.1f}s, {mode})")


if __name__ == "__main__":
    build(sys.argv[1])
