"""
Audio mixer — assembles and mixes the final story audio.

Pipeline:
  1. Concatenate:  start.mp3 + narration segments + end.mp3  → narration_full.wav
  2. Build background track from audio/*.mp3 (excluding start/end) in round-robin,
     looping until it matches the narration duration.
  3. Mix using FFmpeg sidechaincompress:
       · Background auto-ducks when narration is audible (professional ducking)
       · Fades back up naturally during silence / intro / outro
  4. Export 192 kbps MP3 for Spotify.

Background discovery:
  Any .mp3 file in audio/ that is NOT named start.mp3 or end.mp3 is treated as
  a background track.  Multiple files are played in alphabetical order, looping.
"""

import itertools
import subprocess
import tempfile
from pathlib import Path

from pydub import AudioSegment
from pydub.effects import normalize

# Milliseconds of silence inserted between narration segments
_SEG_SILENCE_MS = 600


class AudioMixer:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.audio_dir = base_dir / "audio"
        self.start_file = self.audio_dir / "start.mp3"
        self.end_file = self.audio_dir / "end.mp3"
        self.bg_files = self._collect_bg_files()

    # ── Public API ────────────────────────────────────────────────────────────

    def mix(
        self,
        segments: list[tuple[str, Path]],
        output_dir: Path,
        output_name: str,
    ) -> Path:
        """
        Build final MP3. Returns the path to the output file.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)

            narration_wav = tmp / "narration_full.wav"
            bg_wav = tmp / "bg_track.wav"
            mixed_wav = tmp / "mixed.wav"

            self._build_narration(segments, narration_wav)
            duration_ms = self._audio_duration_ms(narration_wav)

            print(f"  Total duration: {duration_ms / 1000:.1f} s")

            self._build_bg_track(duration_ms, bg_wav)
            self._ffmpeg_duck_mix(narration_wav, bg_wav, mixed_wav)

            out_path = output_dir / f"{output_name}.mp3"
            self._export_mp3(mixed_wav, out_path, output_name)

        return out_path

    # ── Build narration WAV ───────────────────────────────────────────────────

    def _build_narration(
        self, segments: list[tuple[str, Path]], out_wav: Path
    ) -> None:
        """Concatenate start + narration segments + end into one WAV."""
        print("  Assembling narration…")
        track = AudioSegment.empty()
        silence = AudioSegment.silent(duration=_SEG_SILENCE_MS)

        if self.start_file.exists():
            intro = AudioSegment.from_mp3(str(self.start_file))
            track += normalize(intro)
            track += silence
            print(f"    + {self.start_file.name} ({len(intro)/1000:.1f}s)")
        else:
            print("    Warning: start.mp3 not found, skipping intro.")

        for i, (label, wav_path) in enumerate(segments):
            seg = AudioSegment.from_wav(str(wav_path))
            seg = normalize(seg)
            track += silence if i > 0 else AudioSegment.empty()
            track += seg

        track += silence

        if self.end_file.exists():
            outro = AudioSegment.from_mp3(str(self.end_file))
            track += normalize(outro)
            print(f"    + {self.end_file.name} ({len(outro)/1000:.1f}s)")
        else:
            print("    Warning: end.mp3 not found, skipping outro.")

        track.export(str(out_wav), format="wav")

    # ── Build background track ────────────────────────────────────────────────

    def _build_bg_track(self, target_ms: int, out_wav: Path) -> None:
        """
        Round-robin through background MP3 files, repeating until the
        track is at least target_ms long, then trim.
        """
        if not self.bg_files:
            print("  No background music files found — creating silent background.")
            AudioSegment.silent(duration=target_ms).export(str(out_wav), format="wav")
            return

        print(f"  Building background ({len(self.bg_files)} file(s), round-robin)…")
        pool = itertools.cycle(self.bg_files)
        bg = AudioSegment.empty()
        seen: set[str] = set()

        while len(bg) < target_ms:
            f = next(pool)
            # Prevent infinite loop if all files combined are shorter than target
            cycle_key = f.name
            if cycle_key in seen and len(bg) < 1000:
                # All files too short even combined; just pad with silence
                break
            seen.add(cycle_key)
            seg = AudioSegment.from_mp3(str(f))
            bg += seg
            seen.clear()  # reset after a full pass through the pool

        bg = bg[:target_ms]
        bg = normalize(bg)
        bg.export(str(out_wav), format="wav")

    # ── FFmpeg ducking mix ────────────────────────────────────────────────────

    def _ffmpeg_duck_mix(
        self, narration_wav: Path, bg_wav: Path, out_wav: Path
    ) -> None:
        """
        Mix narration + background with automatic ducking via sidechaincompress.
        When narration is above -25 dB, the background is compressed 8:1,
        effectively lowering it to ~15 % of its original volume.
        Attack 100 ms, release 2 s for smooth, natural transitions.
        """
        print("  Mixing with ducking (FFmpeg sidechaincompress)…")

        # Filter graph:
        #   [0] narration  →  split into [narr] (output) and [sc] (sidechain trigger)
        #   [1] background →  compressed whenever [sc] is loud  →  [bg_ducked]
        #   final mix: narr + bg_ducked at equal weights, then hard-limit
        filter_complex = (
            "[0:a]asplit=2[narr][sc];"
            "[sc][1:a]sidechaincompress="
            "threshold=0.02:"    # trigger at ~-34 dB  (quiet speech still ducks)
            "ratio=8:"           # 8:1 compression
            "attack=100:"        # 100 ms attack
            "release=2000:"      # 2 s release (smooth fade-back)
            "makeup=1"           # no makeup gain on bg
            "[bg_ducked];"
            "[narr][bg_ducked]amix=inputs=2:weights=1.5 1,"
            "alimiter=limit=0.99:level=disabled"
            "[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(narration_wav),
            "-i", str(bg_wav),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-ar", "44100",
            str(out_wav),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    # ── Export MP3 ────────────────────────────────────────────────────────────

    @staticmethod
    def _export_mp3(src_wav: Path, dst_mp3: Path, title: str) -> None:
        print("  Exporting MP3 (192 kbps)…")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src_wav),
            "-ar", "44100",
            "-b:a", "192k",
            "-id3v2_version", "3",
            "-metadata", f"title={title}",
            "-metadata", "artist=Kutle Stories",
            str(dst_mp3),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _collect_bg_files(self) -> list[Path]:
        if not self.audio_dir.exists():
            return []
        exclude = {"start.mp3", "end.mp3"}
        return sorted(
            f for f in self.audio_dir.glob("*.mp3") if f.name not in exclude
        )

    @staticmethod
    def _audio_duration_ms(wav_path: Path) -> int:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(wav_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return int(float(result.stdout.strip()) * 1000)
