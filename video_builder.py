"""
Video builder — combines images + audio into a YouTube-ready MP4.

Image handling:
  · Discovers all PNG/JPG/JPEG/WEBP files from image/ in alphabetical order.
  · Displays them round-robin, each for `image_duration` seconds.
  · Images are letterboxed / pillarboxed to 1920×1080 (black bars preserve aspect ratio).

Output:
  · H.264 video, AAC 192 kbps audio, yuv420p pixel format.
  · -movflags +faststart so the file streams immediately on YouTube.
"""

import itertools
import subprocess
import tempfile
from pathlib import Path


class VideoBuilder:
    WIDTH = 1920
    HEIGHT = 1080
    FPS = 24
    VIDEO_CODEC = "libx264"
    CRF = "18"          # quality: 0 (lossless) – 51 (worst); 18 = near-lossless

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.image_dir = base_dir / "image"
        self.images = self._collect_images()

    # ── Public API ────────────────────────────────────────────────────────────

    def build(
        self,
        audio_path: Path,
        output_dir: Path,
        output_name: str,
        image_duration: int = 15,
    ) -> Path:
        if not self.images:
            raise FileNotFoundError(
                "No images found in image/ folder. "
                "Add at least one PNG or JPG file."
            )

        audio_secs = self._audio_duration_secs(audio_path)
        print(f"  Audio duration : {audio_secs:.1f} s")
        print(f"  Image duration : {image_duration} s per slide")
        print(f"  Images found   : {len(self.images)} (round-robin)")

        # How many slides do we need to cover the full audio?
        num_slides = max(1, -(-int(audio_secs) // image_duration))  # ceiling division
        image_cycle = itertools.cycle(self.images)
        slide_sequence = [next(image_cycle) for _ in range(num_slides)]

        out_path = output_dir / f"{output_name}.mp4"

        with tempfile.TemporaryDirectory() as td:
            concat_file = Path(td) / "slides.txt"
            self._write_concat_file(slide_sequence, image_duration, concat_file)
            self._ffmpeg_build(concat_file, audio_path, out_path, audio_secs)

        return out_path

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _collect_images(self) -> list[Path]:
        if not self.image_dir.exists():
            return []
        exts = {".png", ".jpg", ".jpeg", ".webp"}
        return sorted(
            f for f in self.image_dir.iterdir() if f.suffix.lower() in exts
        )

    @staticmethod
    def _audio_duration_secs(audio_path: Path) -> float:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())

    @staticmethod
    def _write_concat_file(
        slides: list[Path], duration: int, dest: Path
    ) -> None:
        """
        Write an ffmpeg concat demuxer file.
        The last entry has no explicit duration so ffmpeg uses -shortest to stop
        at the audio end rather than showing a black frame.
        """
        lines: list[str] = []
        for img in slides:
            # Forward slashes required even on Windows for ffmpeg concat demuxer
            lines.append(f"file '{img.as_posix()}'")
            lines.append(f"duration {duration}")
        # Repeat last image without duration so -shortest takes effect
        lines.append(f"file '{slides[-1].as_posix()}'")
        dest.write_text("\n".join(lines), encoding="utf-8")

    def _ffmpeg_build(
        self,
        concat_file: Path,
        audio_path: Path,
        out_path: Path,
        audio_secs: float,
    ) -> None:
        print("  Building video with FFmpeg…")

        # Scale + pad filter: fit image inside 1920×1080, pad remaining with black
        vf = (
            f"scale={self.WIDTH}:{self.HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={self.WIDTH}:{self.HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
            "format=yuv420p"
        )

        cmd = [
            "ffmpeg", "-y",
            # Image slideshow input
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            # Audio input
            "-i", str(audio_path),
            # Video encoding
            "-vf", vf,
            "-c:v", self.VIDEO_CODEC,
            "-crf", self.CRF,
            "-preset", "medium",
            "-r", str(self.FPS),
            # Audio encoding
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            # Stop at whichever stream ends first (audio wins)
            "-shortest",
            # Optimise for streaming (moov atom at front)
            "-movflags", "+faststart",
            str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  Video written  : {out_path.name}")
