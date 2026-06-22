"""Voiceover generation via ElevenLabs (one mp3 per script segment).

App-agnostic: takes a list of narration segments and a voice; knows nothing about
the course content. Key comes from env ELEVENLABS_API_KEY (never written to disk).

  python -m coursecap.tts segments.json out_dir
where segments.json is a JSON list of strings (the narration, in order).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error


def synth(segments, out_dir, *, voice_id=None, model="eleven_multilingual_v2",
          stability=0.5, similarity=0.75):
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID")
    os.makedirs(out_dir, exist_ok=True)
    for i, text in enumerate(segments, 1):
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        body = json.dumps({"text": text, "model_id": model,
                           "voice_settings": {"stability": stability,
                                              "similarity_boost": similarity,
                                              "style": 0.0, "use_speaker_boost": True}}).encode()
        req = urllib.request.Request(url, data=body, headers={
            "xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                open(os.path.join(out_dir, f"seg_{i:02d}.mp3"), "wb").write(r.read())
            print(f"seg_{i:02d}: ok")
        except urllib.error.HTTPError as e:
            print(f"seg_{i:02d}: HTTP {e.code} {e.read().decode(errors='replace')[:200]}")
            raise


if __name__ == "__main__":
    segs = json.load(open(sys.argv[1], encoding="utf-8"))
    synth(segs, sys.argv[2])
