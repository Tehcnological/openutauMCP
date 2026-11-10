"""End-to-end test: starts the MCP server over stdio as a real MCP client.

    python tests/e2e_test.py           # file / voicebank / utility tools (OpenUtau may be closed)
    python tests/e2e_test.py --live    # also drives the running OpenUtau through the bridge

The live part refuses to run if the open OpenUtau project has unsaved changes.
Set OPENUTAU_MCP_KEEP=1 to keep the temp folder.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USTXCHECK = os.path.join(ROOT, ".build", "ustxcheck", "ustxcheck.exe")
passed: list[str] = []


def ok(cond, label, detail=None):
    if not cond:
        raise AssertionError(f"FAIL: {label}" + (f"\n  {detail}" if detail is not None else ""))
    passed.append(label)
    print(f"  ok  {label}", flush=True)


class Client:
    def __init__(self, session: ClientSession):
        self.s = session

    async def __call__(self, _tool, **args):
        name = _tool
        res = await self.s.call_tool(name, args)
        text = "".join(c.text for c in res.content if getattr(c, "text", None))
        if res.isError:
            raise RuntimeError(f"{name} failed: {text}")
        if res.structuredContent is not None and set(res.structuredContent) == {"result"}:
            return res.structuredContent["result"]
        texts = [c.text for c in res.content if getattr(c, "text", None) is not None]
        try:
            return [json.loads(t) for t in texts] if len(texts) > 1 else json.loads(text)
        except ValueError:
            return text

    async def error(self, name, **args) -> str:
        res = await self.s.call_tool(name, args)
        ok(res.isError, f"{name} returns an error")
        return "".join(c.text for c in res.content if getattr(c, "text", None))


async def file_tests(c: Client, tmp: str) -> dict:
    print("[utilities]")
    ok(await c("note_to_midi", note="C4") == 60, "C4 = 60")
    ok(await c("note_to_midi", note="Cb4") == 59, "Cb4 = 59")
    ok(await c("note_to_midi", note="C-1") == 0, "C-1 = 0")
    ok(await c("note_to_midi", note="Bb3") == 58 and await c("note_to_midi", note="A#3") == 58, "A#3 = Bb3 = 58")
    ok(await c("midi_to_note", midi=61) == "C#4", "61 = C#4")
    ok(await c("beats_to_ticks", beats=1.5) == 720, "1.5 beats = 720 ticks")
    r = await c("split_lyrics", text="きゃりーぱみゅぱみゅ、ちゃっと")
    ok(r["lyrics"] == ["きゃ", "り", "+", "ぱ", "みゅ", "ぱ", "みゅ", "ちゃ", "っ", "と"], "Japanese mora split", r)
    r = await c("split_lyrics", text="夜空")
    ok(r["lyrics"] == ["よ", "ぞ", "ら"], "kanji -> hiragana", r)
    r = await c("split_lyrics", text="Hel-lo, beau-ti-ful world!")
    ok(r["lyrics"] == ["hello", "+", "beautiful", "+", "+", "world"], "English syllable split", r)
    err = await c.error("note_to_midi", note="H9")
    ok("/" in err and any("぀" <= ch <= "ヿ" for ch in err), "error message is bilingual", err)

    print("[voicebanks]")
    banks = await c("list_voicebanks")
    # Works with whatever voicebanks are installed: prefer a Japanese and an English one, else reuse any bank.
    ok(len(banks) > 0, "at least one voicebank installed (the tests need one)", banks)
    ja = next((b for b in banks if "JapanesePresamp" in (b.get("default_phonemizer") or "")), banks[0])
    en = next((b for b in banks if b is not ja and any(k in (b.get("name") or "") + (b.get("default_phonemizer") or "")
               for k in ("English", "Arpasing", "XSampa", "VCCV"))), ja)
    print(f"  using voicebanks: ja={ja['id']!r} en={en['id']!r}")
    r = await c("search_oto", voicebank=ja["id"], query="", limit=5)
    ok(r["total"] > 0, "oto search lists aliases", r["total"])
    r = await c("get_voicebank", voicebank=en["name"])
    ok(r["alias_count"] > 0, "voicebank oto parsed", r["alias_count"])

    print("[ustx file tools]")
    path = os.path.join(tmp, "song.ustx")
    s = await c("ustx_create", path=path, bpm=120, singer=ja["id"])
    ok(s["tracks"][0]["singer"] == ja["id"] and "JapanesePresamp" in s["tracks"][0]["phonemizer"], "create with singer")
    ok((await c("ustx_add_voice_part", path=path, track=0, position=0, duration=1920, name="JA"))["part"] == 0, "add part 0")
    r = await c("ustx_assign_lyrics", path=path, part=0, text="さくら さくら やよいの そらは",
                durations=[480, 480, 960], tones=["A4", "A4", "B4"])
    ok(r["lyrics"][:3] == ["さ", "く", "ら"] and len(r["added"]) == 13, "assign Japanese lyrics", r)
    t = await c("ustx_add_track", path=path, name="EN", singer=en["id"], phonemizer="EN X-SAMPA")
    ok(t["track"] == 1, "add English track")
    ok((await c("ustx_add_voice_part", path=path, track=1, position=0, duration=1920, name="EN"))["part"] == 1, "add part 1")
    r = await c("ustx_assign_lyrics", path=path, part=1, text="Hel-lo world", tones="C4", start_tick=960)
    ok(r["lyrics"] == ["hello", "+", "world"], "assign English lyrics", r)
    await c("ustx_add_notes", path=path, part=1, notes=[{"position": 3840, "duration": 480, "tone": "E4", "lyric": "sing"}])
    notes = (await c("ustx_list_notes", path=path, part=1))["notes"]
    ok([n["lyric"] for n in notes] == ["hello", "+", "world", "sing"] and notes[0]["tone"] == 60, "list notes", notes)
    await c("ustx_edit_notes", path=path, part=1, edits=[{"index": 3, "tone": "F4", "lyric": "song", "vibrato": {"length": 60}}])
    await c("ustx_set_vibrato", path=path, part=0, indices=[2], vibrato={"length": 50, "depth": 30})
    n1 = (await c("ustx_list_notes", path=path, part=1))["notes"][3]
    ok(n1["tone"] == 65 and n1["lyric"] == "song" and n1["vibrato"]["length"] == 60, "edit note + vibrato", n1)
    await c("ustx_delete_notes", path=path, part=1, indices=[3])
    ok(len((await c("ustx_list_notes", path=path, part=1))["notes"]) == 3, "delete note")
    await c("ustx_set_tempo", path=path, bpm=100)
    s = await c("ustx_set_tempo", path=path, bpm=140, tick=1920)
    ok([t["bpm"] for t in s["tempos"]] == [100, 140], "tempo + tempo change", s["tempos"])
    part0 = (await c("ustx_summary", path=path))["voice_parts"][0]
    ok(part0["duration"] >= 14 * 480, "part grew to fit notes", part0)
    mel = os.path.join(tmp, "melody.ustx")
    await c("ustx_create", path=mel, bpm=90)
    await c("ustx_add_voice_part", path=mel, track=0, duration=7680)
    await c("ustx_add_melody", path=mel, part=0, melody="A4:1 A4:1 B4:2 r:1/2 C5:3/2", lyrics="さくらー")
    notes = (await c("ustx_list_notes", path=mel, part=0))["notes"]
    ok([(n["lyric"], n["tone"], n["position"], n["duration"]) for n in notes] ==
       [("さ", 69, 0, 480), ("く", 69, 480, 480), ("ら", 71, 960, 960), ("+", 72, 2160, 720)], "add melody with lyrics", notes)
    await c.error("ustx_add_melody", path=mel, part=0, melody="A4 B4", lyrics="あ")
    ok((await c("ustx_fit_part", path=mel, part=0))["duration"] == 3840, "fit part to the next bar line")

    print("[ust import/export]")
    await c("ustx_add_notes", path=path, part=0, notes=[{"position": 12480, "duration": 480, "tone": 69, "lyric": "ら"}])
    ust_path = os.path.join(tmp, "song.ust")
    await c("ust_export", ustx_path=path, ust_path=ust_path, part=0)
    raw = open(ust_path, "rb").read().decode("shift_jis")
    ok("Lyric=さ" in raw and "Lyric=R" in raw and "Tempo=100" in raw, "UST export is Shift_JIS with rests")
    back = os.path.join(tmp, "back.ustx")
    await c("ust_import", ust_path=ust_path, ustx_path=back, singer=ja["id"])
    a = (await c("ustx_list_notes", path=path, part=0))["notes"]
    b = (await c("ustx_list_notes", path=back, part=0))["notes"]
    ok([(n["position"], n["duration"], n["tone"], n["lyric"]) for n in a] ==
       [(n["position"], n["duration"], n["tone"], n["lyric"]) for n in b], "UST round trip keeps notes")
    utf = os.path.join(tmp, "utf8.ust")
    with open(utf, "w", encoding="utf-8") as f:
        f.write("[#VERSION]\nUST Version1.2\nCharset=UTF-8\n[#SETTING]\nTempo=90\n[#0000]\nLength=480\nLyric=R\nNoteNum=60\n"
                "[#0001]\nLength=960\nLyric=うた\nNoteNum=62\n[#TRACKEND]\n")
    s = await c("ust_import", ust_path=utf, ustx_path=os.path.join(tmp, "utf8.ustx"))
    n = (await c("ustx_list_notes", path=os.path.join(tmp, "utf8.ustx"), part=0))["notes"]
    ok(s["tempos"][0]["bpm"] == 90 and n == [{**n[0], "position": 480, "duration": 960, "tone": 62, "lyric": "うた"}],
       "UST import honours Charset= and skips rests", n)

    if os.path.isfile(USTXCHECK):
        out = subprocess.run([USTXCHECK, path, back], capture_output=True, text=True, encoding="utf-8")
        ok(out.returncode == 0, "OpenUtau.Core loads the written .ustx files", out.stdout + out.stderr)
    else:
        print("  skip  OpenUtau.Core loader check (build tools/ustxcheck to enable)")
    return {"path": path, "ja": ja, "en": en}


async def live_tests(c: Client, tmp: str, ctx: dict):
    print("[live: bridge]")
    st = await c("openutau_status")
    ok(st["bridge"], "bridge reachable", st.get("hint"))
    if not st["project"]["saved"]:
        raise SystemExit("OpenUtau has unsaved changes; save or close that project before running --live")
    phs = await c("list_phonemizers")
    types = [p["type"] for p in phs]
    ok("OpenUtau.Plugin.Builtin.JapanesePresampPhonemizer" in types and "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer" in types,
       "phonemizers listed")
    ok(not any("OpenUtauMcp" in t for t in types), "bridge carrier is not in the phonemizer list")
    singers = await c("list_singers")
    ok({ctx["ja"]["id"], ctx["en"]["id"]} <= {s["id"] for s in singers}, "voicebank ids match OpenUtau singer ids")

    print("[live: project]")
    p = await c("open_project", path=ctx["path"])
    ok(len(p["tracks"]) == 2 and all(t["singer_found"] for t in p["tracks"]), "open file-created project", p["tracks"])
    ok(p["tracks"][1]["phonemizer"].endswith("EnXSampaPhonemizer"), "English track phonemizer kept")
    ok(len(p["voice_parts"]) == 2 and p["voice_parts"][0]["note_count"] == 14, "parts and notes loaded", p["voice_parts"])

    print("[live: notes]")
    before = (await c("list_notes", part=0))["notes"]
    r = await c("edit_notes", part=0, edits=[{"index": 0, "tone": "C5", "duration": 240}, {"index": 1, "position": 240}])
    ok(r["notes"][0]["tone"] == 72 and r["notes"][0]["duration"] == 240 and r["notes"][1]["position"] == 240, "edit notes in place")
    await c("undo")
    ok((await c("list_notes", part=0))["notes"][:2] == before[:2], "undo restores the edit (one undo step)")
    await c("redo")
    ok((await c("list_notes", part=0))["notes"][0]["tone"] == 72, "redo")

    r = await c("set_lyrics", part=0, text="ゆうやけ こやけで", start_index=0)
    notes = (await c("list_notes", part=0))["notes"]
    ok([n["lyric"] for n in notes[:7]] == ["ゆ", "う", "や", "け", "こ", "や", "け"], "Japanese lyrics on existing notes", r)
    r = await c("assign_lyrics", part=1, text="Twin-kle lit-tle star", start_tick=1920, durations=[240, 240, 480], tones=["G4", "G4", "D5"])
    ok(r["lyrics"] == ["twinkle", "+", "little", "+", "star"] and len(r["added"]) == 5, "English lyrics as new notes", r)

    print("[live: phonemes]")
    ph = await c("list_phonemes", part=0)
    # Whether each phoneme has a sample depends on the installed voicebank, so that is reported, not asserted.
    for part in (0, 1):
        ph = await c("list_phonemes", part=part)
        ok(ph["phonemes"] and all("has_oto" in x for x in ph["phonemes"]), f"phonemes listed for part {part}")
        print(f"  part {part}: {sum(x['has_oto'] for x in ph['phonemes'])}/{len(ph['phonemes'])} phonemes have samples")

    print("[live: expression + undo]")
    await c("set_note_expression", part=0, abbr="vel", value=150, indices=[0, 1])
    exps = [n["expressions"] for n in (await c("list_notes", part=0))["notes"][:3]]
    ok(any(e["abbr"] == "vel" and e["value"] == 150 for e in exps[0]) and not any(e["abbr"] == "vel" for e in exps[2]),
       "velocity set on chosen notes", exps)
    await c("undo")
    exps = [n["expressions"] for n in (await c("list_notes", part=0))["notes"][:2]]
    ok(not any(e["abbr"] == "vel" for es in exps for e in es), "undo removes the expression", exps)
    await c.error("set_note_expression", part=0, abbr="dyn", value=1)

    print("[live: tempo / key / tracks]")
    p = await c("set_tempo", bpm=150)
    ok(p["tempos"][0]["bpm"] == 150, "tempo set live")
    p = await c("set_key", key="D")
    ok(p["key"] == 2, "key set")
    p = await c("add_track", singer=ctx["ja"]["name"], name="Harmony")
    t = p["summary"]["tracks"][p["track"]]
    ok(t["singer_id"] == ctx["ja"]["id"] and t["phonemizer"].endswith("JapanesePresampPhonemizer") and t["renderer"],
       "add track applies singer default phonemizer + renderer", t)
    await c("update_track", track=p["track"], volume=-6, pan=20, mute=True)
    t = (await c("get_project"))["tracks"][p["track"]]
    ok(t["volume"] == -6 and t["pan"] == 20 and t["mute"], "update track mixer", t)
    await c("remove_track", track=p["track"])
    ok(len((await c("get_project"))["tracks"]) == 2, "remove track")

    print("[live: playback]")
    r = await c("play", tick=0, end_tick=480)
    await c("stop")
    ok(isinstance(r, dict) and "playing" in r, "play / stop")
    ok((await c("seek", tick=960))["position"] == 960, "seek")

    print("[live: export + save]")
    wav = os.path.join(tmp, "mix.wav")
    r = await c("export_wav", path=wav)
    size = os.path.getsize(wav) if os.path.exists(wav) else 0
    ok(size > 200_000, f"mixdown WAV rendered ({size} bytes)", r)
    r = await c("export_wav", path=os.path.join(tmp, "tracks", "t.wav"), per_track=True)
    ok(len(r["files"]) == 2 and all(f["bytes"] > 50_000 for f in r["files"]), "per-track WAVs", r)
    mid = os.path.join(tmp, "song.mid")
    ok((await c("export_midi", path=mid))["bytes"] > 0, "MIDI export")
    saved = os.path.join(tmp, "saved.ustx")
    p = await c("save_project", path=saved)
    ok(p["saved"] and os.path.isfile(saved), "save project")
    s = await c("ustx_summary", path=saved)
    ok(s["tempos"][0]["bpm"] == 150 and s["voice_parts"][1]["note_count"] == 8, "file tools read OpenUtau's saved file", s)


async def main():
    live = "--live" in sys.argv
    tmp = tempfile.mkdtemp(prefix="openutau-mcp-e2e-")
    params = StdioServerParameters(command=sys.executable, args=["-m", "openutau_mcp.server"],
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    try:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                init = await session.initialize()
                ok("openutau_status" in (init.instructions or ""), "server instructions present")
                c = Client(session)
                ctx = await file_tests(c, tmp)
                if live:
                    await live_tests(c, tmp, ctx)
        print(f"\nPASSED {len(passed)} checks ({'file + live' if live else 'file'})")
    finally:
        if os.environ.get("OPENUTAU_MCP_KEEP"):
            print(f"kept {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
