# AGENTS.md

Notes for AI agents: those that use this MCP server from any client, and those that work on this repository.
Claude users can install [skill/SKILL.md](skill/SKILL.md) as a skill instead; the content is the same.

## Using the server

- Call `openutau_status` first, then `usage_guide` once before a song task. `usage_guide` returns
  [skill/SKILL.md](skill/SKILL.md): the full workflow and quality rules. It is plain Markdown (the block between
  the first two `---` lines is Claude skill metadata and can be ignored), so it can also be pasted into a client's
  project rules or custom instructions.
- Essentials, also sent as the server's MCP instructions:
  - Live tools need OpenUtau running with the bridge plugin; `ustx_*`, `ust_*`, voicebank and utility tools work
    with OpenUtau closed.
  - 480 ticks = quarter note (1920 = one 4/4 bar). Note positions are relative to their part. Pitch is a MIDI number
    or a name (`C4` = 60). `part` counts voice parts only.
  - Lyrics: Japanese one mora per note; English one word per note, hyphenated syllables become `+` extender notes.
  - Pick the phonemizer that matches the voicebank (`rank_phonemizers`); `list_phonemes` with `has_oto: false`
    means the voicebank has no sample for that phoneme.
  - Each live edit is one undo step; save with `save_project`.
- `skill/mix_stems.py` and `skill/scripts/` (stem mix, backing-track analysis, reference check) are separate Python
  tools, not server tools; see the README.

## Working on this repository

- `src/openutau_mcp/server.py` defines every tool. Descriptions and errors are English, then Japanese. `ustx.py` and
  `ust.py` handle the file formats, `bridge.py` talks to the C# plugin in `plugin/`, `schema.py` simplifies the
  advertised tool schemas for strict clients.
- Tests: `.venv\Scripts\python tests\e2e_test.py` (file mode) and `.venv\Scripts\python tests\schema_check.py`.
  Never run `e2e_test.py --live` without the user's consent: it drives the running OpenUtau.
- After changing a tool signature, run `schema_check.py`; it must report 0 errors.
- Single-file build (exe with the plugin inside, plus the loose DLL):
  `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`. The plugin compiles against an installed OpenUtau.
- Keep the repository generic: no personal names, song titles or local paths in code, docs or tests.
