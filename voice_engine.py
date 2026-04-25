"""
Voice synthesis using XTTS v2 (Coqui TTS) — fully local, no API keys.

Voice cloning flow:
  1. Extract WAV from the reference voice file (mp3/mp4 → wav via ffmpeg)
  2. Load XTTS v2 model (downloads ~1.8 GB on first run, cached afterwards)
  3. Synthesise each script paragraph with the reference voice
  4. Return list of (voice_label, wav_path) for the mixer

Language notes:
  XTTS v2 natively supports: en es fr de it pt pl tr ru nl cs ar zh-cn hu ko ja hi
  Telugu (te), Kannada (kn), Tamil (ta) are mapped to Hindi (hi) as the closest
  supported language — pronunciation is approximate but voice cloning still applies.
"""

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

# Languages natively supported by XTTS v2
_XTTS_NATIVE = {
    "en", "es", "fr", "de", "it", "pt", "pl", "tr",
    "ru", "nl", "cs", "ar", "zh-cn", "hu", "ko", "ja", "hi",
}

# Fallback map for unsupported languages
_LANG_FALLBACK = {
    "te": "hi",
    "kn": "hi",
    "ta": "hi",
    "ml": "hi",
    "bn": "hi",
    "mr": "hi",
    "gu": "hi",
}

# XTTS works best with 6-30 s of clean reference audio
_MAX_REF_SECS = 28


class VoiceEngine:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.voice_dir = base_dir / "Voice"
        self._tts_model = None

        self._male_file = self._find_voice("male")
        self._female_file = self._find_voice("female")

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self,
        script_path: Path,
        language: str,
        voice_mode: str,
        output_dir: Path,
    ) -> list[tuple[str, Path]]:
        """
        Synthesise the script and return a list of (voice_label, wav_path) tuples.
        voice_label is 'male' or 'female'.
        """
        xtts_lang = self._resolve_lang(language)
        paragraphs = self._split_paragraphs(script_path.read_text(encoding="utf-8"))
        seg_dir = output_dir / "segments"
        seg_dir.mkdir(exist_ok=True)

        print(f"  Script has {len(paragraphs)} paragraph(s).")
        if xtts_lang != language:
            print(
                f"  Note: '{language}' is not natively supported by XTTS v2 — "
                f"using '{xtts_lang}' as phonetic approximation. "
                "Voice cloning still applies."
            )

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            male_wav = female_wav = None

            if voice_mode in ("male", "both"):
                if not self._male_file:
                    raise FileNotFoundError(
                        "No male voice sample found in Voice/ folder. "
                        "Add a file whose name contains 'male'."
                    )
                print(f"  Preparing male reference voice from {self._male_file.name}…")
                male_wav = self._prepare_reference(self._male_file, tmp / "male_ref.wav")

            if voice_mode in ("female", "both"):
                if not self._female_file:
                    raise FileNotFoundError(
                        "No female voice sample found in Voice/ folder. "
                        "Add a file whose name contains 'female'."
                    )
                print(
                    f"  Preparing female reference voice from {self._female_file.name}…"
                )
                female_wav = self._prepare_reference(
                    self._female_file, tmp / "female_ref.wav"
                )

            results: list[tuple[str, Path]] = []

            for i, para in enumerate(paragraphs):
                if voice_mode == "male":
                    label, ref = "male", male_wav
                elif voice_mode == "female":
                    label, ref = "female", female_wav
                else:
                    label = "male" if i % 2 == 0 else "female"
                    ref = male_wav if label == "male" else female_wav

                out_wav = seg_dir / f"seg_{i:03d}_{label}.wav"
                if out_wav.exists():
                    print(f"  Segment {i+1}/{len(paragraphs)} already exists, skipping.")
                else:
                    preview = para[:60].replace("\n", " ")
                    print(f"  [{i+1}/{len(paragraphs)}] {label:6s} │ {preview}…")
                    self._synthesise(para, ref, xtts_lang, out_wav)

                results.append((label, out_wav))

        return results

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _find_voice(self, gender: str) -> Path | None:
        """Locate a voice file by gender keyword in filename."""
        if not self.voice_dir.exists():
            return None
        for f in sorted(self.voice_dir.iterdir()):
            if gender in f.name.lower() and f.suffix.lower() in {
                ".mp3", ".wav", ".mp4", ".m4a", ".ogg", ".flac"
            }:
                return f
        return None

    def _prepare_reference(self, src: Path, dst: Path) -> Path:
        """
        Convert any audio/video to a mono 22050 Hz WAV, trimmed to _MAX_REF_SECS.
        XTTS v2 is finicky about sample rate and duration.
        """
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-t", str(_MAX_REF_SECS),
            "-ar", "22050",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            str(dst),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return dst

    @staticmethod
    def _resolve_lang(lang: str) -> str:
        if lang in _XTTS_NATIVE:
            return lang
        fb = _LANG_FALLBACK.get(lang)
        if fb:
            return fb
        return "en"

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """Split by one or more blank lines; filter empty results."""
        chunks = re.split(r"\n\s*\n", text.strip())
        return [c.strip() for c in chunks if c.strip()]

    @staticmethod
    def _split_into_chunks(text: str, max_chars: int = 230) -> list[str]:
        """
        XTTS v2 has an internal token limit (~250 chars safe).
        Split on sentence boundaries so each chunk is under max_chars.
        """
        if len(text) <= max_chars:
            return [text]

        # Sentence-ending punctuation for Latin + Devanagari + Telugu
        sentences = re.split(r'(?<=[.!?।॥।॥])\s+', text)
        chunks: list[str] = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) + 1 <= max_chars:
                current = (current + " " + sent).strip() if current else sent
            else:
                if current:
                    chunks.append(current)
                # If a single sentence is still too long, hard-split it
                if len(sent) > max_chars:
                    for start in range(0, len(sent), max_chars):
                        chunks.append(sent[start : start + max_chars])
                    current = ""
                else:
                    current = sent
        if current:
            chunks.append(current)
        return chunks

    def _get_tts(self):
        """Lazy-load XTTS v2 model (downloads on first use, ~1.8 GB)."""
        if self._tts_model is None:
            print(
                "\n  Loading XTTS v2 model (first run downloads ~1.8 GB — "
                "this is a one-time operation)…"
            )
            try:
                import torch
                from TTS.api import TTS

                use_gpu = torch.cuda.is_available()
                if use_gpu:
                    print("  GPU detected — synthesis will be fast.")
                else:
                    print(
                        "  No GPU detected — running on CPU. "
                        "Expect ~2-5 min per paragraph. Consider enabling CUDA."
                    )
                self._tts_model = TTS(
                    model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                    gpu=use_gpu,
                )
            except ImportError as e:
                raise ImportError(
                    "TTS library not found. Run:  pip install TTS"
                ) from e
        return self._tts_model

    def _synthesise(
        self,
        text: str,
        speaker_wav: Path,
        language: str,
        out_path: Path,
    ) -> None:
        """Synthesise text → WAV, handling XTTS chunk limits automatically."""
        tts = self._get_tts()
        chunks = self._split_into_chunks(text)

        if len(chunks) == 1:
            tts.tts_to_file(
                text=chunks[0],
                speaker_wav=str(speaker_wav),
                language=language,
                file_path=str(out_path),
            )
            return

        # Multiple chunks → synthesise each, concatenate with 300 ms silence
        silence_samples = int(22050 * 0.3)
        parts: list[np.ndarray] = []
        sr = 22050

        with tempfile.TemporaryDirectory() as td:
            for j, chunk in enumerate(chunks):
                chunk_path = Path(td) / f"chunk_{j}.wav"
                tts.tts_to_file(
                    text=chunk,
                    speaker_wav=str(speaker_wav),
                    language=language,
                    file_path=str(chunk_path),
                )
                audio, sr = sf.read(str(chunk_path))
                parts.append(audio)
                parts.append(np.zeros(silence_samples, dtype=audio.dtype))

        combined = np.concatenate(parts[:-1])  # drop trailing silence
        sf.write(str(out_path), combined, sr)
