#!/usr/bin/env python3
"""
Extracts every Hebrew string the app can speak and writes voice-manifest.json:
a flat {key: text} map of clips for the pre-rendered Google TTS voice pack.

Source of truth is index.html itself (EXERCISES, ENCOURAGEMENT_LINES,
SESSION_CLOSING_LINES, DAY_LETTERS) so the manifest can never drift from what
the app actually contains. A handful of fixed sentence fragments are copied
verbatim from buildSessionStartText/buildNewExerciseText/buildSessionEndText
in index.html (search those functions if this script's constants ever need
re-syncing after a wording change there).

Several additions go beyond what index.html currently speaks, for near-term
features this voice pack is being built to support:
  - frag.pr        "personal record" callout (no PR detection exists yet)
  - cd.3 / cd.2 / cd.1   spoken rest-timer countdown (rest is silent today)
  - greet.*        random session-opener lines (today's opener is one fixed
                    line, not randomized); enc./close. also gained extra
                    random picks. All three from encouragement.docx.

Number words: reps/sets/counting already use short (grammatically feminine)
forms in-app (see HEBREW_COUNT_WORDS in index.html), so num.* follows the same
convention for every context (including "X קילו", which formally wants
masculine agreement but is commonly said this way in casual Israeli Hebrew).
Flag it if that reads wrong during the native-ear listening pass.

No user name is baked into any clip here: profile.name is data she enters at
setup, not static app content, and voice-manifest.json is tracked in a public
repo (unlike audio/, it is not gitignored) — a real name has no business
being committed to it. frag.hi is just "היי!"; whatever speaks her name stays
a separate, local-only concern outside this pipeline.
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"
OUT_PATH = REPO_ROOT / "voice-manifest.json"

# Range of pre-rendered numbers. Covers realistic minutes/reps/weight-kg
# values for this app. Larger figures (e.g. total session volume) are out
# of scope for exact pre-rendering and stay as a known limitation.
NUM_WHOLE_MAX = 150
NUM_HALF_MAX = 99  # half-steps rendered as "<n> וחצי" for n in 0..NUM_HALF_MAX

# Supplied by the user (encouragement.docx), not sourced from index.html —
# same pattern as frag.pr/cd.* above: content prepared ahead of the app wiring.
# "greet" is a new random-pick pool (today's session start is one fixed line,
# not randomized); the other two extend the existing ENCOURAGEMENT_LINES /
# SESSION_CLOSING_LINES pools with additional random picks.
#
# Punctuated (the docx had none) so Cloud TTS gets prosody cues — pauses,
# falling/rising tone, emphasis — instead of reading each line flat. Wording
# is untouched; only punctuation was added, matching the tone of every
# existing line in ENCOURAGEMENT_LINES/SESSION_CLOSING_LINES, all of which
# end with real punctuation for the same reason.
GREETING_LINES = [
    'מתוקה!! חזרנו, כל הכבוד!',
    'אהלן, מה אנחנו עושים היום?',
    'מה קורה חמודה? איך האנרגיה היום?',
    'יס! הנה את, מתאמנת שוב כמו שתכננת.',
]
ENCOURAGEMENT_EXTRA = [
    'את כבר עייפה? עוד לא התחלנו!',
    'יאללה, יא אלבי!',
    'אוףףף, איזה חזקה!',
    'מהממת, תמשיכי!',
]
CLOSING_EXTRA = [
    'אין לי כוח, בא לי יין.',
    'יאללה, סיימנו! לנשום עמוק, את מהממת.',
    'איזה אימון קשוח, כל הכבוד!',
    'עוד יום על כדור הארץ שאת מהממת ויפה.',
]
# English — needs an actual English voice at generation time; a he-IL voice
# reading this would mangle it. generate_voice.py auto-detects non-Hebrew
# manifest text and routes it to a resolved English voice automatically.
ENCOURAGEMENT_EXTRA_EN = [
    "Let's go, you got this!",
]


def split_top_level_objects(text):
    """Split a `[ {...}, {...} ]` source slice into individual `{...}` object
    substrings, tracking brace depth and string literals so commas/braces
    inside Hebrew text or nested arrays never confuse the split."""
    objects = []
    depth = 0
    start = None
    in_string = False
    string_char = ""
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_char:
                in_string = False
            continue
        if ch in ("'", '"'):
            in_string = True
            string_char = ch
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start:i + 1])
                start = None
    return objects


def unescape_js_string(s):
    return s.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")


def js_string(pattern, text, required=True):
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        if required:
            raise ValueError(f"pattern not found: {pattern!r} in object:\n{text[:200]}")
        return None
    return unescape_js_string(m.group(1))


def js_string_array(pattern, text):
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        raise ValueError(f"array pattern not found: {pattern!r}")
    body = m.group(1)
    return [unescape_js_string(s) for s in re.findall(r"'((?:\\.|[^'\\])*)'", body)]


def extract_bracketed(varname, source):
    m = re.search(re.escape(f"var {varname} = [") + r"(.*?)\n\];", source, re.DOTALL)
    if not m:
        raise ValueError(f"could not locate `var {varname} = [ ... ];` in index.html")
    return m.group(1)


def extract_exercises(source):
    m = re.search(r"var EXERCISES = \[(.*?)\n\];", source, re.DOTALL)
    if not m:
        raise ValueError("could not locate `var EXERCISES = [ ... ];` in index.html")
    exercises = []
    for obj_text in split_top_level_objects(m.group(1)):
        exercises.append({
            "id": js_string(r"\{id:'([^']*)'", obj_text),
            "he": js_string(r"he:'((?:\\.|[^'\\])*)'", obj_text),
            "cues": js_string_array(r"cues:\[((?:\\.|[^\]])*)\]", obj_text),
            "common_mistake": js_string(r"common_mistake:'((?:\\.|[^'\\])*)'", obj_text),
        })
    return exercises


# --- Hebrew number-to-words (short/feminine-leaning forms, matching the
# app's existing HEBREW_COUNT_WORDS convention for 1-20) -------------------
ONES = ['אפס', 'אחת', 'שתיים', 'שלוש', 'ארבע', 'חמש', 'שש', 'שבע', 'שמונה', 'תשע']
TEENS = ['עשר', 'אחת עשרה', 'שתים עשרה', 'שלוש עשרה', 'ארבע עשרה', 'חמש עשרה',
         'שש עשרה', 'שבע עשרה', 'שמונה עשרה', 'תשע עשרה']
TENS = ['', '', 'עשרים', 'שלושים', 'ארבעים', 'חמישים', 'שישים', 'שבעים', 'שמונים', 'תשעים']


def num_to_hebrew(n):
    if n < 10:
        return ONES[n]
    if n < 20:
        return TEENS[n - 10]
    if n < 100:
        t, o = divmod(n, 10)
        return TENS[t] if o == 0 else f"{TENS[t]} ו{ONES[o]}"
    h, rem = divmod(n, 100)
    hundred_word = 'מאה' if h == 1 else f"{ONES[h]} מאות"
    if rem == 0:
        return hundred_word
    return f"{hundred_word} ו{num_to_hebrew(rem)}"


def build_manifest():
    source = INDEX_HTML.read_text(encoding="utf-8")
    exercises = extract_exercises(source)
    encouragement = [unescape_js_string(s) for s in
                      re.findall(r"'((?:\\.|[^'\\])*)'", extract_bracketed("ENCOURAGEMENT_LINES", source))]
    closing = [unescape_js_string(s) for s in
               re.findall(r"'((?:\\.|[^'\\])*)'", extract_bracketed("SESSION_CLOSING_LINES", source))]
    day_letters = [unescape_js_string(s) for s in
                   re.findall(r"'((?:\\.|[^'\\])*)'", extract_bracketed("DAY_LETTERS", source))]

    m = {}

    # -- fixed fragments (verbatim from buildSessionStartText / buildNewExerciseText / buildSessionEndText) --
    m["frag.hi"] = "היי!"
    m["frag.pr"] = "שיא אישי!"
    m["frag.today_lead"] = "היום"
    m["frag.session_len_lead"] = "האימון אמור לקחת בערך"
    m["frag.minutes_word"] = "דקות"
    m["frag.first_time"] = "פעם ראשונה בתרגיל הזה - תתחילי במשקל הכי קל שיש."
    m["frag.last_time_lead"] = "פעם שעברה עשית"
    m["frag.kilo_word"] = "קילו"
    m["frag.try_lead"] = "נסי"
    m["frag.this_time_tail"] = "הפעם"
    m["frag.sets_word"] = "סטים"
    m["frag.reps_lead"] = "עד"
    m["frag.reps_word"] = "חזרות"
    m["frag.go"] = "קדימה."
    m["frag.done"] = "סיימנו!"
    m["frag.summary_lead"] = "דקות אימון, נפח כולל של"

    for i, letter in enumerate(day_letters, start=1):
        m[f"frag.day.{i}"] = f"גוף מלא {letter}"

    # -- spoken rest-timer countdown (new; rest is currently silent) --
    m["cd.3"] = "שלוש"
    m["cd.2"] = "שתיים"
    m["cd.1"] = "אחת"

    # -- rep counting words, matches HEBREW_COUNT_WORDS 1..20 --
    for i in range(1, 21):
        m[f"count.{i:02d}"] = num_to_hebrew(i)

    # -- greeting / encouragement / closing lines --
    for i, line in enumerate(GREETING_LINES, start=1):
        m[f"greet.{i:02d}"] = line
    for i, line in enumerate(encouragement + ENCOURAGEMENT_EXTRA + ENCOURAGEMENT_EXTRA_EN, start=1):
        m[f"enc.{i:02d}"] = line
    for i, line in enumerate(closing + CLOSING_EXTRA, start=1):
        m[f"close.{i:02d}"] = line

    # -- per-exercise voice content --
    for ex in exercises:
        m[f"ex.{ex['id']}.name"] = ex["he"] + "."
        m[f"ex.{ex['id']}.cues"] = ". ".join(ex["cues"]) + "."
        m[f"ex.{ex['id']}.mistake"] = ex["common_mistake"]

    # -- numbers --
    for n in range(0, NUM_WHOLE_MAX + 1):
        m[f"num.{n}"] = num_to_hebrew(n)
    for n in range(0, NUM_HALF_MAX + 1):
        m[f"num.{n}_5"] = f"{num_to_hebrew(n)} וחצי"

    return m, exercises, encouragement, closing


def main():
    manifest, exercises, encouragement, closing = build_manifest()

    OUT_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    total_chars = sum(len(v) for v in manifest.values())
    size_kb = OUT_PATH.stat().st_size / 1024

    groups = {}
    for key in manifest:
        prefix = key.split(".")[0]
        groups.setdefault(prefix, [0, 0])
        groups[prefix][0] += 1
        groups[prefix][1] += len(manifest[key])

    print(f"{'GROUP':<10}{'CLIPS':>8}{'CHARS':>10}")
    for prefix in sorted(groups):
        count, chars = groups[prefix]
        print(f"{prefix:<10}{count:>8}{chars:>10}")
    print(f"{'TOTAL':<10}{len(manifest):>8}{total_chars:>10}")
    print()
    print(f"exercises parsed: {len(exercises)}  encouragement: {len(encouragement)}  closing: {len(closing)}")
    print(f"wrote {OUT_PATH} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
