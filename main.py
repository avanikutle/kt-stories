"""
Kutle Story Generator
Entry point: interactive menu → voice synthesis → audio mix → video build
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

LANG_MAP = {
    "1": "en",
    "2": "te",
    "3": "hi",
    "4": "es",
    "5": "fr",
    "6": "de",
    "7": "ar",
}

LANG_NAMES = {
    "en": "English",
    "te": "Telugu",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ar": "Arabic",
}


def _pick_number(prompt: str, low: int, high: int) -> int:
    while True:
        raw = input(f"  {prompt} [{low}-{high}]: ").strip()
        if raw.isdigit():
            val = int(raw)
            if low <= val <= high:
                return val
        print(f"  Please enter a number between {low} and {high}.")


def get_scripts() -> list[Path]:
    script_dir = BASE_DIR / "script"
    if not script_dir.exists():
        return []
    return sorted(script_dir.glob("*.txt"))


def detect_language(script_path: Path) -> str:
    name = script_path.stem.lower()
    if "telugu" in name or name.startswith("te-") or name.endswith("-te"):
        return "te"
    if "hindi" in name or name.startswith("hi-") or name.endswith("-hi"):
        return "hi"
    if "english" in name or name.startswith("en-") or name.endswith("-en"):
        return "en"
    return "en"


def prompt_menu() -> dict:
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 58)
    print("           KUTLE STORY GENERATOR")
    print("=" * 58)

    # ── Script selection ─────────────────────────────────────
    scripts = get_scripts()
    if not scripts:
        print("\n  ERROR: No .txt files found in script/ folder.")
        sys.exit(1)

    print("\n  [1] SCRIPT")
    for i, s in enumerate(scripts, 1):
        print(f"      {i}. {s.name}")
    idx = _pick_number("Select script", 1, len(scripts)) - 1
    script = scripts[idx]

    # ── Language ─────────────────────────────────────────────
    detected = detect_language(script)
    det_name = LANG_NAMES.get(detected, detected.upper())
    print(f"\n  [2] LANGUAGE  (auto-detected: {det_name})")
    for k, code in LANG_MAP.items():
        print(f"      {k}. {LANG_NAMES.get(code, code)}")
    print("      [Enter] keep auto-detected")
    raw = input("  Select: ").strip()
    language = LANG_MAP.get(raw, detected)

    # ── Voice mode ───────────────────────────────────────────
    print("\n  [3] VOICE")
    print("      1. Male   (entire narration in male voice)")
    print("      2. Female (entire narration in female voice)")
    print("      3. Both   (alternating paragraphs: male / female)")
    vm = _pick_number("Select voice mode", 1, 3)
    voice_mode = {1: "male", 2: "female", 3: "both"}[vm]

    # ── Image duration ───────────────────────────────────────
    print("\n  [4] IMAGE DURATION PER SLIDE")
    print("      1. 15 seconds")
    print("      2. 20 seconds")
    dur = _pick_number("Select duration", 1, 2)
    image_duration = 15 if dur == 1 else 20

    # ── Output name ──────────────────────────────────────────
    default_name = script.stem
    print(f"\n  [5] OUTPUT NAME  (default: {default_name})")
    raw_name = input("  Name [Enter = default]: ").strip()
    output_name = raw_name if raw_name else default_name

    return {
        "script": script,
        "language": language,
        "voice_mode": voice_mode,
        "image_duration": image_duration,
        "output_name": output_name,
    }


def main():
    cfg = prompt_menu()

    print("\n" + "=" * 58)
    print("  SUMMARY")
    print(f"    Script    : {cfg['script'].name}")
    print(f"    Language  : {LANG_NAMES.get(cfg['language'], cfg['language'].upper())}")
    print(f"    Voice     : {cfg['voice_mode']}")
    print(f"    Slide dur : {cfg['image_duration']}s")
    print(f"    Output    : output/{cfg['output_name']}/")
    print("=" * 58)

    confirm = input("\n  Proceed? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("  Cancelled.")
        return

    # Heavy imports deferred so menu shows instantly
    from voice_engine import VoiceEngine
    from audio_mixer import AudioMixer
    from video_builder import VideoBuilder

    out_dir = BASE_DIR / "output" / cfg["output_name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Voice synthesis ───────────────────────────────
    print("\n── [1/3] VOICE NARRATION ──────────────────────────────")
    engine = VoiceEngine(BASE_DIR)
    segments = engine.generate(
        script_path=cfg["script"],
        language=cfg["language"],
        voice_mode=cfg["voice_mode"],
        output_dir=out_dir,
    )
    print(f"  Generated {len(segments)} segment(s).")

    # ── Step 2: Audio mix ─────────────────────────────────────
    print("\n── [2/3] AUDIO MIX ────────────────────────────────────")
    mixer = AudioMixer(BASE_DIR)
    mp3_path = mixer.mix(
        segments=segments,
        output_dir=out_dir,
        output_name=cfg["output_name"],
    )
    print(f"  MP3 → {mp3_path}")

    # ── Step 3: Video build ───────────────────────────────────
    print("\n── [3/3] VIDEO BUILD ──────────────────────────────────")
    builder = VideoBuilder(BASE_DIR)
    mp4_path = builder.build(
        audio_path=mp3_path,
        output_dir=out_dir,
        output_name=cfg["output_name"],
        image_duration=cfg["image_duration"],
    )
    print(f"  MP4 → {mp4_path}")

    print("\n" + "=" * 58)
    print("  DONE")
    print(f"  Spotify MP3 : {mp3_path}")
    print(f"  YouTube MP4 : {mp4_path}")
    print("=" * 58)


if __name__ == "__main__":
    main()
