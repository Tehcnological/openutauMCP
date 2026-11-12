---
name: openutau
description: Make the best-sounding sung vocals in OpenUtau (English and Japanese lyrics) through the openutau MCP server - lyrics, melody, singer and phonemizer choice, timing, pitch, expression, A/B comparisons across voicebanks, harmony/ensembles, audio checks and report. Use for any OpenUtau / UTAU / DiffSinger / vocal synthesis task. / OpenUtau MCP で最高品質の歌声を作るための手順とルール。
---

# OpenUtau vocals / OpenUtau 歌声制作

Follow these rules every time. Defaults are starting points; the user's ear wins.
If a `voicebanks.md` file sits next to this one, read it first: it lists the user's singers, phonemizers,
voice colors, comfortable registers, per-bank findings and credit requirements. `mix_stems.py` (also next to this
file) aligns, levels, pans and mixes WAV stems (section 14).

Basics: 480 ticks = quarter note (1920 = 4/4 bar, 240 = 8th, 120 = 16th, 60 = 32nd). Note positions are relative
to their part. Pitch: MIDI number or name, C4 = 60. "part" counts voice parts only. Every live edit is one undo step.
Never pass `force=true` unless the user agreed to lose unsaved work.

## 1. Workflow (always in this order) / 手順

1. **Start.** `openutau_status`; launch if needed. Before any edit, `get_project` and confirm `file_path` is the
   project you expect. The live project can be replaced under you (it has reset to blank, and it has been
   swapped for an unrelated saved project mid-build, cause unknown): see section 11 to detect and recover.
2. **Source.** Never guess or "remember" a melody. Use a melody the user gave (their JSON/MIDI/notes are the
   source of truth: keep bpm, pitches and note lengths exactly), the user's own song, or a public-domain source
   you can cite (traditional tune from a public-domain score, e.g. IMSLP or Mutopia). No source: ask. If a tune
   written from memory was accepted by the user for a test, still say in the report that it is unverified against
   a score. Write the source in the report.
3. **Lyrics first, approval before building.** Show a table per phrase: source lyric | target lyric | syllables per
   note (one cell per note, `+` for held syllables) | note count. Counts must match the melody's notes per phrase.
   Wait for the user's OK. Do not build before it.
   Exception: when the user already supplied the exact lyrics and note list and said to reuse them unchanged,
   build straight away and put the table in the report instead (the mapping is mechanical: `word + +`).
4. **Singer + phonemizer.** Pick from `voicebanks.md` (or `list_singers`), then confirm with
   `rank_phonemizers(singer, text=<the approved lyrics>)`. Use `best`; never use a phonemizer scoring under ~0.95.
   Rank on the user's real lyrics, not the built-in samples: the winner can differ from the bank's default
   phonemizer (a C+V English bank scored 1.00 with EN ARPA but only 0.90 with its own default on one test). Say so
   in the report. A tag that is not installed (e.g. "EN CVVC") does not exist: do not ask for it, pick from the
   ranking. A wrong singer/phonemizer pair renders as silence, hums or garbled sounds.
5. **Build in stages, save after each:**
   a. Notes: `new_project` (only if the user agrees) → `set_tempo` → `set_time_signature` → track setup →
      `add_part` → `add_melody(part, "A4:1 A4:1 B4:2 r:1 ...")` → `fit_part`. Save.
   b. Lyrics: `set_lyrics` per phrase, then `list_phonemes`: every phoneme must have `has_oto: true` (classic
      banks; see section 9 for DiffSinger). Save.
   c. Pitch and expression (sections 5–6). Save.
   Save to `Documents\OpenUtau\Projects\<song>.ustx` unless the user gives a path; never overwrite an earlier
   version — use `-v2`, `-v3`. Save right after the notes exist (before the long expression pass).
   **Send OpenUtau MCP calls one at a time, never several edits in the same message** (section 11).
6. **Self-check** (section 9), then **report** (section 10).

Do not render/export audio unless asked (when the user asks for renders, use sections 11–13). Do not play audio
without being asked.

## 2. Singers and phonemizers / 歌手と音素化器

- Use the table in `voicebanks.md` when present; trust `rank_phonemizers` over any table if they disagree, and say so.
- Classic UTAU banks: phonemizer must match the bank's sample style (CV/VCV/CVVC Japanese, ARPAsing, VCCV,
  X-SAMPA, C+V English). DiffSinger banks: use a `DIFFS <lang>` phonemizer and the DiffSinger renderer;
  classic phonemizers do not work on them.
  A DiffSinger bank also needs the vocoder named in its `dsconfig.yaml` (`vocoder:`), either in the bank's
  own `dsvocoder` folder or in `Documents\OpenUtau\Dependencies`; if it is missing the track renders silent,
  so tell the user instead of building on it. Check with PowerShell: `Select-String -LiteralPath
  <bank>\dsconfig.yaml -Pattern vocoder`, then look in `<bank>\dsvocoder` and the Dependencies folder (use
  `-LiteralPath` when a path contains `[ ]`).
- DiffSinger voices have a comfortable register for **sustained** notes. Outside it they get choppy (too low) or
  shrill (too high); short passing notes tolerate more. If a melody's long notes fall outside a voice's window,
  change those notes' pitch or the track's octave rather than adding effects.
- Voice colors (subbanks): `get_project` → track `voice_colors`; set with
  `set_note_expression(part, "clr", <index in voice_colors>, indices)`. Do not type color suffixes into lyrics.
  After swapping a track's singer, `voice_colors` still shows the old bank's list: `save_project` (to a new name)
  refreshes it, then set `clr`. Read the index from the refreshed list.
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
  `get`/check with `list_notes` → `pitch`). Use sparingly, a few notes per phrase, and **audition before keeping**:
  - Scoop into a phrase's first or an emphasised note (`snap_first=false`): `[{x:-40,y:-20},{x:60,y:0}]`.
  - Fall/drift at a phrase end, last ~30% of the note: `[{x:-40,y:0},{x:40,y:0},{x:<70% of ms>,y:0},
    {x:<note ms>,y:-30,shape:"i"}]` (note ms = duration ticks × 60000 / (480 × BPM)).
  - Small overshoot on an upward leap: `[{x:-40,y:0},{x:60,y:5},{x:140,y:0}]`.
  Keep |y| ≤ 30 (3 semitones) except for deliberate effects. Normal notes: leave the default points.
  On DiffSinger banks the scoop and the phrase-end fall sounded wrong in testing ("the trailoff and the change in
  pitch"): leave them off unless the user asks, and A/B them (section 12). To remove one:
  `set_pitch(part, indices, [{x:-40,y:0},{x:40,y:0}], snap_first=true)` restores the plain default slide.
- Vibrato (`edit_notes` → `vibrato`): only on notes ≥ 1 beat (480); in practice on held notes of ≥ 2 beats in the
  middle of a phrase. Defaults: `length` 40–60 (starts partway in), `depth` 15–25 cents, `period` 170–200 ms,
  `in` 20, `out` 20. Never on short notes. Avoid it on the last held note of a phrase unless asked (users asked for
  it removed there). `vibrato: {length: 0}` turns it off for a note.
- Phrase volume (`set_note_expression "vol"`, default 100): rise and fall across the phrase, e.g. peak 105–110 on
  the stressed words. `value=null` resets a note to default. A volume dip on the last note, a switch to a Soft voice
  color and a breathiness ramp at phrase ends all sounded odd on some DiffSinger voices: audition any soft ending
  with an A/B before applying it everywhere.
- Consonant clarity (`vel`, default 100): 110–130 for English words that get lost; leave Japanese at 100.
- Breaths: put a breath before phrases where the bank has one. Find it with `search_oto(voicebank, "吸")` or
  `"br"` / `"breath"`; place a short note (8th) in the gap before the phrase with that lyric, then confirm
  `has_oto: true` in `list_phonemes`. No breath sample: leave the gap empty.
- Breathiness/gender (`bre`, `gen`): small values only (bre ≤ 30, gen within ±15).
- Expression curves (`set_curve(part, abbr, [[tick, value], ...])`, part-relative ticks, straight lines between
  points; `get_curve` to read, `clear_curve` to reset): `dyn` dynamics, and on DiffSinger banks `tenc` tension,
  `brec` breathiness, `genc` gender, `voic` voicing. Gentle shapes per phrase: `dyn` 0 → peak +15 to +20 → back to 0
  at the phrase end (a -40 drop at the end sounded odd on some voices); `tenc` 0–30 only at climaxes; `brec` 10–30
  on genuinely soft passages. Observed ranges on 0.1.576: `dyn` -240..120, `brec` -100..100. Stay within about a
  third of each curve's range (`get_curve` gives min/max); extreme values sound robotic.
- "More emotion" for a DiffSinger voice that sounds flat is mostly: `vol` peaks on stressed words (105), a gentle
  `dyn` swell across each phrase, vibrato on mid-phrase held notes, and small `brec` under soft passages. Apply it
  per track, then re-listen or A/B before adding more.
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
- every phoneme `has_oto: true` **on classic banks**. On DiffSinger banks `has_oto` is false and `duration` 0 for
  almost everything (there are no oto samples and durations are predicted at render time): read the phoneme
  *sequence* instead, e.g. `hello` → `en/hh en/ah en/l en/ow`. On classic banks a false `has_oto` can also be a stale
  flag, so trust `rank_phonemizers` and the audio over it, and say which you relied on;
  phonemizer is the `rank_phonemizers` best for that singer;
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
7. Render times: `export_wav` returns almost instantly (about 0.1 s even for DiffSinger) because OpenUtau pre-renders
   phrases in the background while you edit. Do not quote that as the render time; say it is not measurable.

## 11. MCP tool behaviour and gotchas / ツールの癖

Observed on OpenUtau 0.1.576 with this MCP server:

- **One call at a time.** Edits sent in the same message collide: `OpenUtau is in the middle of an edit (open undo
  group)` and a `NullReferenceException` from `fit_part`. A stuck undo group blocks every later edit. Recovery:
  `save_project` (saving still works), then `open_project` on that saved file (without `force`).
- **The live project can be replaced while you work** (seen twice: an unrelated saved project, then an earlier
  version of the same song, replaced the open one; cause not found). Signs: a summary whose `file_path`, tempo or
  tracks are not yours, or `export_wav` returning a file named after a track you did not create. Rules: save to a
  fresh file name early; read `file_path`/tracks in the summary that `save_project`, `fit_part`, `add_part` and
  `update_track` return before trusting any silent edit; if it changed, stop, delete any wrong export you made,
  `open_project` your saved file (no `force`) and redo only the lost edits. Unsaved work in the swapped-out project
  is gone, so save often. Never `save_project` with a path while the wrong project is live: it writes that project
  under your file name.
- `fit_part` is needed after almost every edit: `add_melody` pads a bar, `edit_notes` can grow the part by a bar,
  and `import_tracks` pads a beat. A longer part makes a longer WAV.
- `add_melody` takes MIDI numbers (`62:3 59:3 r:1 ...`) as well as names, lowercases lyrics and accepts `+` and
  apostrophes (`I'm`).
- `export_wav(path, per_track=true)` writes `<path-stem>_<trackname>.wav` for **every** track each time, so name
  tracks in lower case to get predictable files (`line_lem.wav`). `per_track=false` writes one mixdown. Per-track
  export temporarily mutes the other tracks and may leave them muted in the live project: re-check `mute` before
  building on it. Output was 44.1 kHz mono 16-bit for DiffSinger and classic banks alike.
- `set_note_expression(value=null)` resets; `clear_curve` resets a curve; `edit_notes(vibrato={length:0})` turns
  vibrato off; `set_pitch(..., [{x:-40,y:0},{x:40,y:0}], snap_first=true)` restores the default slide. `edit_notes`
  takes several notes per call (e.g. re-pitch a whole 20-note part in one call), and `tone` is an absolute MIDI number.
- `remove_track` renumbers the tracks after it: remove the higher index first.
- `import_tracks(path, import_tempo=false)` imports the tracks *of another project file* into the open one. Imported
  parts keep notes, lyrics, curves and note expressions.
- `list_phonemes` on a DiffSinger part shows `has_oto: false` and `duration: 0` for everything (see section 9).
- Autosaves (`*-autosave.ustx`) appear next to projects; ignore them.

## 12. Cloning a part across voicebanks, and A/B variants / 複製とA/B比較

To compare banks or variants of one phrase:

1. Build **one** track completely (notes, lyrics, expression), `save_project` as `<song>-base.ustx`.
2. `import_tracks(<base>)` once per extra copy. All copies share notes and expression.
3. `update_track(track=n, singer=<id>, phonemizer="DIFFS EN", name="<lowercase name>")` for each copy. Then
   `save_project` to a new name (refreshes `voice_colors`) and apply per-bank things such as `clr`.
4. `fit_part` the parts that grew, save as the next `-vN`, `export_wav(per_track=true)` into the output folder.
   Name any reference renders from other tools to match: `<line>_<who>.wav`.
5. For an A/B of a single idea (e.g. "the ending sounds weird"), do not guess: make 2-3 tracks that differ in exactly
   one thing, name them for what differs (`A_low`, `B_mid`, `C_high`), export to a `*_variants` folder and ask
   which one. Tracks you do not need can be removed from a *working copy* (never from the saved version) so only the
   variants render. Apply the winner to the real projects and say it was the user's pick.
6. Never overwrite earlier projects; every change is `-v2`, `-v3`... Re-exporting the audio into the same output
   folder (overwriting the previous WAVs) is fine when the user is iterating on them, but say so.

When the user says a voice is "too low/too high/weird/choppy/rough" on named words, first check what is actually
sung (section 13) before changing it: the note may be exactly as written (just at the edge of the voice's range) and
the real cause can be an ending effect (color, breath ramp, volume dip, pitch fall), not the pitch.

## 13. Checking audio without listening / 聴かずに確認

Never claim a render "sounds good". You can verify, and should state exactly what was verified:

- Use `python -I` (isolated) with the stdlib `wave`/`struct` modules (Python 3.11 also has `audioop`).
- Per file: duration, sample rate, peak, count of 1-second windows below 0.02 (silence), clipped samples.
  A 1/N quiet window at the tail is normal.
- **Pitch check by autocorrelation** on a held note: read 0.15 s starting at `beat*60/bpm + 0.4 s` (0.4 s into the
  note), search lags for 75-1300 Hz, convert to a note name. This confirmed octave moves and that each harmony
  voice sang its assigned note. Zero-crossing counts are too noisy to use.
- Confirm two renders are identical (or different) with `Get-FileHash -Algorithm MD5`.
- Loudness differs a lot between banks (peaks from ~0.2 to ~0.8 were seen): report it, and match levels (RMS) before
  an A/B or a mix.
- Reference renders from other tools can disappear between turns. Regenerate from the saved source (if the tool is
  deterministic) instead of hunting for the old file.

## 14. Ensembles and harmony / 重唱

1. **Unison/octave quartet first** if asked for "a quartet" with no detail: layer the existing stems with
   `mix_stems.py`. If the user then asks to "harmonize", write real parts.
2. Pick key and a simple chord per melody note or bar; each part sings **chord tones** (the melody tone is always a
   chord tone or a passing note), with the same rhythm and lyrics as the melody (block harmony). Keep voice-leading
   stepwise where possible and avoid a part sitting a semitone from the melody.
3. Give each part to the voice whose **comfortable sustained register** (`voicebanks.md`) it fits. A voice that is
   weak when low must stay above its floor, so put it *above* the melody (upper harmony) where the melody dips, and
   constrain its notes to its window. Melody to the voice that is happy at the melody's register.
4. Re-pitch with `edit_notes` (all notes of a part in one call), `fit_part`, save as a new `-harmony` project and
   export per track. Another renderer can supply a part (e.g. a bass line): render it from the same notes, and
   expect a different lead-in and sample rate.
5. Mix with `mix_stems.py out.wav "<stem>|<pan>|<weight>[|align]" ...`. It resamples to 44.1 kHz, RMS-matches each
   stem, applies the weight, pans with an equal-power law and peak-normalises to ~0.9 as 16-bit stereo. Mark a stem
   from another tool `align` so it is shifted onto the OpenUtau voices' timeline by envelope cross-correlation
   (one such renderer started ~0.3 s late). Defaults that worked: melody weight 1.2, others 0.85–0.95; SATB spread
   bass -0.5, tenor -0.2, upper harmony +0.25, melody +0.5.
6. Verify with section 13 (pitch of each voice on a few notes) and report the part table (voice / notes / register /
   pan).
