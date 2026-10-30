"""Sarvam AI speech: transcription for voice SOS, text-to-speech for spoken alerts.

Both return None when no key is set or the call fails; callers fall back to text.
"""

import asyncio
import base64
import hashlib
import logging
import os

import httpx

from .http import Timer, client, mark

log = logging.getLogger("rahat.voice")
STT_URL = "https://api.sarvam.ai/speech-to-text"
TTS_URL = "https://api.sarvam.ai/text-to-speech"
STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "priya")
# Bulbul speaks these languages; anything else (e.g. Assamese) is voiced in Hindi.
TTS_LANGS = {"hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "od", "en"}

_tts_cache: dict[str, tuple[bytes, str]] = {}


def _key() -> str | None:
    return os.getenv("SARVAM_API_KEY") or None


async def transcribe(audio: bytes, filename: str = "voice.ogg", mime: str = "audio/ogg") -> dict | None:
    """Returns {"text", "lang"} (lang is ISO 639-1, e.g. "hi") or None."""
    key = _key()
    if not key:
        mark("Sarvam", "down", "no SARVAM_API_KEY")
        return None
    with Timer() as t:
        try:
            r = await client().post(
                STT_URL,
                headers={"api-subscription-key": key},
                data={"model": STT_MODEL, "mode": "transcribe"},
                files={"file": (filename, audio, mime)},
                timeout=30,
            )
            r.raise_for_status()
            d = r.json()
        except (httpx.HTTPError, ValueError) as e:
            mark("Sarvam", "down", f"STT failed: {e}")
            log.warning("Sarvam STT failed: %s", e)
            return None
    mark("Sarvam", "live", "speech-to-text", t.ms)
    lang = (d.get("language_code") or "hi-IN").split("-")[0]
    return {"text": d.get("transcript", "").strip(), "lang": lang}


async def speak(text: str, lang: str) -> tuple[bytes, str] | None:
    """Returns (audio bytes, "ogg" | "wav") or None. Asks for Opus so Telegram can show a voice bubble."""
    key = _key()
    if not key:
        return None
    lang = lang if lang in TTS_LANGS else "hi"
    ck = hashlib.sha1(f"{lang}|{text}".encode()).hexdigest()
    if ck in _tts_cache:
        return _tts_cache[ck]
    base = {"text": text[:2500], "language_code": f"{lang}-IN", "model": TTS_MODEL, "speaker": TTS_SPEAKER}
    with Timer() as t:
        d = None
        # Try Opus first; if the API rejects the codec field, retry with its default (WAV).
        for body in ({**base, "output_audio_codec": "opus"}, base):
            try:
                r = await client().post(TTS_URL, headers={"api-subscription-key": key}, json=body, timeout=30)
                if r.status_code in (400, 422):
                    continue
                r.raise_for_status()
                d = r.json()
                break
            except (httpx.HTTPError, ValueError) as e:
                log.warning("Sarvam TTS failed: %s", e)
                break
    if not d or not d.get("audios"):
        mark("Sarvam", "down", "TTS failed")
        return None
    mark("Sarvam", "live", "text-to-speech", t.ms)
    audio = base64.b64decode("".join(d["audios"]))
    kind = "ogg" if audio[:4] == b"OggS" else "wav"
    if kind == "wav":
        ogg = await _to_ogg_opus(audio)
        if ogg:
            audio, kind = ogg, "ogg"
    _tts_cache[ck] = (audio, kind)
    return audio, kind


async def _to_ogg_opus(wav: bytes) -> bytes | None:
    """Telegram shows voice bubbles only for OGG/Opus. Uses the ffmpeg binary bundled with imageio-ffmpeg."""
    try:
        import imageio_ffmpeg

        proc = await asyncio.create_subprocess_exec(
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
            "-c:a", "libopus", "-b:a", "32k", "-ac", "1", "-f", "ogg", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(wav), timeout=20)
        if proc.returncode == 0 and out[:4] == b"OggS":
            return out
        log.warning("ffmpeg conversion failed: %s", err.decode(errors="ignore")[:200])
    except Exception as e:
        log.warning("ffmpeg unavailable: %s", e)
    return None
