---
name: openutau
description: Compose and edit singing in OpenUtau (English and Japanese lyrics) through the openutau MCP server - write melodies, set lyrics, choose singers and phonemizers, check pronunciation, export WAV. / OpenUtau MCP サーバーで歌声（日本語・英語の歌詞）を作成・編集し、WAV に書き出します。
---

# OpenUtau workflows / OpenUtau ワークフロー

## Ground rules / 基本

- 480 ticks = quarter note, 1920 = one 4/4 bar. Note positions are relative to their part.
  / 四分音符 = 480 ティック、4/4 の1小節 = 1920。音符の位置はパート相対。
- Pitch: MIDI number or name, C4 = 60. / 音高は MIDI 番号か音名（C4 = 60）。
- "part" counts voice parts only; "note" is the index inside the part, sorted by position.
  / part はボイスパートだけの番号、note はパート内の位置順の番号。
- Every live edit is one undo step; save explicitly with `save_project`.
  / ライブ編集は1回 = 取り消し1回。保存は `save_project` で明示的に。
- Never pass `force=true` to `open_project` / `new_project` / `close_openutau` unless the user agreed to lose
  unsaved work. / ユーザーの了承なしに `force=true` を使わないこと。

## 1. Start / 開始

1. `openutau_status`. If `bridge` is false, follow `hint`: launch with `launch_openutau`, or install the plugin and
   restart OpenUtau. / `bridge` が false なら `hint` に従う（`launch_openutau`、またはプラグインを入れて再起動）。
2. `list_singers` → pick a singer id. `list_phonemizers` if unsure. / 歌手 ID を選ぶ。

## 2. New song, live / 新曲（ライブ）

1. `new_project` → `set_tempo(bpm)` → `set_time_signature` if not 4/4.
2. `update_track(track=0, singer=..., phonemizer=...)` (or `add_track`). Choose the phonemizer for the bank:
   Japanese UTAU → `JapanesePresampPhonemizer`; English X-SAMPA → `EnXSampaPhonemizer`;
   ARPAsing → `ArpasingPhonemizer`; VCCV → `EnglishVCCVPhonemizer`; English words on a Japanese bank → `ENtoJAPhonemizer`.
   / 音源に合う音素化器を選ぶ（上記）。
3. `add_part(track=0, position=0, duration=7680)`.
4. Melody + lyrics in one call: `assign_lyrics(part, text, start_tick, durations, tones)`.
   Durations/tones can be lists; the last value repeats. Preview with `split_lyrics` first if the note count matters.
   / `assign_lyrics` でメロディと歌詞を一度に。音符数が重要なら先に `split_lyrics` で確認。
5. `list_phonemes(part)` — any `has_oto: false` means that sound is missing from the voicebank: change the lyric,
   phonemizer or singer. / `has_oto: false` があれば歌詞・音素化器・歌手を見直す。
6. `play(tick=0)` / `stop`, then `save_project(path)` and `export_wav(path)`.

Melody and lyrics together: `add_melody(part, melody="A4:1 A4:1 B4:2 r:1", lyrics="さくら")` (beats are quarter notes,
r = rest; one lyric per sounding note). Then `fit_part(part)` to trim the part to the last bar.
Choosing a phonemizer: `rank_phonemizers(singer)` tries every installed one on sample lyrics and ranks them by how many
sounds the voicebank has; use `best`. Only installed phonemizers exist (there is no "EN CVVC" in stock OpenUtau).
/ メロディと歌詞は add_melody で一度に入力し、fit_part でパートの長さを合わせます。

## 3. Edit an existing song / 既存曲の編集

1. `open_project(path)` → `get_project` → `list_notes(part)`.
2. Change notes in place with `edit_notes` (keeps pitch curves). Replace words with `set_lyrics(part, text, start_index)`.
   Delete with `delete_notes`. / `edit_notes` はピッチ曲線を保ったまま編集。歌詞の差し替えは `set_lyrics`。
3. Expressions: `list_expressions`, then `set_note_expression(part, "vel", 130, indices)`. `value: null` resets.
4. Made a mistake? `undo`. / 間違えたら `undo`。

## 4. Lyrics / 歌詞

- Japanese: one mora per note (きゃ = 1 note; っ is a separate note; ー becomes a "+" note holding the previous vowel). Kanji → hiragana if pykakasi is installed;
  otherwise write kana. Romaji works when separated by spaces.
  / 日本語は1音符1モーラ。漢字は pykakasi があればひらがなに。ローマ字はスペース区切り。
- English: one word per note. For a word over several notes write hyphens: `beau-ti-ful` → `beautiful + +`.
  / 英語は1音符1単語。複数音符にまたがる単語はハイフンで区切る。

## 5. Without OpenUtau running / OpenUtau なしで

`ustx_create(path, bpm, singer)` → `ustx_add_voice_part` → `ustx_assign_lyrics` (or `ustx_add_notes`) →
`ustx_set_vibrato` → open later with `launch_openutau(project_path=path)`.
Classic UTAU: `ust_import` (.ust → .ustx), `ust_export` (.ustx part → Shift_JIS .ust).
Voicebank checks: `list_voicebanks`, `search_oto(voicebank, "か")`.
/ OpenUtau を起動せずに .ustx を作成・編集し、後で `launch_openutau` で開けます。UTAU の .ust も変換できます。
