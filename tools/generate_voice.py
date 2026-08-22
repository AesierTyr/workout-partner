#!/usr/bin/env python3
"""
Google Cloud TTS driver for the voice pack (see voice-manifest.json,
produced by extract_voice_strings.py).

Three modes:
  --list-voices   sanity-check auth + list available he-IL voices. Free.
  --sample        synthesize a handful of representative lines across every
                   he-IL voice, into audio/_samples/, for on-phone audition.
                   Cheap (tens of clips, a few hundred characters total).
  --voice NAME    full build: every manifest clip, in one chosen voice, into
                   audio/. Costs real quota — this is the next session's step,
                   after a voice has been picked from the samples.

Auth: relies on Application Default Credentials (`gcloud auth application-
default login`, done once in Part 0). No key file is read or written by this
script; nothing here should ever need a committed credential.

Mixed-language manifest: most clips are Hebrew, but a manifest entry can be
plain English (e.g. enc.21, "Let's go, you got this!") — a he-IL voice would
mangle Latin text, so any entry with no Hebrew characters is automatically
routed to a resolved English voice instead of the chosen he-IL voice. The
English voice is picked once per run (prefers Chirp3-HD, same tier as the
Hebrew voices) and reused for every non-Hebrew clip.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HEBREW_RE = re.compile("[" + chr(0x0591) + "-" + chr(0x05F4) + "]")  # Hebrew unicode block

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "voice-manifest.json"
AUDIO_DIR = REPO_ROOT / "audio"
SAMPLES_DIR = AUDIO_DIR / "_samples"
HASHES_PATH = REPO_ROOT / ".hashes.json"

# Representative cross-section for --sample: greeting, PR callout,
# encouragement, rest countdown, an exercise name, a rep count.
SAMPLE_KEYS = ["frag.hi", "frag.pr", "enc.01", "cd.3", "ex.chest_press_machine.name", "count.05"]

MAX_SAMPLE_VOICES = 8


def load_client():
    try:
        from google.cloud import texttospeech
    except ImportError:
        print("google-cloud-texttospeech is not installed. Run: pip install google-cloud-texttospeech", file=sys.stderr)
        sys.exit(1)
    try:
        client = texttospeech.TextToSpeechClient()
    except Exception as e:
        print(f"Could not create a Text-to-Speech client: {e}", file=sys.stderr)
        print("Check `gcloud auth application-default login` was run (Part 0).", file=sys.stderr)
        sys.exit(1)
    return texttospeech, client


def list_he_voices(texttospeech, client):
    try:
        resp = client.list_voices(language_code="he-IL")
    except Exception as e:
        print(f"list_voices failed: {e}", file=sys.stderr)
        sys.exit(1)
    voices = [v for v in resp.voices if "he-IL" in v.language_codes]
    return voices


_EN_VOICE_CACHE = {}


def resolve_english_voice(texttospeech, client):
    """Picks one en-US voice (Chirp3-HD preferred) and caches it for the run."""
    if "voice" in _EN_VOICE_CACHE:
        return _EN_VOICE_CACHE["voice"]
    try:
        resp = client.list_voices(language_code="en-US")
    except Exception as e:
        print(f"list_voices(en-US) failed: {e}", file=sys.stderr)
        sys.exit(1)
    voices = [v for v in resp.voices if "en-US" in v.language_codes]
    chirp = [v for v in voices if "Chirp3-HD" in v.name]
    chosen = (chirp or voices)[0]
    _EN_VOICE_CACHE["voice"] = chosen.name
    return chosen.name


def voice_for_text(texttospeech, client, text, default_voice_name):
    """Returns (language_code, voice_name) for this clip's text."""
    if HEBREW_RE.search(text):
        return "he-IL", default_voice_name
    en_voice = resolve_english_voice(texttospeech, client)
    return "en-US", en_voice


def cmd_list_voices(args):
    texttospeech, client = load_client()
    voices = list_he_voices(texttospeech, client)
    if not voices:
        print("No he-IL voices returned. Auth worked but the response was empty — check the API is enabled for this project.")
        return
    print(f"{'NAME':<28}{'GENDER':<10}{'SAMPLE_RATE_HZ':>15}")
    for v in voices:
        gender = texttospeech.SsmlVoiceGender(v.ssml_gender).name
        print(f"{v.name:<28}{gender:<10}{v.natural_sample_rate_hertz:>15}")
    print(f"\n{len(voices)} he-IL voices available.")


def synth(texttospeech, client, text, voice_name, out_path, rate=1.0, language_code="he-IL"):
    input_ = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code=language_code, name=voice_name)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=rate)
    resp = client.synthesize_speech(input=input_, voice=voice, audio_config=audio_config)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.audio_content)
    return len(text)


def load_manifest():
    if not MANIFEST_PATH.exists():
        print(f"{MANIFEST_PATH} not found. Run extract_voice_strings.py first.", file=sys.stderr)
        sys.exit(1)
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def cmd_sample(args):
    texttospeech, client = load_client()
    manifest = load_manifest()
    missing = [k for k in SAMPLE_KEYS if k not in manifest]
    if missing:
        print(f"Sample keys missing from manifest: {missing}", file=sys.stderr)
        sys.exit(1)

    voices = list_he_voices(texttospeech, client)
    if args.voices:
        wanted = set(args.voices.split(","))
        voices = [v for v in voices if v.name in wanted]
    else:
        voices = voices[:MAX_SAMPLE_VOICES]
    if not voices:
        print("No matching he-IL voices — nothing to sample.", file=sys.stderr)
        sys.exit(1)

    rate_suffix = "" if args.rate == 1.0 else f"__rate{args.rate}"
    total_chars = 0
    written = []
    for voice in voices:
        for key in SAMPLE_KEYS:
            text = manifest[key]
            lang, voice_name = voice_for_text(texttospeech, client, text, voice.name)
            safe_key = key.replace(".", "_")
            out_path = SAMPLES_DIR / f"{voice_name}__{safe_key}{rate_suffix}.mp3"
            total_chars += synth(texttospeech, client, text, voice_name, out_path, rate=args.rate, language_code=lang)
            written.append(out_path)

    print(f"{len(voices)} voices x {len(SAMPLE_KEYS)} lines = {len(written)} sample files")
    for p in sorted(written):
        print(f"  {p.relative_to(REPO_ROOT)}  ({p.stat().st_size} bytes)")
    print(f"\ntotal characters synthesized: {total_chars}")


def load_hashes():
    if HASHES_PATH.exists():
        return json.loads(HASHES_PATH.read_text(encoding="utf-8"))
    return {}


def save_hashes(hashes):
    HASHES_PATH.write_text(json.dumps(hashes, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cmd_voice(args):
    import hashlib

    texttospeech, client = load_client()
    manifest = load_manifest()
    hashes = load_hashes().setdefault(args.voice, {})

    total_chars = 0
    generated = 0
    skipped = 0
    for key, text in manifest.items():
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if hashes.get(key) == digest:
            skipped += 1
            continue
        lang, voice_name = voice_for_text(texttospeech, client, text, args.voice)
        out_path = AUDIO_DIR / args.voice / (key.replace(".", "/") + ".mp3")
        total_chars += synth(texttospeech, client, text, voice_name, out_path, rate=args.rate, language_code=lang)
        hashes[key] = digest
        generated += 1

    all_hashes = load_hashes()
    all_hashes[args.voice] = hashes
    save_hashes(all_hashes)

    print(f"voice: {args.voice}")
    print(f"generated: {generated}  skipped (unchanged): {skipped}  total characters this run: {total_chars}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-voices", action="store_true", help="list available he-IL voices")
    group.add_argument("--sample", action="store_true", help="generate audition samples across voices")
    group.add_argument("--voice", metavar="NAME", help="full build: every clip, in this voice")
    parser.add_argument("--rate", type=float, default=1.0, help="speaking_rate passed to Cloud TTS (0.25-4.0, default 1.0)")
    parser.add_argument("--voices", metavar="NAME,NAME,...", help="--sample only: limit to these voice names instead of the first %d discovered" % MAX_SAMPLE_VOICES)
    args = parser.parse_args()

    if args.list_voices:
        cmd_list_voices(args)
    elif args.sample:
        cmd_sample(args)
    elif args.voice:
        cmd_voice(args)


if __name__ == "__main__":
    main()
