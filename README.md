# OpenUtau MCP

[日本語版 README はこちら](README.ja.md)

Lets AI assistants in any MCP client (Claude, Cursor, VS Code, Codex, Gemini CLI and others) operate [OpenUtau](https://github.com/openutau/OpenUtau) 0.1.576 on
Windows: write melodies and lyrics in **English and Japanese**, pick singers and phonemizers, check pronunciation,
play, and export WAV/MIDI.

Two parts:

| Part | What it does |
|---|---|
| `src/openutau_mcp` (Python, stdio MCP server) | 71 tools. Live tools talk to the plugin; `ustx_*`, `ust_*`, voicebank and utility tools work with OpenUtau closed. |
| `plugin/` (C# OpenUtau plugin DLL) | Starts automatically inside OpenUtau and serves a local control API on `127.0.0.1:51128`. |

## Requirements

- Windows, OpenUtau 0.1.576 (default install: `C:\Program Files\OpenUtau`). The released plugin is compiled against
  0.1.576; for another OpenUtau version, build the plugin yourself (below).
- Any MCP client that runs local (stdio) servers: Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, Cline,
  Continue, Codex CLI, Gemini CLI, LM Studio and others.

## Install

### 1. Server

Pick one way to get the server. Both give your MCP client a command to start.

**A. Single file, no Python needed.** Download `openutau-mcp.exe` from this repository's **Releases** page and put it
in a folder of your choice, e.g. `C:\Tools\`. The command is the path to the file: `C:\Tools\openutau-mcp.exe`. The
bridge plugin is inside the exe (step 2).

- Optional check that the download is intact: `Get-FileHash C:\Tools\openutau-mcp.exe` in PowerShell must print the
  same value as `SHA256SUMS.txt` on the release.
- The exe is not code-signed. If Windows blocks it: right-click the file, Properties, tick **Unblock**, OK.
- Japanese kanji-to-kana support (`pykakasi`) is built in.

**B. uvx, always the latest code.** Needs [uv](https://docs.astral.sh/uv/). Nothing to clone; uv downloads and caches
the server the first time the client starts it. The command is `uvx` with these arguments:

```text
--from "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP" openutau-mcp
```

**C. From a clone (to change the code).** Needs Python 3.11+ and uv:

```bash
git clone https://github.com/Tehcnological/openutauMCP openutau-mcp
```

```bash
cd openutau-mcp
uv venv -p 3.11
uv pip install -e ".[kanji]"
```

The command is then `C:\path\to\openutau-mcp\.venv\Scripts\openutau-mcp.exe`. Without the `kanji` extra, kanji lyrics
are kept and a warning is returned.

### 2. Bridge plugin

Live tools talk to a small plugin inside OpenUtau. Install it once (and again after an update), with OpenUtau closed:

- **Route A:** run `C:\Tools\openutau-mcp.exe install-plugin`. It copies the plugin into
  `Plugins\OpenUtauMcp\` inside OpenUtau's data folder, found the way OpenUtau finds it: `Documents\OpenUtau` for an
  installed OpenUtau (also when Documents is redirected, e.g. to OneDrive), the OpenUtau program folder for the zip
  (portable) version, or `%OPENUTAU_DATA_DIR%` if you set it.
- **Routes B and C:** download `OpenUtauMcp.Plugin.dll` from the same release and copy it into
  `Plugins\OpenUtauMcp\` in that same data folder (create the folder). Or build it (below).

Start OpenUtau (it loads plugins only at startup). The OpenUtau log shows
`OpenUtau MCP bridge listening on 127.0.0.1:51128`. In the piano roll, **Batch Edit → OpenUtau MCP: bridge status**
shows the same as a toast. The plugin adds nothing to the phonemizer list and changes no track.

**Build the plugin yourself** (another OpenUtau version, or code changes). It needs a .NET 10 SDK; to install one into
your user folder (no admin, no system changes):

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

Bridge not starting, with socket error 10013 in OpenUtau's log? Windows has reserved a port range that contains
the port (check with `netsh interface ipv4 show excludedportrange protocol=tcp`). Run `net stop winnat` then
`net start winnat` as administrator, or move the port with `OPENUTAU_MCP_PORT`.

### 3. Register with your MCP client

The examples use route A (`C:\Tools\openutau-mcp.exe`). For route B, replace the command line with `"command":
"uvx"` plus the `args` shown under each client. Restart the client (or reload its MCP servers) after editing a config
file. In JSON every `\` in a path is written `\\`.

**Claude Desktop, Cursor, Windsurf, Cline, Gemini CLI, LM Studio** all use the same JSON shape:

```json
{
  "mcpServers": {
    "openutau": {
      "command": "C:\\Tools\\openutau-mcp.exe",
      "args": []
    }
  }
}
```

Route B: `"command": "uvx", "args": ["--from", "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP", "openutau-mcp"]`.

| Client | Config file (merge the `openutau` entry into `mcpServers`) |
|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` (Settings, Developer, Edit Config). The Microsoft Store version may read `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json` instead. |
| Cursor | `%USERPROFILE%\.cursor\mcp.json` (all projects) or `.cursor\mcp.json` (one project). Add `"type": "stdio"` to the entry. |
| Windsurf (now Devin Desktop) | `%APPDATA%\devin\mcp_config.json`; older Windsurf versions: `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |
| Cline | Cline panel, MCP Servers, Configure, **Configure MCP Servers** opens `cline_mcp_settings.json` |
| Gemini CLI | `%USERPROFILE%\.gemini\settings.json`, or in one step: `gemini mcp add -s user openutau "C:\Tools\openutau-mcp.exe"` |
| LM Studio (0.3.17+) | `%USERPROFILE%\.lmstudio\mcp.json` (Program tab, Install, Edit mcp.json) |

**Claude Code** (one command, no file to edit):

```bash
claude mcp add --scope user openutau -- "C:\Tools\openutau-mcp.exe"
```

```bash
claude mcp add --scope user openutau -- uvx --from "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP" openutau-mcp
```

**VS Code (GitHub Copilot, agent mode)**: Command Palette, **MCP: Open User Configuration** (or `.vscode\mcp.json` in
a workspace). The top-level key is `servers`, not `mcpServers`:

```json
{
  "servers": {
    "openutau": {
      "type": "stdio",
      "command": "C:\\Tools\\openutau-mcp.exe"
    }
  }
}
```

Copilot's newer shared files, `%USERPROFILE%\.copilot\mcp-config.json` and `.mcp.json` in a workspace, take the
`mcpServers` shape above instead.

**Continue** (MCP works in agent mode only): create `.continue\mcpServers\openutau.yaml` in your workspace:

```yaml
name: OpenUtau
version: 0.0.1
schema: v1
mcpServers:
  - name: openutau
    type: stdio
    command: 'C:\Tools\openutau-mcp.exe'
```

Route B: `command: uvx` and `args: ["--from", "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP", "openutau-mcp"]`.

**Codex CLI**: add to `%USERPROFILE%\.codex\config.toml` (in TOML, single quotes keep `\` as is):

```toml
[mcp_servers.openutau]
command = 'C:\Tools\openutau-mcp.exe'
tool_timeout_sec = 300  # WAV export and launching OpenUtau can take longer than the 60 s default
```

Route B: `command = "uvx"` and `args = ["--from", "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP", "openutau-mcp"]`.
Or in one step: `codex mcp add openutau -- "C:\Tools\openutau-mcp.exe"` (then add `tool_timeout_sec` by hand).

Optional environment variables: `OPENUTAU_EXE` (path to OpenUtau.exe), `OPENUTAU_DATA_DIR` (default:
OpenUtau's own data folder, see step 2), `OPENUTAU_MCP_PORT` (default 51128; `launch_openutau` passes it on to the
OpenUtau it starts; set it for OpenUtau too if you start OpenUtau yourself).
Add them as `"env": {"OPENUTAU_EXE": "D:\\Apps\\OpenUtau\\OpenUtau.exe"}` in JSON, or
`env = { OPENUTAU_EXE = 'D:\Apps\OpenUtau\OpenUtau.exe' }` in TOML.

### Usage rules in every client

The server sends its essential rules (ticks, indexes, lyrics, phonemizer choice) as MCP instructions, and the
`usage_guide` tool returns the full workflow and quality guide ([skill/SKILL.md](skill/SKILL.md)). Some clients do
not pass server instructions to the model; if the assistant skips steps, ask it to "call usage_guide first". Claude
users can install `skill/SKILL.md` as a skill instead (e.g. `.claude/skills/openutau/SKILL.md`). See
[AGENTS.md](AGENTS.md) for agents and clients without skill support.

The server has 71 tools. VS Code allows 128 tools per request and Cursor used to send only the first 40, so if a
client warns about too many tools, turn off the ones you do not need (VS Code: the tools picker in Chat; Codex:
`enabled_tools`; Gemini CLI: `includeTools`).

### Song scripts (optional)

Copy `skill/mix_stems.py` and `skill/scripts/` next to the skill: `mix_stems.py` lines up, levels, pans and mixes
exported WAV stems into one stereo file; `scripts/` measures a backing track (tempo, beat, key, chords, an 8-bar
check WAV) and mixes vocals over it, and needs librosa (see SKILL.md section 5b). `scripts/reference_check.py`
compares a cover with the original recording: notes the singer sings 1-2.5 semitones off, long notes the singer
releases early, vocal-vs-backing balance per section, and loudness (Demucs optional). These scripts are not part of
the server or the exe.

### Build the single file yourself

```bash
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

It needs uv, a .NET 10 SDK and an OpenUtau install to compile the plugin against (`-OpenUtauDir "D:\Apps\OpenUtau"`
if it is not in `C:\Program Files\OpenUtau`; `-Dotnet $env:USERPROFILE\.dotnet-sdk10\dotnet.exe` for a user-folder
SDK). It writes `dist\openutau-mcp.exe` (PyInstaller, about 20 MB, plugin inside), `dist\OpenUtauMcp.Plugin.dll`,
`SHA256SUMS.txt` and the list of packages inside. Pushing a tag such as `v0.4.0` runs the same script on GitHub
Actions (against OpenUtau 0.1.576) and attaches the files to a draft release, which you publish by hand.

## Usage

Ask your assistant things like:

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
  parts, notes (`list_notes`, `add_notes`, `edit_notes` incl. phoneme timing overrides, `replace_lyrics`,
  `delete_notes`, `set_note_expression`),
  lyrics (`assign_lyrics`, `set_lyrics`), melody + lyrics in one call (`add_melody`, e.g. `A4:1 A4:1 B4:2 r:1`),
  `fit_part` (shrink/grow a part to its notes), `rank_phonemizers` (best phonemizer for a singer), pitch curves
  (`set_pitch`), expression curves (`get_curve`, `set_curve`, `clear_curve`), `refresh_singers`, `list_phonemes`, playback (`play`, `pause`, `stop`, `seek`),
  export (`export_midi`; `export_wav` writes 44.1 kHz 16-bit WAV as OpenUtau renders it, with no bit-depth option)
- **Files (OpenUtau may be closed)**: `ustx_create`, `ustx_summary`, `ustx_set_tempo`, `ustx_add_track`,
  `ustx_set_track_singer`, `ustx_add_voice_part`, `ustx_add_notes`, `ustx_list_notes`, `ustx_edit_notes`,
  `ustx_delete_notes`, `ustx_set_vibrato`, `ustx_assign_lyrics`, `ustx_add_melody`, `ustx_fit_part`, `ust_import` / `ust_export` (keep each note's VBR vibrato and PBS/PBW/PBY/PBM portamento)
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
.venv\Scripts\python tests\schema_check.py      # every tool schema against strict client rules
```

`schema_check.py` is a plain MCP client that lists the tools and checks each input schema against the strictest
documented rules of Gemini, Codex, VS Code and Cursor (rules listed at the top of the file). Set
`MCP_SERVER_EXE=dist\openutau-mcp.exe` to run `e2e_test.py` against the single-file build, or pass the exe to
`schema_check.py`.

The live test opens its own temporary project; it refuses to run if OpenUtau has unsaved changes. If
`tools/ustxcheck` is built (`dotnet build tools/ustxcheck -c Release -o .build/ustxcheck`), the file test also checks
that OpenUtau's own loader accepts the written `.ustx` files.

## License

MIT, see [LICENSE](LICENSE). Not affiliated with the OpenUtau project.
