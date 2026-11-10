---
name: openutau
description: Make the best-sounding sung vocals in OpenUtau (English and Japanese lyrics) through the openutau MCP server - lyrics, melody, singer and phonemizer choice, timing, pitch, expression, checks and report. Use for any OpenUtau / UTAU / vocal synthesis task. / OpenUtau MCP で最高品質の歌声を作るための手順とルール。
---

# OpenUtau vocals / OpenUtau 歌声制作

Follow these rules every time. Defaults are starting points; the user's ear wins.
If a `voicebanks.md` file sits next to this one, read it first: it lists the user's singers, phonemizers,
voice colors and credit requirements.

Basics: 480 ticks = quarter note (1920 = 4/4 bar, 240 = 8th, 120 = 16th, 60 = 32nd). Note positions are relative
to their part. Pitch: MIDI number or name, C4 = 60. "part" counts voice parts only. Every live edit is one undo step.
Never pass `force=true` unless the user agreed to lose unsaved work.

## 1. Workflow (always in this order) / 手順

1. **Start.** `openutau_status`; launch if needed. Before any edit, `get_project` and confirm `file_path` is the
   project you expect (a live project has reset to blank before: reopen the saved file with `open_project`).
2. **Source.** Never guess or "remember" a melody. Use a melody the user gave, the user's own song, or a
   public-domain source you can cite (traditional tune from a public-domain score, e.g. IMSLP or Mutopia).
   No source: ask. Write the source in the report.
3. **Lyrics first, approval before building.** Show a table per phrase: source lyric | target lyric | syllables per
   note (one cell per note, `+` for held syllables) | note count. Counts must match the melody's notes per phrase.
   Wait for the user's OK. Do not build before it.
4. **Singer + phonemizer.** Pick from `voicebanks.md` (or `list_singers`), then confirm with
   `rank_phonemizers(singer, text=<the approved lyrics>)`. Use `best`; never use a phonemizer scoring under ~0.95.
   A tag that is not installed (e.g. "EN CVVC") does not exist: do not ask for it, pick from the ranking.
   A wrong singer/phonemizer pair renders as silence, hums or garbled sounds.
5. **Build in stages, save after each:**
   a. Notes: `new_project` (only if the user agrees) → `set_tempo` → `set_time_signature` → track setup →
      `add_part` → `add_melody(part, "A4:1 A4:1 B4:2 r:1 ...")` → `fit_part`. Save.
   b. Lyrics: `set_lyrics` per phrase, then `list_phonemes`: every phoneme must have `has_oto: true`. Save.
   c. Pitch and expression (sections 5–6). Save.
   Save to `Documents\OpenUtau\Projects\<song>.ustx` unless the user gives a path; never overwrite an earlier
   version — use `-v2`, `-v3`.
6. **Self-check** (section 9), then **report** (section 10).

Do not render/export audio unless asked. Do not play audio without being asked.

## 2. Singers and phonemizers / 歌手と音素化器

- Use the table in `voicebanks.md` when present; trust `rank_phonemizers` over any table if they disagree, and say so.
- Classic UTAU banks: phonemizer must match the bank's sample style (CV/VCV/CVVC Japanese, ARPAsing, VCCV,
  X-SAMPA, C+V English). DiffSinger banks: use a `DIFFS <lang>` phonemizer and the DiffSinger renderer;
  classic phonemizers do not work on them.
  A DiffSinger bank also needs the vocoder named in its `dsconfig.yaml` (`vocoder:`), either in the bank's
  own `dsvocoder` folder or in `Documents\OpenUtau\Dependencies`; if it is missing the track renders silent,
  so tell the user instead of building on it.
- Voice colors (subbanks): `get_project` → track `voice_colors`; set with
  `set_note_expression(part, "clr", <index in voice_colors>, indices)`. Do not type color suffixes into lyrics.
- English lyrics on a Japanese-only bank: `ENtoJAPhonemizer` ("EN to JA"), and expect an accent.

## 3. English lyric rules / 英語の歌詞

- Whole word on its first note; `+` on each extra note of that word (`beau-ti-ful` → `beautiful + +`).
- One vowel sound per note. Never put two syllables on one note.
- Word endings: most English UTAU banks sing a word's final consonants as a transition into the NEXT note.
  So after a consonant-ending word ("mist", "cloud", "and") put a rest or a note of at least an 8th; avoid
  final clusters (-st, -nd, -ts, -ks) before short notes.
- Vowel-initial words ("all", "it", "is", "as", "eyes") blur into the previous word. Prefer consonant-initial
  words, especially on short notes; if you must, put a short rest before them.
- High or long notes: open vowels (ah, oh, ay, "aw"). Avoid "ee" and "ih" above about C5 and on long holds.
- Short notes (8th or less): one-syllable, simple words ("the", "to", "go"), not "eyes can" or "us and".
- A word that sounds mushy: hyphenate it by hand, or swap a synonym with the same meaning and stress.
- Check `list_phonemes`: a word whose phonemes look wrong or are missing its ending needs rewording.

## 4. Japanese lyric rules / 日本語の歌詞

- One mora per note: `きゃ` = 1 note, `っ` = its own note, `ー` = a `+` note holding the previous vowel.
- Prefer kana; kanji are converted with pykakasi but readings can be wrong — check the split first.
- Particles は/へ/を: write as sung (わ/え/お) when the phonemizer reads them literally; confirm with `list_phonemes`.
- Do not put `っ` on a long note; give it a short note or merge into the previous note's end.

## 5. Timing / タイミング

- Put note starts exactly on the beat. OpenUtau already starts each consonant early using the bank's
  preutterance, so the vowel lands on the beat. Do not shift notes earlier by hand.
- Leave a gap between phrases: at least an 8th (240) at slow/medium tempos, 16th (120) minimum when fast.
  Never run phrases back-to-back. The gap is also where breaths go.
- Minimum note length: 16th (120) below ~100 BPM, 32nd (60) at any tempo. Merge or re-rhythm anything shorter.
- No overlapping notes and no zero/negative lengths.

## 6. Pitch and expression defaults / ピッチと表情

- Portamento: keep OpenUtau's default short slide between notes. Bigger slides only for emotional moments.
- Pitch curves (`set_pitch(part, indices, points, snap_first)`; x = ms from note start, y = tenths of a semitone,
  `get`/check with `list_notes` → `pitch`). Use sparingly, a few notes per phrase:
  - Scoop into a phrase's first or an emphasised note (`snap_first=false`): `[{x:-40,y:-20},{x:60,y:0}]`.
  - Fall/drift at a phrase end, last ~30% of the note: `[{x:-40,y:0},{x:40,y:0},{x:<70% of ms>,y:0},
    {x:<note ms>,y:-30,shape:"i"}]` (note ms = duration ticks × 60000 / (480 × BPM)).
  - Small overshoot on an upward leap: `[{x:-40,y:0},{x:60,y:5},{x:140,y:0}]`.
  Keep |y| ≤ 30 (3 semitones) except for deliberate effects. Normal notes: leave the default points.
- Vibrato (`edit_notes` → `vibrato`): only on notes ≥ 1 beat (480). Defaults: `length` 40–60 (starts partway in),
  `depth` 15–25 cents, `period` 170–200 ms, `in` 20, `out` 20. Never on short notes.
- Phrase volume (`set_note_expression "vol"`, default 100): rise and fall across the phrase, e.g. first note 90,
  peak 105–110, last note 85. Soften phrase endings.
- Consonant clarity (`vel`, default 100): 110–130 for English words that get lost; leave Japanese at 100.
- Breaths: put a breath before phrases where the bank has one. Find it with `search_oto(voicebank, "吸")` or
  `"br"` / `"breath"`; place a short note (8th) in the gap before the phrase with that lyric, then confirm
  `has_oto: true` in `list_phonemes`. No breath sample: leave the gap empty.
- Breathiness/gender (`bre`, `gen`): small values only (bre ≤ 30, gen within ±15).
- Expression curves (`set_curve(part, abbr, [[tick, value], ...])`, part-relative ticks, straight lines between
  points; `get_curve` to read, `clear_curve` to reset): `dyn` dynamics, and on DiffSinger banks `tenc` tension,
  `brec` breathiness, `genc` gender, `voic` voicing. Gentle shapes per phrase: `dyn` 0 → peak 0 to +20 → -40 at the
  phrase end; `tenc` 0–30 only at climaxes; `brec` 10–30 on soft or ending notes. Stay within about a third of each
  curve's range (`get_curve` gives min/max); extreme values sound robotic.
- New voicebank installed while OpenUtau is open: `refresh_singers` instead of restarting.
- Range: use the range in the bank's readme / `voicebanks.md`. Unknown: flag any note far outside the rest of the
  melody (more than ~an octave from its middle) and ask before keeping it.

## 7. Musical quality / 音楽性

- Stress: stressed syllables on strong beats and on longer or higher notes; unstressed ones on weak beats and
  short notes. Japanese: keep pitch accent natural where the melody allows.
- Motifs: when a motif returns (the user's game uses leitmotifs), keep its rhythm and contour recognizable;
  change lyrics, not shape.
- When the agent writes or adapts melody: mostly stepwise, occasional leaps, a leap followed by a step back in
  the other direction, phrase endings on stable notes.

## 8. Safety and licensing / 安全とライセンス

- Never edit, move or delete voicebank / singer files or OpenUtau settings.
- Projects go to `Documents\OpenUtau\Projects` (or the user's path). Never overwrite the user's files.
- Only public-domain material or the user's own songs. No copyrighted lyrics or melodies, including translations
  of copyrighted lyrics. Traditional tunes are fine, but a modern arrangement or engraved score can be copyrighted:
  cite the public-domain source.
- Note every used voicebank's credit and licence terms in the report (see `voicebanks.md`). If the user's use
  may be commercial and a bank is non-commercial only, say so plainly.

## 9. Self-check before reporting / 報告前の確認

Run `list_notes` and `list_phonemes` for every part and confirm:
- every note has a lyric; `+` notes only follow a real syllable;
- no overlaps (`position + duration` ≤ next `position`), no notes shorter than the minimum, no zero lengths;
- a gap between every phrase;
- every phoneme `has_oto: true`; phonemizer is the `rank_phonemizers` best for that singer;
- vibrato only on long notes; expression values inside the defaults above;
- parts trimmed (`fit_part`); project saved; `get_project.saved` is true.
Fix what you can; list what you can't.

## 10. Report / 報告

1. What was built: song, source (with link), tempo/key, tracks (singer, phonemizer, score), file path(s).
2. Lyrics used (final table) and any words changed during the build, with why.
3. Tool problems and workarounds.
4. **Listen here first:** the 3 spots most likely to sound off (bar/beat, lyric, why — e.g. vowel-initial word
   on an 8th, high "ee", consonant cluster before a short note).
5. Credits and licence notes for every voicebank used.
6. What you did not do or check (e.g. "did not listen", "pitch curves left default").
