# OpenUtau MCP

[日本語版 README はこちら](README.ja.md)

Lets Claude (Claude Desktop / Claude Code) operate [OpenUtau](https://github.com/openutau/OpenUtau) 0.1.576 on
Windows: write melodies and lyrics in **English and Japanese**, pick singers and phonemizers, check pronunciation,
play, and export WAV/MIDI.

Two parts:

| Part | What it does |
|---|---|
| `src/openutau_mcp` (Python, stdio MCP server) | ~60 tools. Live tools talk to the plugin; `ustx_*`, `ust_*`, voicebank and utility tools work with OpenUtau closed. |
| `plugin/` (C# OpenUtau plugin DLL) | Starts automatically inside OpenUtau and serves a local control API on `127.0.0.1:51128`. |

## Requirements

- Windows, OpenUtau 0.1.576 (default install: `C:\Program Files\OpenUtau`)
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or pip)
- .NET 10 SDK to build the plugin (only the runtime is needed to run OpenUtau)

## Install

### 1. Python server

```bash
git clone <this repo> openutau-mcp
cd openutau-mcp
uv venv -p 3.11
uv pip install -e ".[kanji]"
```

The `kanji` extra installs `pykakasi`, which turns kanji lyrics into hiragana. Without it kanji are kept and a
warning is returned.

### 2. Build and install the plugin

If you have no .NET 10 SDK, install one into your user folder (no admin, no system changes):

```powershell
Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile dotnet-install.ps1
.\dotnet-install.ps1 -Channel 10.0 -InstallDir $env:USERPROFILE\.dotnet-sdk10 -NoPath
```

Build against your installed OpenUtau (so the types match the running app) and copy the DLL:

```powershell
& $env:USERPROFILE\.dotnet-sdk10\dotnet build plugin -c Release
# OpenUtau somewhere else?  add  -p:OpenUtauDir="D:\Apps\OpenUtau"
New-Item -ItemType Directory -Force "$env:USERPROFILE\Documents\OpenUtau\Plugins\OpenUtauMcp"
Copy-Item plugin\bin\Release\net10.0\OpenUtauMcp.Plugin.dll "$env:USERPROFILE\Documents\OpenUtau\Plugins\OpenUtauMcp\"
```

Restart OpenUtau (it loads plugins only at startup). The OpenUtau log shows
`OpenUtau MCP bridge listening on 127.0.0.1:51128`. In the piano roll, **Batch Edit → OpenUtau MCP: bridge status**
shows the same as a toast. The plugin adds nothing to the phonemizer list and changes no track.

### 3. Register with Claude

**Claude Code**

```bash
claude mcp add openutau -- "C:\path\to\openutau-mcp\.venv\Scripts\openutau-mcp.exe"
```

**Claude Desktop** — edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "openutau": {
      "command": "C:\\path\\to\\openutau-mcp\\.venv\\Scripts\\openutau-mcp.exe"
    }
  }
}
```

Optional environment variables: `OPENUTAU_EXE` (path to OpenUtau.exe), `OPENUTAU_DATA_DIR` (default
`Documents\OpenUtau`), `OPENUTAU_MCP_PORT` (default 51128; set the same variable for OpenUtau to move the plugin).

Optionally copy `skill/SKILL.md` into your Claude skills folder (e.g. `.claude/skills/openutau/SKILL.md`) for
step-by-step workflows.

## Usage

Ask Claude things like:

- "Is OpenUtau ready?" → `openutau_status`
- "Make a new song with my Japanese voicebank at 128 BPM and sing さくら さくら on A4 A4 B4."
- "Add an English track with my English voicebank and sing 'Hel-lo world' as quarter notes from C4."
- "Check the pronunciation of part 1." → `list_phonemes` (`has_oto: false` = no sample for that phoneme)
- "Export a WAV to my desktop."

Basics: 480 ticks = one quarter note; pitch `C4` = 60; note positions are relative to their part; one tool call = one
undo step in OpenUtau.

### Lyrics

- Japanese: one mora per note. `きゃりーぱみゅぱみゅ、ちゃっと` → きゃ り + ぱ みゅ ぱ みゅ ちゃ っ と (ー holds the previous vowel as a `+` note); `夜空` → よ ぞ ら.
- English: one word per note; hyphens mark syllables, extra syllables become `+` notes.
  `Hel-lo, beau-ti-ful world!` → hello + beautiful + + world.

### Phonemizers

| Voicebank | Phonemizer |
|---|---|
| Japanese UTAU (CV / VCV / CVVC) | `OpenUtau.Plugin.Builtin.JapanesePresampPhonemizer` (`JA VCV & CVVC`) |
| English ARPAsing | `ArpasingPhonemizer` (`EN ARPA`) |
| English VCCV | `EnglishVCCVPhonemizer` (`EN VCCV`) |
| English X-SAMPA | `EnXSampaPhonemizer` (`EN X-SAMPA`) |
| English lyrics on a Japanese bank | `ENtoJAPhonemizer` (`EN to JA`) |

### Tool groups

- **App**: `openutau_status`, `launch_openutau`, `close_openutau`
- **Live (bridge)**: project (`get_project`, `new_project`, `open_project`, `save_project`, `import_tracks`, `undo`,
  `redo`), tempo/time signature/key, catalog (`list_singers`, `list_phonemizers`, `list_expressions`), tracks,
  parts, notes (`list_notes`, `add_notes`, `edit_notes`, `replace_lyrics`, `delete_notes`, `set_note_expression`),
  lyrics (`assign_lyrics`, `set_lyrics`), melody + lyrics in one call (`add_melody`, e.g. `A4:1 A4:1 B4:2 r:1`),
  `fit_part` (shrink/grow a part to its notes), `rank_phonemizers` (best phonemizer for a singer), `list_phonemes`, playback (`play`, `pause`, `stop`, `seek`),
  export (`export_wav`, `export_midi`)
- **Files (OpenUtau may be closed)**: `ustx_create`, `ustx_summary`, `ustx_set_tempo`, `ustx_add_track`,
  `ustx_set_track_singer`, `ustx_add_voice_part`, `ustx_add_notes`, `ustx_list_notes`, `ustx_edit_notes`,
  `ustx_delete_notes`, `ustx_set_vibrato`, `ustx_assign_lyrics`, `ustx_add_melody`, `ustx_fit_part`, `ust_import`, `ust_export`
- **Voicebanks**: `list_voicebanks`, `get_voicebank`, `search_oto`
- **Utilities**: `note_to_midi`, `midi_to_note`, `beats_to_ticks`, `ticks_to_beats`, `split_lyrics`

## Security

The plugin listens on 127.0.0.1 only. Every request must carry `X-OpenUtau-MCP: 1` and no `Origin` header,
otherwise it gets 403, so web pages in your browser cannot drive it. `open_project` / `new_project` refuse to
discard unsaved changes unless `force=true`.

## Tests

```bash
.venv\Scripts\python tests\e2e_test.py          # file, voicebank and utility tools over stdio
.venv\Scripts\python tests\e2e_test.py --live   # also drives the running OpenUtau (needs the plugin)
```

The live test opens its own temporary project; it refuses to run if OpenUtau has unsaved changes. If
`tools/ustxcheck` is built (`dotnet build tools/ustxcheck -c Release -o .build/ustxcheck`), the file test also checks
that OpenUtau's own loader accepts the written `.ustx` files.

## License

MIT — see [LICENSE](LICENSE). Not affiliated with the OpenUtau project.
