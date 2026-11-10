"""OpenUtau MCP server (stdio). Every tool description and error is English, then Japanese."""

import functools
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from . import app, bridge, music, ust, ustx, voicebanks
from . import lyrics as lyric_text
from .errors import OpenUtauError

INSTRUCTIONS = """\
Control OpenUtau (singing synthesis) in English or Japanese.
1. Call openutau_status first. Live tools need OpenUtau running with the OpenUtauMcp plugin (the "bridge").
   If it is not running, call launch_openutau. ustx_* / ust_* / voicebank tools work with OpenUtau closed.
2. Time is in ticks: 480 ticks = one quarter note (1920 = one 4/4 bar). Note positions are relative to their part.
3. Pitch: MIDI number or name. C4 = 60 (middle C), A4 = 69, C#4/Db4 = 61, C-1 = 0.
4. Indexes: "track" = track number; "part" = index among voice parts only; "note" = index in the part, sorted by position.
5. Lyrics (assign_lyrics / set_lyrics / ustx_assign_lyrics): Japanese = one mora per note (きゃ is one note; っ is its own note;
   ー becomes a "+" note that holds the previous vowel; punctuation is dropped; kanji become hiragana when pykakasi is installed). English = one word per
   note; write hyphens for syllables ("hel-lo") and the extra syllables become "+" extender notes.
6. Phonemizer by voicebank: Japanese UTAU bank -> OpenUtau.Plugin.Builtin.JapanesePresampPhonemizer ("JA VCV & CVVC");
   English ARPAsing bank -> ArpasingPhonemizer ("EN ARPA"); English VCCV bank -> EnglishVCCVPhonemizer ("EN VCCV");
   English X-SAMPA bank -> EnXSampaPhonemizer ("EN X-SAMPA");
   English lyrics on a Japanese bank -> ENtoJAPhonemizer ("EN to JA"). Check list_phonemes: has_oto=false means the
   voicebank has no sample for that phoneme.
7. Each live edit is one undo step (undo / redo). Save with save_project.

OpenUtau（歌声合成）を英語・日本語で操作します。
1. まず openutau_status を呼んでください。ライブ操作には OpenUtauMcp プラグイン（ブリッジ）入りの OpenUtau が必要です。
   起動していなければ launch_openutau。ustx_* / ust_* / 音源ツールは OpenUtau を閉じたままでも使えます。
2. 時間はティック単位：四分音符 = 480（4/4 の1小節 = 1920）。音符の位置はパートの先頭からの相対値です。
3. 音高は MIDI 番号か音名：C4 = 60（中央ド）、A4 = 69、C#4/Db4 = 61、C-1 = 0。
4. 番号：track はトラック番号、part はボイスパートだけを数えた番号、note はパート内の位置順の番号です。
5. 歌詞：日本語は1音符1モーラ（「きゃ」で1音符、「っ」は単独の音符、「ー」は前の母音を伸ばす「+」音符、句読点は除去、pykakasi があれば漢字をひらがなに）。
   英語は1音符1単語。音節はハイフンで区切ると（hel-lo）、残りの音節が「+」の延長音符になります。
6. 音源に合う音素化器：日本語 UTAU 音源 → JapanesePresampPhonemizer、英語 ARPAsing → ArpasingPhonemizer、
   英語 VCCV → EnglishVCCVPhonemizer、英語 X-SAMPA→ EnXSampaPhonemizer、
   日本語音源で英語歌詞 → ENtoJAPhonemizer。list_phonemes の has_oto=false は音源に該当サンプルがないことを示します。
7. ライブ編集は1回の呼び出しが1回の取り消し単位です（undo / redo）。保存は save_project。
"""

mcp = FastMCP("openutau", instructions=INSTRUCTIONS, log_level="WARNING")


def _tool():
    """mcp.tool() that turns unexpected exceptions into bilingual errors."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except OpenUtauError:
                raise
            except Exception as e:  # noqa: BLE001 - surface anything else in both languages
                raise OpenUtauError(f"{type(e).__name__}: {e}", f"予期しないエラー {type(e).__name__}: {e}") from e
        return mcp.tool()(wrapper)
    return deco

Pitch = int | str
_PITCH_DESC = "MIDI number or note name (C4 = 60). / MIDI 番号または音名（C4 = 60）"


class NoteIn(BaseModel):
    position: int = Field(description="Start tick, relative to the part. / パート先頭からの開始ティック")
    duration: int = Field(description="Length in ticks (480 = quarter note). / 長さ（ティック、480 = 四分音符）")
    tone: Pitch = Field(description=_PITCH_DESC)
    lyric: str = Field("a", description="Lyric. / 歌詞")


class Vibrato(BaseModel):
    length: float | None = Field(None, description="Percent of note length (0 = off). / 音符長に対する割合（0 で無効）")
    period: float | None = Field(None, description="Period in ms. / 周期（ミリ秒）")
    depth: float | None = Field(None, description="Depth in cents. / 深さ（セント）")
    in_: float | None = Field(None, alias="in", description="Fade-in percent. / フェードイン（%）")
    out: float | None = Field(None, description="Fade-out percent. / フェードアウト（%）")
    shift: float | None = Field(None, description="Phase shift percent. / 位相シフト（%）")
    drift: float | None = Field(None, description="Pitch drift (-100..100). / ドリフト（-100〜100）")

    def values(self) -> dict:
        return {k: v for k, v in {"length": self.length, "period": self.period, "depth": self.depth, "in": self.in_,
                                  "out": self.out, "shift": self.shift, "drift": self.drift}.items() if v is not None}


class NoteEdit(BaseModel):
    index: int = Field(description="Note index in the part. / パート内の音符番号")
    position: int | None = Field(None, description="New start tick. / 新しい開始ティック")
    duration: int | None = Field(None, description="New length in ticks. / 新しい長さ")
    tone: Pitch | None = Field(None, description=_PITCH_DESC)
    lyric: str | None = Field(None, description="New lyric. / 新しい歌詞")
    tuning: int | None = Field(None, description="Fine tuning in cents. / 微調整（セント）")
    vibrato: Vibrato | None = Field(None, description="Vibrato fields to change. / 変更するビブラート項目")


def _notes_payload(notes: list[NoteIn]) -> list[dict]:
    return [{"position": n.position, "duration": n.duration, "tone": music.to_midi(n.tone), "lyric": n.lyric}
            for n in notes]


def _edit_payload(e: NoteEdit) -> dict:
    d: dict[str, Any] = {"index": e.index}
    for k in ("position", "duration", "lyric", "tuning"):
        if getattr(e, k) is not None:
            d[k] = getattr(e, k)
    if e.tone is not None:
        d["tone"] = music.to_midi(e.tone)
    if e.vibrato is not None:
        d["vibrato"] = e.vibrato.values()
    return d


def _split(text: str, language: str) -> tuple[list[str], list[str]]:
    tokens, warnings, _lang = lyric_text.split_lyrics(text, language)
    if not tokens:
        raise OpenUtauError("No lyrics found in the text", "テキストに歌詞が見つかりません")
    return tokens, warnings


# ======================= app & status =======================

@_tool()
def openutau_status() -> dict:
    """Is OpenUtau running, is the bridge reachable, and how to fix it if not. Call this first.
    / OpenUtau が起動しているか、ブリッジに接続できるか、できない場合の対処法。最初に呼んでください。"""
    info = app.status()
    if info["bridge"]:
        info["project"] = bridge.call("project.get")
    return info


@_tool()
def launch_openutau(project_path: str | None = None) -> dict:
    """Start OpenUtau (optionally with a project). If it is already running with the bridge, opens the project there.
    / OpenUtau を起動します（プロジェクト指定可）。起動済みならそのプロジェクトを開きます。"""
    return app.launch(project_path)


@_tool()
def close_openutau(force: bool = False) -> dict:
    """Close OpenUtau. Refuses if there are unsaved changes unless force=true (force discards them).
    / OpenUtau を終了します。未保存の変更がある場合は force=true が必要です（変更は破棄されます）。"""
    return app.close(force)


# ======================= live: project =======================

@_tool()
def get_project() -> dict:
    """Summary of the open project: file, saved state, key, tempos, time signatures, tracks, voice parts.
    / 開いているプロジェクトの概要（ファイル、保存状態、キー、テンポ、拍子、トラック、ボイスパート）。"""
    return bridge.call("project.get")


@_tool()
def new_project(force: bool = False) -> dict:
    """Start a new empty project. force=true discards unsaved changes.
    / 新規プロジェクトを作成します。force=true で未保存の変更を破棄します。"""
    return bridge.call("project.new", force=force)


@_tool()
def open_project(path: str, force: bool = False) -> dict:
    """Open a project file (.ustx, .ust, .vsqx, .mid, .musicxml, .svp, ...). force=true discards unsaved changes.
    / プロジェクトを開きます（.ustx .ust .vsqx .mid .musicxml .svp など）。force=true で未保存の変更を破棄します。"""
    return bridge.call("project.open", path=os.path.abspath(path), force=force)


@_tool()
def save_project(path: str | None = None) -> dict:
    """Save as .ustx to path, or to the current file if path is omitted.
    / .ustx として保存します。path 省略時は現在のファイルに上書き保存します。"""
    return bridge.call("project.save", path=os.path.abspath(path) if path else None)


@_tool()
def import_tracks(path: str, import_tempo: bool | None = None) -> dict:
    """Import the tracks of another project file into the open project.
    / 別のプロジェクトファイルのトラックを現在のプロジェクトに読み込みます。"""
    return bridge.call("project.import", path=os.path.abspath(path), import_tempo=import_tempo)


@_tool()
def undo() -> dict:
    """Undo the last edit. / 直前の編集を取り消します。"""
    return bridge.call("undo")


@_tool()
def redo() -> dict:
    """Redo the last undone edit. / 取り消した編集をやり直します。"""
    return bridge.call("redo")


@_tool()
def set_tempo(bpm: float, tick: int = 0) -> dict:
    """Set the tempo at tick 0, or add/replace a tempo change at a tick.
    / テンポを設定します（tick 0）。tick を指定するとその位置にテンポ変更を追加・置換します。"""
    return bridge.call("tempo.set", bpm=bpm, tick=tick)


@_tool()
def remove_tempo(tick: int) -> dict:
    """Remove the tempo change at a tick (not tick 0). / 指定ティックのテンポ変更を削除します（tick 0 は不可）。"""
    return bridge.call("tempo.remove", tick=tick)


@_tool()
def set_time_signature(beat_per_bar: int, beat_unit: int, bar: int = 0) -> dict:
    """Set the time signature at bar 0, or add a change at a bar (e.g. 3/4 = 3, 4).
    / 拍子を設定します（bar 0）。bar を指定するとその小節に拍子変更を追加します（例：3/4 は 3, 4）。"""
    return bridge.call("timesig.set", beat_per_bar=beat_per_bar, beat_unit=beat_unit, bar=bar)


@_tool()
def set_key(key: int | str) -> dict:
    """Set the project key: 0 = C ... 11 = B, or a name like "F#" / "Bb".
    / プロジェクトのキー：0 = C 〜 11 = B、または "F#"・"Bb" などの音名。"""
    if isinstance(key, str) and not key.strip().isdigit():
        key = music.to_midi(key.strip() + "4") % 12
    return bridge.call("key.set", key=int(key))


# ======================= live: catalog =======================

@_tool()
def list_singers() -> list:
    """Singers OpenUtau has loaded: id, name, type, location, default phonemizer, supported renderers.
    Singers without a default phonemizer get a "suggested_phonemizer" (a guess: confirm with rank_phonemizers).
    / OpenUtau が読み込んだ歌手一覧（ID、名前、種類、場所、既定の音素化器、対応レンダラー）。
    既定の音素化器が無い歌手には "suggested_phonemizer" を付けます。"""
    singers = bridge.call("singers.list")
    banks = {b["id"]: b for b in voicebanks.list_voicebanks()}
    for s in singers:
        if not s.get("default_phonemizer") and s.get("id") in banks:
            s["suggested_phonemizer"] = voicebanks.suggest_phonemizer(banks[s["id"]])
    return singers


@_tool()
def list_phonemizers(language: str | None = None) -> list:
    """Installed phonemizers (type, name, tag, language, author); filter by language such as "EN" or "JA".
    / インストール済みの音素化器一覧。language（"EN"・"JA" など）で絞り込めます。"""
    return bridge.call("phonemizers.list", language=language)


_SAMPLE_WORDS = {
    "EN": "hello world this is a test we sing beautiful songs of light and love through the night",
    "JA": "さくら さくら やよいの そらは みわたす かぎり きゃっと しゅんかん",
}


@_tool()
def rank_phonemizers(singer: str, language: str | None = None, text: str | None = None) -> dict:
    """Find the best phonemizer for a singer by trying each installed classic phonemizer on sample lyrics and
    counting how many of the sounds it asks for exist in the voicebank (score 1.0 = every sound has a sample).
    language: "EN", "JA" or omitted for both; text: your own lyrics instead of the built-in samples.
    Nothing in the project changes. / 各音素化器でサンプル歌詞を音素化し、音源にサンプルがある音の割合で順位付けします
    （1.0 = すべての音にサンプルあり）。プロジェクトは変更しません。"""
    langs = [language.upper()] if language else ["EN", "JA"]
    out = []
    for lang in langs:
        words = _split(text or _SAMPLE_WORDS.get(lang, _SAMPLE_WORDS["EN"]), "ja" if lang == "JA" else "en")[0]
        words = [w for w in words if not w.startswith("+")]
        out += bridge.call("phonemizers.rank", timeout=300, singer=singer, language=lang, words=words)["ranking"]
    # Converters ("EN to JA") turn English into Japanese sounds; on a tie, a native phonemizer is the better pick.
    out.sort(key=lambda r: (r["score"], " to " not in r["tag"], r["phonemes"]), reverse=True)
    best = next((r for r in out if r["score"] > 0 and not r["error"]), None)
    # Coverage often ties (rich banks cover several styles); then the bank author's default is the better pick.
    default = next((s.get("default_phonemizer") for s in bridge.call("singers.list") if s.get("id") == singer), None)
    pick = next((r for r in out if r["type"] == default and not r["error"]), None)
    if best and pick and pick["score"] >= best["score"] - 0.03:
        best = pick
    return {"singer": singer, "best": best and best["type"], "best_tag": best and best["tag"], "ranking": out}


@_tool()
def list_expressions() -> list:
    """Project expressions (abbr, name, type, min, max, default). / プロジェクトの表情パラメータ一覧。"""
    return bridge.call("expressions.list")


# ======================= live: tracks & parts =======================

@_tool()
def add_track(singer: str | None = None, phonemizer: str | None = None, name: str | None = None,
              renderer: str | None = None) -> dict:
    """Add a track. Setting a singer also applies its default phonemizer and a suitable renderer unless given.
    Phonemizer may be a full type name, class name or tag ("EN ARPA", "JA VCV & CVVC").
    / トラックを追加します。歌手を指定すると既定の音素化器とレンダラーも設定されます。
    音素化器は型名・クラス名・タグ（"EN ARPA" など）で指定できます。"""
    return bridge.call("track.add", singer=singer, phonemizer=phonemizer, name=name, renderer=renderer)


@_tool()
def update_track(track: int, singer: str | None = None, phonemizer: str | None = None, name: str | None = None,
                 renderer: str | None = None, volume: float | None = None, pan: float | None = None,
                 mute: bool | None = None, solo: bool | None = None) -> dict:
    """Change a track: singer, phonemizer, name, renderer, volume (dB, -24..12), pan (-100..100), mute, solo.
    / トラックを変更します：歌手、音素化器、名前、レンダラー、音量（dB）、パン、ミュート、ソロ。"""
    return bridge.call("track.update", track=track, singer=singer, phonemizer=phonemizer, name=name,
                       renderer=renderer, volume=volume, pan=pan, mute=mute, solo=solo)


@_tool()
def remove_track(track: int) -> dict:
    """Remove a track and its parts. / トラックとそのパートを削除します。"""
    return bridge.call("track.remove", track=track)


@_tool()
def add_part(track: int, position: int = 0, duration: int = 7680, name: str | None = None) -> dict:
    """Add an empty voice part to a track (position/duration in ticks; 7680 = 4 bars of 4/4).
    / トラックに空のボイスパートを追加します（位置・長さはティック、7680 = 4/4 で4小節）。"""
    return bridge.call("part.add", track=track, position=position, duration=duration, name=name)


@_tool()
def update_part(part: int, name: str | None = None, position: int | None = None, track: int | None = None,
                duration: int | None = None) -> dict:
    """Rename, move (position / track) or resize a voice part.
    / ボイスパートの名前変更・移動（位置・トラック）・長さ変更。"""
    return bridge.call("part.update", part=part, name=name, position=position, track=track, duration=duration)


@_tool()
def remove_part(part: int) -> dict:
    """Remove a voice part. / ボイスパートを削除します。"""
    return bridge.call("part.remove", part=part)


# ======================= live: notes =======================

@_tool()
def list_notes(part: int) -> dict:
    """Notes of a voice part: index, position, duration, tone, lyric, tuning, vibrato.
    / ボイスパートの音符一覧（番号、位置、長さ、音高、歌詞、微調整、ビブラート）。"""
    return bridge.call("notes.list", part=part)


@_tool()
def add_notes(part: int, notes: list[NoteIn]) -> dict:
    """Add notes to a voice part (positions relative to the part); the part grows if needed.
    / ボイスパートに音符を追加します（位置はパート相対）。必要ならパートを延長します。"""
    return bridge.call("notes.add", part=part, notes=_notes_payload(notes))


@_tool()
def edit_notes(part: int, edits: list[NoteEdit]) -> dict:
    """Edit notes in place by index (position, duration, tone, lyric, tuning, vibrato); pitch curves are kept.
    / 番号で指定した音符をその場で編集します（位置・長さ・音高・歌詞・微調整・ビブラート）。ピッチ曲線は保持されます。"""
    return bridge.call("notes.edit", part=part, edits=[_edit_payload(e) for e in edits])


@_tool()
def replace_lyrics(part: int, lyrics: list[str], start: int = 0) -> dict:
    """Write lyrics onto consecutive notes starting at note index start (one item per note, no splitting).
    / 音符番号 start から順に歌詞を書き込みます（1要素 = 1音符、分割なし）。"""
    return bridge.call("notes.lyrics", part=part, start=start, lyrics=lyrics)


@_tool()
def delete_notes(part: int, indices: list[int] | None = None) -> dict:
    """Delete notes by index; no indices = delete all notes in the part.
    / 番号で音符を削除します。indices を省略するとパートの全音符を削除します。"""
    return bridge.call("notes.delete", part=part, indices=indices)


@_tool()
def set_note_expression(part: int, abbr: str, value: float | None, indices: list[int] | None = None) -> dict:
    """Set a note expression (e.g. vel, vol, atk, dec, gen, bre, clr) on notes; no indices = all notes;
    value null = reset to default. / 音符の表情（vel・vol・atk など）を設定します。indices 省略で全音符、value=null で既定値に戻します。"""
    return bridge.call("notes.expression", part=part, abbr=abbr, value=value, indices=indices)


class PitchPoint(BaseModel):
    x: float = Field(description="Milliseconds from the note start (negative = before it). / 音符の開始からのミリ秒（負 = 前）")
    y: float = Field(description="Offset from the note's pitch in tenths of a semitone (10 = 1 semitone, -5 = a quarter tone "
                                 "flat). / 音符の音高からのずれ（0.1 半音単位、10 = 半音）")
    shape: str = Field("io", description="Curve to the next point: io (ease in-out), i, o, l (linear). / 次の点への曲線形状")


@_tool()
def set_pitch(part: int, indices: list[int], points: list[PitchPoint], snap_first: bool = True) -> dict:
    """Replace the pitch curve of notes (scoops, falls, drifts, overshoot). At least 2 points. snap_first=true makes the
    first point start from the previous note's pitch, overriding its y (a normal slide); use false for a scoop or any
    start you set yourself. Examples: scoop up into a note (snap_first=false): [{x:-40,y:-20},{x:60,y:0}];
    fall at a phrase end on a 600 ms note: [{x:-40,y:0},{x:40,y:0},{x:420,y:0},{x:600,y:-30,shape:"i"}].
    / 音符のピッチ曲線を置き換えます（しゃくり・フォール・揺れ）。点は2つ以上。"""
    return bridge.call("notes.pitch", part=part, indices=indices,
                       points=[p.model_dump() for p in points], snap_first=snap_first)


@_tool()
def get_curve(part: int, abbr: str) -> dict:
    """Read an expression curve of a part (e.g. dyn, pitd, tenc, brec, genc, voic): [tick, value] points, min/max/default.
    / パートの表情カーブを読みます（dyn・tenc・brec など）。"""
    return bridge.call("curve.get", part=part, abbr=abbr)


@_tool()
def set_curve(part: int, abbr: str, points: list[list[float]]) -> dict:
    """Draw an expression curve through [tick, value] points (part-relative ticks), straight lines between them; values
    are clamped to the curve's range. Use for dynamics (dyn), DiffSinger tension (tenc), breathiness (brec), gender
    (genc), voicing (voic), pitch deviation (pitd, cents). / [ティック, 値] の点を直線で結んで表情カーブを描きます。"""
    return bridge.call("curve.set", part=part, abbr=abbr, points=points)


@_tool()
def clear_curve(part: int, abbr: str) -> dict:
    """Reset an expression curve of a part to its default. / 表情カーブを既定値に戻します。"""
    return bridge.call("curve.clear", part=part, abbr=abbr)


@_tool()
def refresh_singers() -> list:
    """Rescan the Singers folder so newly installed voicebanks appear without restarting OpenUtau.
    / Singers フォルダを再読み込みし、新しく入れた音源を OpenUtau の再起動なしで使えるようにします。"""
    return bridge.call("singers.refresh", timeout=300)


@_tool()
def list_phonemes(part: int) -> dict:
    """Phonemes OpenUtau produced for a part (note index, lyric, position, duration, phoneme, has_oto).
    Use it to check pronunciation. / パートについて OpenUtau が生成した音素一覧。発音の確認に使います。"""
    return bridge.call("phonemes.list", part=part)


@_tool()
def assign_lyrics(part: int, text: str, start_tick: int = 0, durations: int | list[int] = 480,
                  tones: Pitch | list[Pitch] = 60, language: str = "auto") -> dict:
    """Split text into lyrics and lay out new consecutive notes from start_tick. durations / tones may be one value
    or a list (the last value repeats). / テキストを歌詞に分割し、start_tick から連続する新しい音符を作ります。
    durations・tones は単一値かリスト（最後の値を繰り返し）。"""
    tokens, warnings = _split(text, language)
    notes = music.layout_notes(tokens, start_tick, durations, tones)
    result = bridge.call("notes.add", part=part, notes=notes)
    return {"lyrics": tokens, "warnings": warnings, **result}


@_tool()
def set_lyrics(part: int, text: str, start_index: int = 0, language: str = "auto") -> dict:
    """Split text into lyrics and write them onto existing notes from start_index.
    / テキストを歌詞に分割し、start_index 番目からの既存の音符に書き込みます。"""
    tokens, warnings = _split(text, language)
    result = bridge.call("notes.lyrics", part=part, start=start_index, lyrics=tokens)
    return {"lyrics": tokens, "warnings": warnings, **result}


def _bar_ticks(time_signatures: list[dict] | None) -> int:
    ts = (time_signatures or [{}])[0]
    return ts.get("beat_per_bar", 4) * 1920 // ts.get("beat_unit", 4)


@_tool()
def add_melody(part: int, melody: str, lyrics: str | None = None, start_tick: int = 0, language: str = "auto") -> dict:
    """Add a melody with its lyrics in one call. melody: space-separated PITCH:BEATS (r = rest). lyrics are split
    like set_lyrics and must give one lyric per sounding note (use "+" for held syllables).
    / メロディと歌詞を一度に追加します。melody は「音名:拍」（r = 休符）。歌詞は set_lyrics と同じ規則で分割され、
    音の数と一致する必要があります（伸ばす音節は「+」）。"""
    tokens, warnings = _split(lyrics, language) if lyrics else (None, [])
    notes = music.melody_notes(melody, tokens, start_tick)
    return {"lyrics": tokens, "warnings": warnings, **bridge.call("notes.add", part=part, notes=notes)}


@_tool()
def fit_part(part: int) -> dict:
    """Resize a voice part to end on the first bar line after its last note.
    / ボイスパートの長さを、最後の音符の後の最初の小節線までに合わせます。"""
    notes = bridge.call("notes.list", part=part)["notes"]
    bar = _bar_ticks(bridge.call("project.get").get("time_signatures"))
    return bridge.call("part.update", part=part, duration=music.fitted_length(notes, bar))


# ======================= live: playback & export =======================

@_tool()
def play(tick: int | None = None, end_tick: int | None = None, track: int | None = None) -> dict:
    """Start playback (from tick, optionally until end_tick, optionally one track only).
    / 再生します（tick から、end_tick まで、track 指定でそのトラックのみ）。"""
    return bridge.call("playback.play", tick=tick, end_tick=end_tick, track=track)


@_tool()
def pause() -> dict:
    """Pause playback. / 再生を一時停止します。"""
    return bridge.call("playback.pause")


@_tool()
def stop() -> dict:
    """Stop playback. / 再生を停止します。"""
    return bridge.call("playback.stop")


@_tool()
def seek(tick: int) -> dict:
    """Move the playback cursor. / 再生位置を移動します。"""
    return bridge.call("playback.seek", tick=tick)


@_tool()
def export_wav(path: str, per_track: bool = False) -> dict:
    """Render the mixdown to a WAV file, or one WAV per track (per_track=true). Can take minutes.
    / ミックスダウンを WAV に書き出します。per_track=true でトラックごとに書き出します。数分かかることがあります。"""
    return bridge.call("export.wav", timeout=1800, path=os.path.abspath(path), per_track=per_track)


@_tool()
def export_midi(path: str) -> dict:
    """Export the project as a MIDI file. / プロジェクトを MIDI ファイルに書き出します。"""
    return bridge.call("export.midi", path=os.path.abspath(path))


# ======================= file tools (.ustx / .ust) =======================

_PHONEMIZER_TAGS = {
    "ja vcv & cvvc": "JapanesePresampPhonemizer", "ja vcv": "JapaneseVCVPhonemizer", "ja cvvc": "JapaneseCVVCPhonemizer",
    "en arpa": "ArpasingPhonemizer", "en vccv": "EnglishVCCVPhonemizer", "en to ja": "ENtoJAPhonemizer",
    "en x-sampa": "EnXSampaPhonemizer",
}


def _phonemizer_type(name: str | None) -> str | None:
    """Full type name from a full name, built-in class name or common tag (offline: no plugin list available)."""
    if not name:
        return None
    if "." in name:
        return name
    cls = _PHONEMIZER_TAGS.get(name.lower(), name)
    return f"OpenUtau.Plugin.Builtin.{cls}"


def _singer(query: str | None, phonemizer: str | None) -> tuple[str | None, str | None]:
    """Voicebank id + phonemizer (given > voicebank default > JapanesePresampPhonemizer)."""
    if not query:
        return None, _phonemizer_type(phonemizer)
    bank = voicebanks.find_voicebank(query)
    ph = _phonemizer_type(phonemizer) or bank.get("default_phonemizer") or \
        "OpenUtau.Plugin.Builtin.JapanesePresampPhonemizer"
    return bank["id"], ph


def _edit_file(path: str, fn):
    project = ustx.load(path)
    result = fn(project)
    ustx.save(project, path)
    return result


@_tool()
def ustx_create(path: str, bpm: float = 120, singer: str | None = None, phonemizer: str | None = None,
                name: str | None = None, overwrite: bool = False) -> dict:
    """Create a new .ustx file (one track, no parts). singer = voicebank id or name.
    / 新しい .ustx ファイルを作成します（1トラック、パートなし）。singer は音源 ID か名前。"""
    path = os.path.abspath(path)
    if os.path.exists(path) and not overwrite:
        raise OpenUtauError(f"{path} exists; pass overwrite=true", f"{path} は既に存在します。overwrite=true を指定してください")
    sid, ph = _singer(singer, phonemizer)
    project = ustx.new_project(bpm, sid, ph, name or os.path.splitext(os.path.basename(path))[0])
    ustx.save(project, path)
    return ustx.summary(project, path)


@_tool()
def ustx_summary(path: str) -> dict:
    """Summary of a .ustx file (tempos, tracks, voice parts). / .ustx ファイルの概要。"""
    path = os.path.abspath(path)
    return ustx.summary(ustx.load(path), path)


@_tool()
def ustx_set_tempo(path: str, bpm: float, tick: int = 0) -> dict:
    """Set the tempo at tick 0 or a tempo change at a tick in a .ustx file.
    / .ustx ファイルのテンポ（tick 0）またはテンポ変更を設定します。"""
    path = os.path.abspath(path)
    return _edit_file(path, lambda p: (ustx.set_tempo(p, bpm, tick), ustx.summary(p, path))[1])


@_tool()
def ustx_add_track(path: str, name: str | None = None, singer: str | None = None, phonemizer: str | None = None) -> dict:
    """Add a track to a .ustx file. / .ustx ファイルにトラックを追加します。"""
    path = os.path.abspath(path)
    sid, ph = _singer(singer, phonemizer)
    return _edit_file(path, lambda p: {"track": ustx.add_track(p, name, sid, ph)})


@_tool()
def ustx_set_track_singer(path: str, track: int, singer: str, phonemizer: str | None = None) -> dict:
    """Set the singer (and phonemizer: given > voicebank default > Japanese presamp) of a track in a .ustx file.
    / .ustx ファイルのトラックの歌手（と音素化器）を設定します。"""
    path = os.path.abspath(path)
    sid, ph = _singer(singer, phonemizer)

    def fn(p):
        t = ustx.track(p, track)
        t["singer"], t["phonemizer"], t["renderer_settings"] = sid, ph, {}
        return {"track": track, "singer": sid, "phonemizer": ph}
    return _edit_file(path, fn)


@_tool()
def ustx_add_voice_part(path: str, track: int = 0, position: int = 0, duration: int = 7680,
                        name: str = "New Part") -> dict:
    """Add an empty voice part to a .ustx file. / .ustx ファイルに空のボイスパートを追加します。"""
    path = os.path.abspath(path)
    return _edit_file(path, lambda p: {"part": ustx.add_voice_part(p, track, position, duration, name)})


@_tool()
def ustx_add_notes(path: str, part: int, notes: list[NoteIn]) -> dict:
    """Add notes to a voice part in a .ustx file (the part grows if needed).
    / .ustx ファイルのボイスパートに音符を追加します（必要ならパートを延長）。"""
    path = os.path.abspath(path)
    payload = [n.model_dump() for n in notes]
    return _edit_file(path, lambda p: {"added": ustx.add_notes(ustx.voice_part(p, part), payload)})


@_tool()
def ustx_list_notes(path: str, part: int) -> dict:
    """List the notes of a voice part in a .ustx file. / .ustx ファイルのボイスパートの音符一覧。"""
    vp = ustx.voice_part(ustx.load(os.path.abspath(path)), part)
    return {"part": part, "position": vp.get("position", 0), "duration": vp.get("duration", 0),
            "notes": [ustx.note_info(i, n) for i, n in enumerate(vp["notes"])]}


@_tool()
def ustx_edit_notes(path: str, part: int, edits: list[NoteEdit]) -> dict:
    """Edit notes by index in a .ustx file (position, duration, tone, lyric, tuning, vibrato).
    / .ustx ファイルの音符を番号で編集します。"""
    path = os.path.abspath(path)

    def fn(p):
        vp = ustx.voice_part(p, part)
        targets = [(_edit_payload(e), vp["notes"][e.index] if 0 <= e.index < len(vp["notes"]) else None) for e in edits]
        for e, note in targets:
            if note is None:
                raise OpenUtauError(f"Note {e['index']} does not exist", f"音符 {e['index']} は存在しません")
            ustx.edit_note(note, e)
        vp["duration"] = max(vp["duration"], max((n["position"] + n["duration"] for n in vp["notes"]), default=0))
        return {"edited": len(targets)}
    return _edit_file(path, fn)


@_tool()
def ustx_delete_notes(path: str, part: int, indices: list[int] | None = None) -> dict:
    """Delete notes by index from a .ustx file (no indices = all). / .ustx ファイルの音符を削除します（省略で全部）。"""
    path = os.path.abspath(path)

    def fn(p):
        vp = ustx.voice_part(p, part)
        drop = set(range(len(vp["notes"]))) if not indices else set(indices)
        bad = [i for i in drop if not 0 <= i < len(vp["notes"])]
        if bad:
            raise OpenUtauError(f"Notes {bad} do not exist", f"音符 {bad} は存在しません")
        vp["notes"] = [n for i, n in enumerate(vp["notes"]) if i not in drop]
        return {"deleted": len(drop), "note_count": len(vp["notes"])}
    return _edit_file(path, fn)


@_tool()
def ustx_set_vibrato(path: str, part: int, vibrato: Vibrato, indices: list[int] | None = None) -> dict:
    """Set vibrato fields on notes in a .ustx file (no indices = all notes). length > 0 turns vibrato on.
    / .ustx ファイルの音符にビブラートを設定します（省略で全音符）。length > 0 で有効。"""
    path = os.path.abspath(path)

    def fn(p):
        vp = ustx.voice_part(p, part)
        idx = indices or list(range(len(vp["notes"])))
        for i in idx:
            if not 0 <= i < len(vp["notes"]):
                raise OpenUtauError(f"Note {i} does not exist", f"音符 {i} は存在しません")
            ustx.set_vibrato(vp["notes"][i], **vibrato.values())
        return {"notes": len(idx)}
    return _edit_file(path, fn)


@_tool()
def ustx_assign_lyrics(path: str, part: int, text: str, start_tick: int = 0, durations: int | list[int] = 480,
                       tones: Pitch | list[Pitch] = 60, language: str = "auto") -> dict:
    """Split text into lyrics and add consecutive notes to a voice part in a .ustx file.
    / テキストを歌詞に分割し、.ustx ファイルのボイスパートに連続する音符を追加します。"""
    path = os.path.abspath(path)
    tokens, warnings = _split(text, language)
    notes = music.layout_notes(tokens, start_tick, durations, tones)
    added = _edit_file(path, lambda p: ustx.add_notes(ustx.voice_part(p, part), notes))
    return {"lyrics": tokens, "warnings": warnings, "added": added}


@_tool()
def ustx_add_melody(path: str, part: int, melody: str, lyrics: str | None = None, start_tick: int = 0,
                    language: str = "auto") -> dict:
    """add_melody for a .ustx file. / .ustx ファイル版の add_melody。"""
    path = os.path.abspath(path)
    tokens, warnings = _split(lyrics, language) if lyrics else (None, [])
    notes = music.melody_notes(melody, tokens, start_tick)
    added = _edit_file(path, lambda p: ustx.add_notes(ustx.voice_part(p, part), notes))
    return {"lyrics": tokens, "warnings": warnings, "added": added}


@_tool()
def ustx_fit_part(path: str, part: int) -> dict:
    """fit_part for a .ustx file. / .ustx ファイル版の fit_part。"""
    path = os.path.abspath(path)

    def fn(p):
        vp = ustx.voice_part(p, part)
        vp["duration"] = music.fitted_length(vp["notes"], _bar_ticks(
            [{"beat_per_bar": t.get("beat_per_bar", 4), "beat_unit": t.get("beat_unit", 4)}
             for t in p.get("time_signatures") or []]))
        return {"part": part, "duration": vp["duration"]}
    return _edit_file(path, fn)


@_tool()
def ust_import(ust_path: str, ustx_path: str, singer: str | None = None, phonemizer: str | None = None,
               overwrite: bool = False) -> dict:
    """Convert a classic UTAU .ust (Shift_JIS unless Charset= says otherwise) into a new .ustx file.
    / UTAU の .ust（既定は Shift_JIS、Charset= 行があれば従う）を新しい .ustx に変換します。"""
    ustx_path = os.path.abspath(ustx_path)
    if os.path.exists(ustx_path) and not overwrite:
        raise OpenUtauError(f"{ustx_path} exists; pass overwrite=true", f"{ustx_path} は既に存在します。overwrite=true を指定してください")
    sid, ph = _singer(singer, phonemizer)
    project = ust.to_ustx(os.path.abspath(ust_path), sid, ph)
    ustx.save(project, ustx_path)
    return ustx.summary(project, ustx_path)


@_tool()
def ust_export(ustx_path: str, ust_path: str, part: int = 0, encoding: str = "shift_jis") -> dict:
    """Export one voice part of a .ustx as a classic .ust (gaps become R rests; Shift_JIS by default).
    / .ustx のボイスパートを UTAU の .ust に書き出します（隙間は休符 R、既定は Shift_JIS）。"""
    project = ustx.load(os.path.abspath(ustx_path))
    vp = ustx.voice_part(project, part)
    blocks = ust.write(os.path.abspath(ust_path), vp["notes"], project["tempos"][0]["bpm"],
                       project.get("name", ""), encoding)
    return {"path": os.path.abspath(ust_path), "blocks": blocks}


# ======================= voicebanks =======================

@_tool()
def list_voicebanks() -> list:
    """Voicebanks in the Singers folder and AdditionalSingerPath (id as OpenUtau uses it, name, author,
    default phonemizer). / Singers フォルダーと AdditionalSingerPath の音源一覧（OpenUtau と同じ ID）。"""
    return voicebanks.list_voicebanks()


@_tool()
def get_voicebank(voicebank: str) -> dict:
    """Details of a voicebank: info, oto sets and alias count. / 音源の詳細（情報、oto セット、エイリアス数）。"""
    bank = voicebanks.find_voicebank(voicebank)
    entries = voicebanks.otos(bank)
    sets: dict[str, int] = {}
    for e in entries:
        sets[e["set"]] = sets.get(e["set"], 0) + 1
    return {**bank, "alias_count": len(entries), "oto_sets": sets, "sample_aliases": [e["alias"] for e in entries[:30]]}


@_tool()
def search_oto(voicebank: str, query: str, limit: int = 50) -> dict:
    """Search oto.ini aliases of a voicebank (substring match). / 音源の oto.ini エイリアスを検索します（部分一致）。"""
    bank = voicebanks.find_voicebank(voicebank)
    hits = [e for e in voicebanks.otos(bank) if query in e["alias"]]
    return {"voicebank": bank["id"], "total": len(hits), "results": hits[:max(1, limit)]}


# ======================= utilities =======================

@_tool()
def note_to_midi(note: str) -> int:
    """Note name to MIDI number (C4 = 60). / 音名を MIDI 番号に変換します（C4 = 60）。"""
    return music.to_midi(note)


@_tool()
def midi_to_note(midi: int) -> str:
    """MIDI number to note name (60 = C4). / MIDI 番号を音名に変換します（60 = C4）。"""
    return music.to_name(midi)


@_tool()
def beats_to_ticks(beats: float) -> int:
    """Quarter-note beats to ticks (1 beat = 480). / 拍数（四分音符）をティックに変換します（1拍 = 480）。"""
    return music.beats_to_ticks(beats)


@_tool()
def ticks_to_beats(ticks: int) -> float:
    """Ticks to quarter-note beats. / ティックを拍数に変換します。"""
    return music.ticks_to_beats(ticks)


@_tool()
def split_lyrics(text: str, language: str = "auto") -> dict:
    """Preview how text is split into one lyric per note (language auto / ja / en).
    / テキストが1音符ずつの歌詞にどう分割されるかを確認します（auto / ja / en）。"""
    tokens, warnings, lang = lyric_text.split_lyrics(text, language)
    return {"language": lang, "lyrics": tokens, "count": len(tokens), "warnings": warnings}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
