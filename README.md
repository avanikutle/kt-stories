# KT Stories — Local Voice Story Generator

Generate narrated story videos from text scripts using cloned voices — fully local, no API keys required.

## What it does

1. **Reads** any `.txt` script from the `script/` folder (English, Telugu, or other languages)
2. **Clones** the voice from a reference audio sample (male, female, or both alternating)
3. **Mixes** narration with background music — auto-ducking so music lowers during speech
4. **Exports** a Spotify-ready **MP3** and a YouTube-ready **1080p MP4** with image slideshow

## Project structure

```
kt-stories/
├── script/          # Drop your .txt scripts here
├── Voice/           # Reference voice samples (files must contain 'male' or 'female' in name)
├── audio/
│   ├── start.mp3    # Intro played before narration
│   ├── end.mp3      # Outro played after narration
│   └── *.mp3        # Background music (any number, played round-robin)
├── image/           # Images shown in the video (PNG/JPG, round-robin)
├── output/          # Generated files saved here (git-ignored)
├── main.py          # Entry point
├── voice_engine.py  # XTTS v2 voice cloning
├── audio_mixer.py   # Audio assembly + FFmpeg ducking
└── video_builder.py # FFmpeg image slideshow + audio → MP4
```

## Requirements

### System
- **Python 3.10 or 3.11** (3.12+ may have compatibility issues with XTTS)
- **FFmpeg** — install via `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org)

### Python packages
```bash
pip install -r requirements.txt
```

> **First run:** XTTS v2 model (~1.8 GB) is downloaded automatically and cached.

## Setup

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

### Optional — GPU acceleration (10–20× faster synthesis)
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```
Replace `cu121` with your CUDA version (check with `nvidia-smi`).

## Usage

Run `python main.py` and follow the interactive menu:

```
[1] Select script      — picks from script/ folder
[2] Language           — auto-detected from filename, or override
[3] Voice mode         — Male / Female / Both (alternating paragraphs)
[4] Image duration     — 15 s or 20 s per slide
[5] Output name        — folder name under output/
```

Output files appear in `output/<name>/`:
- `<name>.mp3` — final audio for Spotify
- `<name>.mp4` — 1920×1080 video for YouTube
- `segments/`  — individual narration WAVs (kept for re-use)

## Adding content

| What | Where | Convention |
|---|---|---|
| New script | `script/` | Any `.txt` file; language auto-detected from filename (`Telugu-`, `English-`, etc.) |
| Voice sample | `Voice/` | Filename must contain `male` or `female`; supports mp3, wav, mp4, m4a |
| Background music | `audio/` | Any `.mp3` not named `start.mp3` or `end.mp3`; played in alphabetical round-robin |
| Images | `image/` | PNG, JPG, WEBP; displayed in alphabetical round-robin |

## Language support

| Language | Code | XTTS native |
|---|---|---|
| English | `en` | Yes |
| Hindi | `hi` | Yes |
| Telugu | `te` | Mapped to `hi` (phonetic approximation; voice cloning still applies) |
| + 13 more | — | See XTTS v2 docs |

## Hardware notes

| Spec | Minimum | Recommended |
|---|---|---|
| RAM | 6 GB free | 8 GB+ |
| GPU VRAM | — (CPU works) | 4 GB+ for GPU mode |
| Storage | 3 GB free | — |

On CPU-only machines synthesis is slow (~5–15 min/paragraph). Close other apps to free RAM.

## Tech stack

- [XTTS v2](https://github.com/idiap/coqui-ai-TTS) — multilingual voice cloning
- [pydub](https://github.com/jiaaro/pydub) — audio manipulation
- [FFmpeg](https://ffmpeg.org) — audio mixing (sidechaincompress ducking) + video encoding

## License

MIT
