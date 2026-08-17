# Build Spec — "מאמנת אישית" (Personal Gym Coach)

A single-user, offline-first web app that plans gym workouts and coaches the user
through them out loud in Hebrew.

**Read this whole file before writing code.** Build in the phases listed at the
bottom, in order. Do not skip to Phase 3.

---

## 1. Who this is for

One person. A woman living abroad for a year. Context that drives every decision:

- **Hebrew speaker in a non-Hebrew-speaking country.** She cannot read the
  signage on the gym machines, cannot ask staff questions easily, and cannot
  join the local group classes. The app is her instructor.
- **Beginner with weights.** Her background is Pilates — she has good body
  awareness and core control, but she does not know gym exercises, does not
  know what weight to start with, and does not know what the machines are called.
- **Trains alone.** No spotter, no coach, nobody to check her form.
- **On her phone, in the gym, probably with no signal.**
- She misses training with a group. The loneliness is part of the problem the
  app is solving, not a side note. The voice should feel like a person is with
  her, not like a stopwatch.

Everything below follows from those five points.

---

## 2. Hard constraints

| Constraint | Requirement |
|---|---|
| Offline | **Every core function must work in airplane mode, forever, after first load.** Planning, coaching, logging, voice — all local. Online features exist (§2.1) but are strictly optional and must fail silently. Never block the UI on a network request. |
| Distribution | Hosted as a static site (§2.1). Source is `index.html` + `sw.js` + `manifest.json` — three files, no build step, no npm, no bundler, no external CDN, no runtime dependencies. |
| Platform | **Chrome on Android**, portrait, one-handed, sweaty fingers. Target Chrome 110+. Do not spend effort on iOS Safari compatibility — it is not the target device. |
| Install | A real installable PWA: proper `manifest.json` (standalone display, portrait orientation, name, icons) and a service worker that cache-firsts the entire app shell on install. She should be able to turn off mobile data entirely and have it still open from the home screen. |
| Language | **Entire UI and all voice output in Hebrew. RTL layout** (`<html dir="rtl" lang="he">`). |
| Storage | `localStorage` only. No accounts, no login, no cloud. |
| Dependencies | Zero. Vanilla JS. |

### 2.1 Hosting, updates, and what the internet is allowed to do

The device has internet. That buys exactly three things, and nothing else.

**1. Hosting and silent updates.** Deploy the static files to GitHub Pages (free,
HTTPS by default, which the service worker requires). She opens the URL once,
installs the PWA, and never needs to be sent a file again. When the code changes,
push to the repo and the service worker picks it up.

Service worker update strategy — get this right or she will be stuck on a broken
version with no way to clear it:
- Cache-first for the app shell, so offline is instant.
- On every launch, fetch the SW in the background and check for a new version.
- When a new version is ready, **do not hot-swap mid-session.** Set a flag and
  apply it on the next app open, showing a small one-line Hebrew notice that the
  app updated. Losing a workout to a refresh is unacceptable.
- Version the cache name (`coach-v1`, `coach-v2`…) and delete old caches on activate.
- Never cache `localStorage` state anywhere near this. Her log is sacred; a bad
  cache purge must not touch it.

**2. Share workout summary — build this, it matters.**
At the end of a session, a **שתפי אימון** button using the Web Share API
(`navigator.share`, well supported in Chrome Android). It shares a short plain-text
Hebrew summary: date, session name, exercises, total volume, any personal bests,
and a closing line. She sends it to whoever she wants on WhatsApp.

This is not analytics or social features. It exists because she trains alone in a
country where nobody knows her, and the whole reason this app is being built is
that she misses training with people. A one-tap "I did it, here's proof" to a
friend back home is the closest thing to that. Treat it as a core feature, not a
nice-to-have. Fall back to copy-to-clipboard if `navigator.share` is unavailable.

**3. Optional exercise demo lookup.**
She is a beginner and static SVGs only go so far. On the exercise screen, a small
secondary **איך עושים את זה?** button that opens a YouTube search URL in a new tab
for that exercise's English name plus "form". Do not embed video, do not use an
API key, do not cache video, do not autoplay. It is a link out, it is clearly
secondary to the on-screen cues, and if there is no connection it is simply
hidden. The app must be fully usable without ever tapping it.

**Explicitly out of bounds, despite the connection:**
- **No LLM or AI API for plan generation.** The plan generator stays rule-based
  (§8). Deterministic, instant, works offline, and — more importantly — cannot
  invent an unsafe exercise for a beginner training alone. This is a safety
  decision, not a technical one. Do not add it.
- No accounts, no login, no user database, no sync server, no analytics,
  no telemetry, no crash reporting, no third-party scripts of any kind.

---

## 3. Safety rules — non-negotiable, build these in

She is a beginner training alone. The app must be conservative by design.

1. **No barbell back squat, no barbell bench press, no conventional barbell
   deadlift in the generated plans.** Not at this level, not without a spotter.
   Use machines, dumbbells, cables, and bodyweight. (Goblet squat, dumbbell RDL,
   and hip thrust are fine and should be included.)
2. **First session of any new exercise is calibration, not training.** The app
   explicitly instructs: use the lightest available weight, do the reps, and
   record how it felt. It suggests real working weight only from session two.
3. **"How did that feel?" after every set** — three buttons: `קל` / `מאוזר` /
   `מדי כבד`. This drives the progression logic and is the only input she has
   to give.
4. **Never increase weight more than one increment per week per exercise.**
   If she logs `מדי כבד`, the app *reduces* the suggestion next time and says so.
5. **Form cues are mandatory in the voice script**, not optional text. Max three
   per exercise, short, imperative.
6. **A permanent, honest disclaimer on the setup screen** (Hebrew): this app is
   not a physiotherapist or a trainer; if something hurts — sharp pain, joint
   pain, not muscle burn — stop, and it is worth paying for one or two sessions
   with a trainer at the gym to check form. Do not bury this in a modal she
   dismisses once. Put it in the settings screen permanently too.
7. **Pain check on any exercise she reports pain in** — that exercise is
   auto-swapped out of future plans and flagged in settings so she can re-enable
   it.

---

## 4. Data model

All in `localStorage` under a single key `coach_v1`, one JSON object.

```js
{
  profile: {
    name: string,
    daysPerWeek: 2 | 3 | 4,
    sessionMinutes: 30 | 45 | 60,
    goal: 'strength' | 'tone' | 'general',   // Hebrew labels in UI
    focusAreas: string[],                     // optional emphasis
    voiceEnabled: boolean,
    voiceRate: number,                        // 0.8–1.2
    localLangNames: boolean                   // show local-language exercise name
  },
  equipment: {                                // set during gym walkthrough
    [equipmentId: string]: boolean
  },
  plan: {
    generatedAt: ISOstring,
    split: 'fullbody' | 'upperlower',
    days: [ { id, nameHe, blocks: [ { exerciseId, sets, repRange, restSec } ] } ]
  },
  log: [
    { date, dayId, exerciseId, sets: [ { weight, reps, feel }], painFlag: bool }
  ],
  disabledExercises: string[],
  streak: { current: number, lastSessionDate: string }
}
```

Ship a `Reset` button in settings that wipes it. Ship an `Export` button that
dumps the JSON to the clipboard — that is her backup, since there is no cloud.

---

## 5. Screens

### 5.1 Setup (first run only)

Short. Four questions, one per screen, big tap targets:

1. שם (name) — used in the voice: *"מוריה, בואי, נתחיל"*
2. כמה פעמים בשבוע (2 / 3 / 4)
3. כמה זמן יש לך לאימון (30 / 45 / 60 דקות)
4. מה המטרה (חיזוק / חיטוב / כושר כללי) — explain each in one line, plainly.

Then the disclaimer from §3.6. Then the gym walkthrough.

### 5.2 Gym walkthrough — the most important screen in the app

This is how the app learns what her gym has. Frame it as a task:
*"בפעם הראשונה שאת מגיעה לחדר כושר, תסתובבי בו במשך כ-10 דקות ותסמני מה יש."*

Present a checklist of equipment. **For each item show:**
- Hebrew name (large)
- English name (small — this is often what is written on the machine plate)
- **A one-sentence physical description in Hebrew of what it looks like**, so she
  can identify it without being able to read anything. This is critical. Example:
  *"מכונה עם משענת גב שנשענים עליה, ומייצבים ידיות קדימה."*
- A simple inline SVG line-drawing icon. Draw these yourself, minimal strokes.
  No external images.

Equipment list (ids in code, Hebrew shown):

| id | Hebrew | English |
|---|---|---|
| `dumbbells` | משקולות יד | Dumbbells |
| `bench_flat` | ספסל שטוח | Flat bench |
| `bench_adj` | ספסל מתכוונן | Adjustable bench |
| `cable` | מתקן פולי / כבלים | Cable machine |
| `latpulldown` | מתקן משיכה עליונה | Lat pulldown |
| `seatedrow` | מתקן חתירה בישיבה | Seated row |
| `chestpress` | מתקן לחיצת חזה | Chest press machine |
| `shoulderpress` | מתקן לחיצת כתפיים | Shoulder press machine |
| `legpress` | מכונת לחיצת רגליים | Leg press |
| `legcurl` | מכונת כפיפת רגליים | Leg curl |
| `legext` | מכונת פשיטת רגליים | Leg extension |
| `smith` | מתקן סמית' | Smith machine |
| `kettlebell` | קטלבל | Kettlebell |
| `band` | גומיית התנגדות | Resistance band |
| `mat` | מזרן | Mat |
| `treadmill` | הליכון | Treadmill |
| `bike` | אופני כושר | Stationary bike |
| `pullupbar` | מתח | Pull-up bar |
| `hipthrust` | מכונת הרמת אגן | Hip thrust machine |

Every item defaults to **unchecked**. She can revisit and edit this screen any
time from settings. Bodyweight and mat exercises must always be available so the
app produces a valid plan even if she checks nothing.

Add a free-text note field: *"יש עוד ציוד שאת רוצה לרשום?"* — just stored, not parsed.

### 5.3 Home

- Greeting with her name, and today's session or rest day.
- One giant button: **התחילי אימון**.
- Streak (gentle — never guilt-trip, never a red broken-streak state).
- Small link: עדכני את שם / ההגדרות / ההיסטוריה.

### 5.4 Session runner — the core

Full-screen, one exercise at a time. Layout top to bottom:

1. Progress: `תרגיל 3 מתוך 7`
2. **Exercise name in Hebrew, huge.** English name underneath, small.
3. Inline SVG showing the movement (two-frame: start position / end position).
4. Target: `3 סטים × 10-12 חזרות`
5. Suggested weight from history: `פעם שעברה: 12 ק"ג` — `נסי 14 ק"ג`
6. Form cues — max three, as a short Hebrew list.
7. Buttons, thumb-reachable at the bottom:
   - **סיימתי סט** (primary, largest)
   - **החליפי תרגיל** (the machine is taken or missing — substitute chain)
   - **דילוג**
   - **כואב לי** (triggers §3.7)

After **סיימתי סט**: quick log — reps done (stepper, prefilled with target),
weight (stepper), and feel (`קל` / `מאוזר` / `מדי כבד`). Three taps max. Then
rest timer.

**Rest timer:** big circular countdown, and voice. She can add 30s or skip.
Screen must not sleep — use the **Wake Lock API**, re-acquire on
`visibilitychange`. If unsupported (older iOS), fall back to a hidden looping
silent audio element to keep the screen alive, and warn her once to set her
auto-lock longer.

### 5.5 Substitute flow

Every exercise has an ordered `substitutes` array of other exercise ids. Tapping
**החליפי תרגיל** shows the next 2–3 valid substitutes she has equipment for,
same muscle group, with a one-line reason (*"מתאים לאותם שרירים, אבל בציוד אחר"*).
Her choice applies to this session only, unless she taps *"תמיד להחליף"*.

### 5.6 History

Per-exercise weight progression, plain and readable. Draw the chart as inline
SVG — no chart library. Keep it simple: she wants to see the line go up, not
analyze it. Show total sessions and a "personal best" per exercise.

### 5.7 Settings

Voice on/off, voice speed, rest defaults, re-run gym walkthrough, re-enable
disabled exercises, regenerate plan, export data, reset, permanent disclaimer.

---

## 6. The voice coach

This is the feature. Everything else is scaffolding. She trains alone and the
point is that she doesn't feel alone.

**Technical:**
Target is Chrome on Android with Google Text-to-Speech, which ships solid `he-IL`
support. This is the good case — build for it properly.

- `window.speechSynthesis` with `SpeechSynthesisUtterance`, `lang = 'he-IL'`.
- Voices load async and `getVoices()` returns empty on first call. Wait for the
  `voiceschanged` event, then select a `he-IL` voice. Prefer a local/offline
  voice (`voice.localService === true`) over a network one so speech still works
  in airplane mode — **check this explicitly**, since a network-only TTS voice
  would silently break the entire app in a basement gym.
- Chrome still requires a user gesture before audio plays. Prime it: speak the
  session greeting on the tap of **התחילי אימון**, never before.
- **If no Hebrew voice is installed**, do not fall back to an English voice
  mangling Hebrew text. Detect it, disable voice, and show a one-time Hebrew
  message with the fix: Settings → System → Languages & input → Text-to-speech
  output → Google TTS → Install voice data → עברית. Meanwhile compensate with
  larger on-screen cues and countdown beeps from a small `AudioContext` oscillator.
- Cancel any queued speech before speaking something new. Never let cues stack —
  this is the single most common way a voice app becomes unbearable.
- Android may pause speech when the screen locks. Wake Lock (§5.4) mostly
  prevents this; also re-check `speechSynthesis.speaking` on `visibilitychange`
  and recover rather than hanging the session state machine.
- **Recommend headphones on the first session screen** — she's in a public gym
  and a phone announcing squat cues in Hebrew is not what she wants.

**Script — what it actually says. Write these as Hebrew string templates:**

| Moment | Content |
|---|---|
| Session start | Greets her by name, says what today's session is and how long it should take. |
| Before each exercise | Names the exercise, says which machine or weight, gives the 3 form cues, states sets and reps. |
| Set start | Short: *"קדימה"* |
| Rep counting | Optional toggle. If on, count reps aloud at a steady pace for timed/tempo work. Off by default — she should go at her own pace. |
| Set end | Confirms, states rest duration. |
| Rest — last 10s | Counts down 3, 2, 1. |
| Between exercises | One short line of encouragement. **Write at least 15 variants and rotate randomly.** Repetition is what makes it feel like a machine instead of a person. Keep them warm and normal — the register of a friend who trains with her, not a motivational poster. Avoid anything about appearance, weight, or "burning fat." |
| Personal best | Calls it out specifically: *"זה משקל שיא שברת בתרגיל הזה"* |
| Session end | Total time, total volume, one genuine closing line. |

Tone rules: no shouting, no drill-sergeant, no body talk, no guilt. Second
person feminine throughout — **check every single Hebrew string for correct
feminine conjugation.** This is easy to get wrong and it will feel broken to her
immediately if you do.

---

## 7. Exercise library

An array of objects, inline in the file. **Minimum 40 exercises.** Schema:

```js
{
  id: 'chest_press_machine',
  he: 'לחיצת חזה במכונה',
  en: 'Chest Press Machine',
  equipment: ['chestpress'],        // needs ALL of these
  muscles: ['chest', 'triceps', 'shoulders'],
  primary: 'chest',
  pattern: 'horizontal_push',       // for plan balancing
  level: 1,                         // 1 beginner, 2 intermediate
  repRange: [10, 12],
  restSec: 60,
  cues: [                            // Hebrew, max 3, short, imperative
    'שבי זקוף עם הגב צמוד למשענת',
    'מרפקים בזווית של 45 מעלות',
    'תנועה איטית ונשלטת, לא בתנופה'
  ],
  common_mistake: 'לא לתת למרפקים להיפתח יותר מדי הצידה',
  substitutes: ['db_bench_press', 'pushup', 'band_chest_press'],
  svg: '...'                         // inline two-frame line drawing
}
```

Movement patterns to cover, so plans stay balanced:
`horizontal_push`, `vertical_push`, `horizontal_pull`, `vertical_pull`,
`squat`, `hinge`, `lunge`, `core`, `carry`.

Starter set — expand to 40+, keep the Hebrew names as written here since these
are the terms actually used in Israeli gyms:

- לחיצת חזה במכונה · לחיצת חזה עם משקולות · שכיבות סמיכה (רגילה/על ברכיים)
- פרפר במכונה · פרפר עם משקולות
- משיכת פולי עליון · מתח מסייע
- חתירה בישיבה במכונה · חתירה עם משקולת יד · חתירה בפולי
- לחיצת כתפיים עם משקולות · הרמת כתפיים צדדית
- כפיפת מרפק · פשיטת מרפק בפולי · שקיעות (דיפס) עם ספסל
- סקוואט גובלט (goblet) · לחיצת רגליים במכונה · סקוואט משקל גוף
- מנשא הרנא עם משקולות · כפיפת רגליים במכונה · פשיטת רגליים במכונה
- מדרגה למקדה · מדרגה למאחור · עלייה (step-up)
- הרמת אגן / היפ ת'רסט · הרמת אגן במכונה
- הרקת קור עם מטרונום · מתיחת קור במכונה
- פלאנק · פלאנק צד · דד באג · ציפור-כלב · הרמת רגליים משכיבה
- המאה משחפוע · רול אפ

**Pilates carry-over:** she has a Pilates background — that's an asset, use it.
Include a set of mat-Pilates core exercises she'll recognize by name (המאה /
hundred, רול אפ, רולאפ, טיזר, סוואן, מאה) and use them as the core block and
cooldown. Cue them with Pilates language — *"נשפי, ומשכי את הטבור פנימה"* —
because that vocabulary is already in her body. This is the one place the app
should feel familiar rather than new.

**Local-language name field:** add an optional `local` string field to the
schema, empty for now. Build a settings screen where she can type in the name
written on the machine at her gym in the local language, per exercise, and have
it display alongside the Hebrew. She fills it in herself as she learns the gym.
Do not attempt to guess the local language.

---

## 8. Plan generator

Rule-based. **No AI, no API, no randomness beyond variety selection.** It must
produce the same quality plan every time, offline, instantly.

Algorithm:

1. Filter the exercise library to what her `equipment` supports, minus
   `disabledExercises`, minus `level > 1`.
2. Choose split by `daysPerWeek`: 2 or 3 → full body every session.
   4 → upper/lower alternating.
3. For each session, fill slots by movement pattern in this order:
   `squat or lunge` → `hinge` → `horizontal push` → `horizontal pull` →
   `vertical push or pull` → `core` → (if time remains) accessory.
4. Number of exercises from `sessionMinutes`: roughly
   `30min → 5 exercises`, `45min → 6-7`, `60min → 8`.
   Estimate each exercise at `sets × (40s work + restSec)` and fit to budget.
5. Sets: 2 for the first two weeks, then 3. Rep range from the exercise.
6. Rotate exercise selection week to week within the same pattern, so she isn't
   doing the identical seven things forever — but keep the anchor lifts stable
   so progression is measurable.
7. Always prepend a 5-minute warmup block and append a 5-minute cooldown/stretch
   block. Both voice-guided.

**Progression logic** (runs when generating the next session's suggestions):
- All sets at top of rep range and feel = `קל` → increase weight one increment
  (2.5kg for machines/barbell-ish, 1–2kg for dumbbells) and drop to bottom of rep range.
- feel = `מאוזר` → same weight, add one rep.
- feel = `מדי כבד` or reps missed → hold weight, or reduce 10% if it happens twice.
- Missed more than 10 days → drop all suggestions 10% and say so kindly.

---

## 9. Visual design

Do not ship a generic dark-mode fitness template with a neon accent. Some direction:

- **Legible at arm's length, in a bright gym, at a glance.** Exercise name should
  be readable when the phone is on the floor and she's standing. That means
  genuinely large type — 32px+ for the current exercise — and high contrast.
- **Light background, not dark.** Gyms are bright; dark mode washes out.
- One accent color used for the primary action only. Everything else neutral.
- Hebrew type: system stack, `-apple-system, "Segoe UI", Arial, sans-serif` —
  no webfonts (offline constraint). Hebrew has no case, so hierarchy must come
  from size and weight, not capitalization.
- Tap targets minimum 56px. She has chalky, sweaty hands and is out of breath.
- The rest-timer countdown is the signature moment — make it the one place the
  design does something memorable. A single large ring that drains. Nothing else
  on screen during rest except the next exercise name.
- Respect `prefers-reduced-motion`.
- Test the RTL layout properly. Mixed Hebrew/English/numbers strings are where
  RTL breaks — wrap English exercise names and weight units in `<bdi>`.

---

## 10. Build phases

**Do not build all of this at once.** Ship each phase working before starting
the next.

**Phase 1 — skeleton and data.**
Single `index.html`, RTL, localStorage layer, full exercise library (40+ with
cues and SVGs), setup flow, gym walkthrough. No voice, no session runner yet.
Verify: she can complete setup and see a generated plan.

**Phase 2 — plan generator.**
Implement §8 fully. Verify by testing edge cases: zero equipment checked
(must still produce a bodyweight/mat plan), only dumbbells, everything checked,
2 days vs 4 days, 30 min vs 60 min.

**Phase 3 — session runner.**
Exercise flow, set logging, rest timer, wake lock, substitute chain, pain flag.
Still silent. Verify the whole workout is completable with the screen only.

**Phase 4 — voice.**
Everything in §6. Test three cases explicitly on a real Android device: Hebrew
voice present, Hebrew voice absent, and airplane mode with a network-only voice
selected. All three will bite you.

**Phase 5 — history, progression, polish.**
Progression logic, history charts, streak, share summary (§2.1), export.

**Phase 5b — ship it.**
`manifest.json`, service worker with versioned caching and the update strategy
from §2.1, deploy to GitHub Pages. Then the real test: install it on an Android
phone, **turn on airplane mode**, and complete a full workout start to finish.
If anything breaks, the offline layer is wrong and nothing else matters yet.

**Phase 6 — the real test.**
Take the phone, put it on the floor, and run through an entire session standing
up, out loud, at arm's length. Everything that is annoying will become obvious
in about four minutes. Fix that list.

---

## 11. Things that will go wrong — handle them

- Speech silently fails without a user gesture — prime on the start-workout tap.
- Voices array is empty on first call — listen for `voiceschanged`.
- A network-only Hebrew TTS voice gets selected — app goes mute in the gym.
  Filter for `localService` first.
- Service worker serves a stale broken build with no escape hatch — versioned
  caches, background update check, apply on next open, plus a "force update"
  button buried in settings.
- Screen sleeps mid-rest — Wake Lock + `visibilitychange` re-acquire + fallback.
- She backgrounds the app mid-session — persist session state on every action so
  reopening resumes exactly where she left off. Do not lose a workout. Ever.
- Phone rotates — lock the layout to portrait behavior; don't reflow.
- Local-language machine names she can't match — the physical descriptions in
  §5.2 are the mitigation. Make them genuinely descriptive.
- RTL number and unit rendering — `<bdi>`, and test with 12.5 ק"ג strings.
- Feminine conjugation errors throughout the Hebrew — audit every string.

---

## 12. Out of scope

No accounts, no sync, no social, no nutrition, no calorie tracking, no weight
tracking, no body measurements, no photos, no AI generation, no video. If a
feature needs the internet at runtime, it is out of scope.
