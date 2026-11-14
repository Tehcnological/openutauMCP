# OpenUtau MCP

[English README](README.md)

Claude（Claude Desktop / Claude Code）から Windows 版 [OpenUtau](https://github.com/openutau/OpenUtau) 0.1.576 を
操作するための MCP サーバーです。**日本語と英語**の歌詞でメロディを作り、歌手・音素化器を選び、発音を確認し、
再生や WAV / MIDI 書き出しができます。

構成は2つです。

| 部品 | 役割 |
|---|---|
| `src/openutau_mcp`（Python、stdio MCP サーバー） | 約60個のツール。ライブ操作はプラグイン経由。`ustx_*`・`ust_*`・音源・ユーティリティは OpenUtau を閉じたままでも使えます。 |
| `plugin/`（C# の OpenUtau プラグイン DLL） | OpenUtau 起動時に自動で動き、`127.0.0.1:51128` で操作 API を提供します。 |

## 必要なもの

- Windows、OpenUtau 0.1.576（既定のインストール先 `C:\Program Files\OpenUtau`）
- Python 3.11 以上と [uv](https://docs.astral.sh/uv/)（または pip）
- プラグインのビルドに .NET 10 SDK（OpenUtau の実行にはランタイムのみで可）

## インストール

### 1. Python サーバー

```bash
git clone <このリポジトリ> openutau-mcp
cd openutau-mcp
uv venv -p 3.11
uv pip install -e ".[kanji]"
```

`kanji` を付けると `pykakasi` が入り、漢字の歌詞をひらがなに変換します。無い場合は漢字のまま残し、警告を返します。

### 2. プラグインのビルドと配置

.NET 10 SDK が無い場合は、ユーザーフォルダーにインストールできます（管理者権限・システム変更なし）。

```powershell
Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile dotnet-install.ps1
.\dotnet-install.ps1 -Channel 10.0 -InstallDir $env:USERPROFILE\.dotnet-sdk10 -NoPath
```

インストール済みの OpenUtau を参照してビルドし（実行中のアプリと型が一致するように）、DLL をコピーします。

```powershell
& $env:USERPROFILE\.dotnet-sdk10\dotnet build plugin -c Release
# OpenUtau が別の場所にある場合は  -p:OpenUtauDir="D:\Apps\OpenUtau"  を追加
New-Item -ItemType Directory -Force "$env:USERPROFILE\Documents\OpenUtau\Plugins\OpenUtauMcp"
Copy-Item plugin\bin\Release\net10.0\OpenUtauMcp.Plugin.dll "$env:USERPROFILE\Documents\OpenUtau\Plugins\OpenUtauMcp\"
```

OpenUtau を再起動してください（プラグインは起動時にしか読み込まれません）。OpenUtau のログに
`OpenUtau MCP bridge listening on 127.0.0.1:51128` と出れば成功です。ピアノロールの
**Batch Edit メニュー → OpenUtau MCP: bridge status** でも状態がトーストで表示されます。
音素化器の一覧には何も追加されず、トラックも変更されません。

### 3. Claude への登録

**Claude Code**

```bash
claude mcp add openutau -- "C:\path\to\openutau-mcp\.venv\Scripts\openutau-mcp.exe"
```

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json` を編集：

```json
{
  "mcpServers": {
    "openutau": {
      "command": "C:\\path\\to\\openutau-mcp\\.venv\\Scripts\\openutau-mcp.exe"
    }
  }
}
```

任意の環境変数：`OPENUTAU_EXE`（OpenUtau.exe のパス）、`OPENUTAU_DATA_DIR`（既定 `Documents\OpenUtau`）、
`OPENUTAU_MCP_PORT`（既定 51128。OpenUtau 側にも同じ変数を設定するとプラグインのポートも変わります）。

ブリッジが起動しない場合（OpenUtau のログに socket error 10013）、そのポートが Windows の予約範囲に入っています
（`netsh interface ipv4 show excludedportrange protocol=tcp` で確認）。管理者で `net stop winnat` → `net start winnat`
を実行するか、`OPENUTAU_MCP_PORT` で別のポートにしてください。

`skill/SKILL.md` を Claude のスキルフォルダー（例 `.claude/skills/openutau/SKILL.md`）に置くと、手順付きのワークフローが使えます。
`skill/mix_stems.py` と `skill/scripts/` も同じフォルダーに置いてください。`mix_stems.py` は書き出した WAV ステムを
揃えてミックスします。`scripts/` は伴奏トラックの解析（テンポ・拍・キー・コード、8小節の確認用 WAV）と伴奏上のミックス用で、
librosa が必要です（SKILL.md 5b 参照）。

## 使い方

Claude にこう頼みます。

- 「OpenUtau の準備はできてる？」→ `openutau_status`
- 「日本語の音源で 128 BPM の新しい曲を作って、さくら さくら を A4 A4 B4 で歌わせて」
- 「英語の音源で英語トラックを追加して、'Hel-lo world' を C4 から四分音符で」
- 「パート1の発音を確認して」→ `list_phonemes`（`has_oto: false` はその音素のサンプルが無いという意味）
- 「デスクトップに WAV を書き出して」

基本：四分音符 = 480 ティック、音高 `C4` = 60、音符の位置はパート先頭からの相対値、1回の呼び出し = OpenUtau の取り消し1回分。

### 歌詞

- 日本語：1音符1モーラ。`きゃりーぱみゅぱみゅ、ちゃっと` → きゃ り + ぱ みゅ ぱ みゅ ちゃ っ と（「ー」は前の母音を伸ばす `+` 音符）、`夜空` → よ ぞ ら。
- 英語：1音符1単語。ハイフンで音節を区切ると、残りの音節は `+` の音符になります。
  `Hel-lo, beau-ti-ful world!` → hello + beautiful + + world。

### 音素化器の選び方

| 音源 | 音素化器 |
|---|---|
| 日本語 UTAU（単独音・連続音・CVVC） | `OpenUtau.Plugin.Builtin.JapanesePresampPhonemizer`（`JA VCV & CVVC`） |
| 英語 ARPAsing | `ArpasingPhonemizer`（`EN ARPA`） |
| 英語 VCCV | `EnglishVCCVPhonemizer`（`EN VCCV`） |
| 英語 X-SAMPA | `EnXSampaPhonemizer`（`EN X-SAMPA`） |
| 日本語音源で英語歌詞 | `ENtoJAPhonemizer`（`EN to JA`） |

### ツール一覧

- **アプリ**：`openutau_status`、`launch_openutau`、`close_openutau`
- **ライブ（ブリッジ経由）**：プロジェクト（`get_project`、`new_project`、`open_project`、`save_project`、
  `import_tracks`、`undo`、`redo`）、テンポ・拍子・キー、一覧（`list_singers`、`list_phonemizers`、
  `list_expressions`）、トラック、パート、音符（`list_notes`、`add_notes`、`edit_notes`、`replace_lyrics`、
  `delete_notes`、`set_note_expression`）、歌詞（`assign_lyrics`、`set_lyrics`）、メロディと歌詞を一度に（`add_melody`、例 `A4:1 A4:1 B4:2 r:1`）、
  `fit_part`（パートを音符に合わせて伸縮）、`rank_phonemizers`（歌手に最適な音素化器）、ピッチ曲線（`set_pitch`）、
  表情カーブ（`get_curve`、`set_curve`、`clear_curve`）、`refresh_singers`、`list_phonemes`、
  再生（`play`、`pause`、`stop`、`seek`）、書き出し（`export_wav`、`export_midi`）
- **ファイル（OpenUtau を閉じたままで可）**：`ustx_create`、`ustx_summary`、`ustx_set_tempo`、`ustx_add_track`、
  `ustx_set_track_singer`、`ustx_add_voice_part`、`ustx_add_notes`、`ustx_list_notes`、`ustx_edit_notes`、
  `ustx_delete_notes`、`ustx_set_vibrato`、`ustx_assign_lyrics`、`ustx_add_melody`、`ustx_fit_part`、`ust_import`、`ust_export`
- **音源**：`list_voicebanks`、`get_voicebank`、`search_oto`
- **ユーティリティ**：`note_to_midi`、`midi_to_note`、`beats_to_ticks`、`ticks_to_beats`、`split_lyrics`

## セキュリティ

プラグインは 127.0.0.1 だけで待ち受けます。すべてのリクエストに `X-OpenUtau-MCP: 1` ヘッダーが必要で、
`Origin` ヘッダーがあると 403 を返すため、ブラウザーの Web ページからは操作できません。
`open_project` / `new_project` は `force=true` が無い限り未保存の変更を破棄しません。

## テスト

```bash
.venv\Scripts\python tests\e2e_test.py          # ファイル・音源・ユーティリティ（stdio 経由）
.venv\Scripts\python tests\e2e_test.py --live   # 起動中の OpenUtau も操作（プラグインが必要）
```

ライブテストは一時プロジェクトを開きます。OpenUtau に未保存の変更があるときは実行しません。

## ライセンス

MIT — [LICENSE](LICENSE) を参照。OpenUtau プロジェクトとは無関係です。
