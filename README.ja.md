# OpenUtau MCP

[English README](README.md)

MCP クライアント（Claude、Cursor、VS Code、Codex、Gemini CLI など）の AI アシスタントから Windows 版 [OpenUtau](https://github.com/openutau/OpenUtau) 0.1.576 を
操作するための MCP サーバーです。**日本語と英語**の歌詞でメロディを作り、歌手・音素化器を選び、発音を確認し、
再生や WAV / MIDI 書き出しができます。

構成は2つです。

| 部品 | 役割 |
|---|---|
| `src/openutau_mcp`（Python、stdio MCP サーバー） | 71 個のツール。ライブ操作はプラグイン経由。`ustx_*`・`ust_*`・音源・ユーティリティは OpenUtau を閉じたままでも使えます。 |
| `plugin/`（C# の OpenUtau プラグイン DLL） | OpenUtau 起動時に自動で動き、`127.0.0.1:51128` で操作 API を提供します。 |

## 必要なもの

- Windows、OpenUtau 0.1.576（既定のインストール先 `C:\Program Files\OpenUtau`）。リリースのプラグインは 0.1.576 向けに
  ビルドしています。別のバージョンの OpenUtau では、プラグインを自分でビルドしてください（下記）。
- ローカル（stdio）サーバーを起動できる MCP クライアント：Claude Desktop、Claude Code、Cursor、VS Code、Windsurf、
  Cline、Continue、Codex CLI、Gemini CLI、LM Studio など。

## インストール

### 1. サーバー

次のどれか1つを選びます。どれも、MCP クライアントに「起動するコマンド」を渡すだけです。

**A. 1ファイル版（Python 不要）。** このリポジトリの **Releases** ページから `openutau-mcp.exe` をダウンロードし、
好きなフォルダー（例 `C:\Tools\`）に置きます。コマンドはそのファイルのパス `C:\Tools\openutau-mcp.exe` です。
ブリッジプラグインも exe に入っています（手順 2）。

- ダウンロードが壊れていないかの確認（任意）：PowerShell で `Get-FileHash C:\Tools\openutau-mcp.exe` を実行し、
  リリースの `SHA256SUMS.txt` と同じ値になることを確かめます。
- exe にはコード署名がありません。Windows にブロックされたら、ファイルを右クリック、プロパティ、
  **許可する** にチェックして OK。
- 漢字をかなに変換する機能（`pykakasi`）が入っています。

**B. uvx（常に最新のコード）。** [uv](https://docs.astral.sh/uv/) が必要です。クローン不要で、クライアントが初めて
起動したときに uv がサーバーをダウンロードしてキャッシュします。コマンドは `uvx`、引数は次のとおりです。

```text
--from "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP" openutau-mcp
```

**C. クローンから（コードを変更する場合）。** Python 3.11 以上と uv が必要です。

```bash
git clone https://github.com/Tehcnological/openutauMCP openutau-mcp
```

```bash
cd openutau-mcp
uv venv -p 3.11
uv pip install -e ".[kanji]"
```

コマンドは `C:\path\to\openutau-mcp\.venv\Scripts\openutau-mcp.exe` になります。`kanji` を付けないと漢字の歌詞は
そのまま残り、警告が返ります。

### 2. ブリッジプラグイン

ライブ操作は OpenUtau の中の小さなプラグインと通信します。OpenUtau を閉じた状態で一度だけ（更新後にもう一度）入れます。

- **A の場合：** `C:\Tools\openutau-mcp.exe install-plugin` を実行します。プラグインが
  `Documents\OpenUtau\Plugins\OpenUtauMcp\`（または `%OPENUTAU_DATA_DIR%\Plugins\OpenUtauMcp\`）にコピーされます。
- **B・C の場合：** 同じリリースから `OpenUtauMcp.Plugin.dll` をダウンロードし、
  `%USERPROFILE%\Documents\OpenUtau\Plugins\OpenUtauMcp\`（無ければ作成）にコピーします。またはビルドします（下記）。

OpenUtau を起動します（プラグインは起動時にしか読み込まれません）。OpenUtau のログに
`OpenUtau MCP bridge listening on 127.0.0.1:51128` と出れば成功です。ピアノロールの
**Batch Edit メニュー → OpenUtau MCP: bridge status** でも状態がトーストで表示されます。
音素化器の一覧には何も追加されず、トラックも変更されません。

**プラグインを自分でビルドする**（別バージョンの OpenUtau、またはコードを変更した場合）。.NET 10 SDK が必要です。
ユーザーフォルダーにインストールできます（管理者権限・システム変更なし）。

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

ブリッジが起動しない場合（OpenUtau のログに socket error 10013）、そのポートが Windows の予約範囲に入っています
（`netsh interface ipv4 show excludedportrange protocol=tcp` で確認）。管理者で `net stop winnat` → `net start winnat`
を実行するか、`OPENUTAU_MCP_PORT` で別のポートにしてください。

### 3. MCP クライアントへの登録

例は A の `C:\Tools\openutau-mcp.exe` です。B の場合は、コマンドを `"command": "uvx"` にし、各クライアントの下に
書いた `args` を加えます。設定ファイルを編集したら、クライアントを再起動（または MCP サーバーを再読み込み）します。
JSON ではパスの `\` を `\\` と書きます。

**Claude Desktop・Cursor・Windsurf・Cline・Gemini CLI・LM Studio** は同じ JSON 形式です。

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

B の場合：`"command": "uvx", "args": ["--from", "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP", "openutau-mcp"]`。

| クライアント | 設定ファイル（`mcpServers` に `openutau` の項目を追加） |
|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json`（設定、開発者、構成を編集）。Microsoft Store 版は `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json` を読むことがあります。 |
| Cursor | `%USERPROFILE%\.cursor\mcp.json`（全プロジェクト）または `.cursor\mcp.json`（1プロジェクト）。項目に `"type": "stdio"` を追加。 |
| Windsurf（現 Devin Desktop） | `%APPDATA%\devin\mcp_config.json`。古い Windsurf は `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |
| Cline | Cline パネル、MCP Servers、Configure、**Configure MCP Servers** で `cline_mcp_settings.json` が開きます |
| Gemini CLI | `%USERPROFILE%\.gemini\settings.json`。1行で登録するなら `gemini mcp add -s user openutau "C:\Tools\openutau-mcp.exe"` |
| LM Studio（0.3.17 以上） | `%USERPROFILE%\.lmstudio\mcp.json`（Program タブ、Install、Edit mcp.json） |

**Claude Code**（コマンド1行、ファイル編集なし）

```bash
claude mcp add --scope user openutau -- "C:\Tools\openutau-mcp.exe"
```

```bash
claude mcp add --scope user openutau -- uvx --from "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP" openutau-mcp
```

**VS Code（GitHub Copilot のエージェントモード）**：コマンドパレットで **MCP: Open User Configuration**
（ワークスペース単位なら `.vscode\mcp.json`）。最上位のキーは `mcpServers` ではなく `servers` です。

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

Copilot の新しい共通ファイル `%USERPROFILE%\.copilot\mcp-config.json` とワークスペースの `.mcp.json` は、上の
`mcpServers` 形式を使います。

**Continue**（MCP はエージェントモードのみ）：ワークスペースに `.continue\mcpServers\openutau.yaml` を作ります。

```yaml
name: OpenUtau
version: 0.0.1
schema: v1
mcpServers:
  - name: openutau
    type: stdio
    command: 'C:\Tools\openutau-mcp.exe'
```

B の場合：`command: uvx` と `args: ["--from", "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP", "openutau-mcp"]`。

**Codex CLI**：`%USERPROFILE%\.codex\config.toml` に追加します（TOML では単一引用符で囲むと `\` をそのまま書けます）。

```toml
[mcp_servers.openutau]
command = 'C:\Tools\openutau-mcp.exe'
tool_timeout_sec = 300  # WAV 書き出しや OpenUtau の起動は既定の 60 秒を超えることがあります
```

B の場合：`command = "uvx"` と `args = ["--from", "openutau-mcp[kanji] @ git+https://github.com/Tehcnological/openutauMCP", "openutau-mcp"]`。
1行で登録するなら `codex mcp add openutau -- "C:\Tools\openutau-mcp.exe"`（`tool_timeout_sec` は後から手で追加）。

任意の環境変数：`OPENUTAU_EXE`（OpenUtau.exe のパス）、`OPENUTAU_DATA_DIR`（既定 `Documents\OpenUtau`）、
`OPENUTAU_MCP_PORT`（既定 51128。OpenUtau 側にも同じ変数を設定するとプラグインのポートも変わります）。
JSON では `"env": {"OPENUTAU_EXE": "D:\\Apps\\OpenUtau\\OpenUtau.exe"}`、TOML では
`env = { OPENUTAU_EXE = 'D:\Apps\OpenUtau\OpenUtau.exe' }` と書きます。

### どのクライアントでも使い方のルールを使う

サーバーは基本ルール（ティック、番号、歌詞、音素化器の選び方）を MCP の instructions として送り、`usage_guide`
ツールは手順と品質ルールの全文（[skill/SKILL.md](skill/SKILL.md)）を返します。instructions をモデルに渡さない
クライアントもあるので、手順が飛ばされるときは「まず usage_guide を呼んで」と頼んでください。Claude では
`skill/SKILL.md` をスキルとして入れることもできます（例 `.claude/skills/openutau/SKILL.md`）。スキルに対応しない
エージェントやクライアント向けの説明は [AGENTS.md](AGENTS.md) にあります。

ツールは 71 個あります。VS Code は1回のリクエストで 128 個まで、Cursor は以前は最初の 40 個しか送らなかったので、
ツールが多すぎると警告されたら使わないものをオフにします（VS Code：チャットのツール選択、Codex：`enabled_tools`、
Gemini CLI：`includeTools`）。

### 曲作り用スクリプト（任意）

`skill/mix_stems.py` と `skill/scripts/` をスキルと同じフォルダーに置いてください。`mix_stems.py` は書き出した WAV
ステムを揃えてミックスします。`scripts/` は伴奏トラックの解析（テンポ・拍・キー・コード、8小節の確認用 WAV）と
伴奏上のミックス用で、librosa が必要です（SKILL.md 5b 参照）。`scripts/reference_check.py` はカバー曲を原曲と
比べます（1〜2.5 半音ずれて歌われている音符、歌手が早めに切る長い音、セクションごとのボーカルと伴奏の音量差、
ラウドネス。Demucs は任意）。これらのスクリプトはサーバーにも exe にも入っていません。

### 1ファイル版を自分でビルドする

```bash
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

uv、.NET 10 SDK、プラグインのビルドに使う OpenUtau のインストールが必要です（`C:\Program Files\OpenUtau` 以外なら
`-OpenUtauDir "D:\Apps\OpenUtau"`、ユーザーフォルダーの SDK なら `-Dotnet $env:USERPROFILE\.dotnet-sdk10\dotnet.exe`）。
`dist\openutau-mcp.exe`（PyInstaller、約 20 MB、プラグイン入り）、`dist\OpenUtauMcp.Plugin.dll`、`SHA256SUMS.txt`、
中に入ったパッケージの一覧を作ります。`v0.4.0` のようなタグを push すると GitHub Actions が同じスクリプトを
（OpenUtau 0.1.576 を使って）実行し、ファイルを下書きのリリースに添付します。公開は手動です。

## 使い方

AI アシスタントにこう頼みます。

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
  `list_expressions`）、トラック、パート、音符（`list_notes`、`add_notes`、`edit_notes`（音素タイミングの上書きも可）、`replace_lyrics`、
  `delete_notes`、`set_note_expression`）、歌詞（`assign_lyrics`、`set_lyrics`）、メロディと歌詞を一度に（`add_melody`、例 `A4:1 A4:1 B4:2 r:1`）、
  `fit_part`（パートを音符に合わせて伸縮）、`rank_phonemizers`（歌手に最適な音素化器）、ピッチ曲線（`set_pitch`）、
  表情カーブ（`get_curve`、`set_curve`、`clear_curve`）、`refresh_singers`、`list_phonemes`、
  再生（`play`、`pause`、`stop`、`seek`）、書き出し（`export_midi`、`export_wav`：OpenUtau の出力どおり 44.1 kHz 16 bit の WAV、ビット深度は選べません）
- **ファイル（OpenUtau を閉じたままで可）**：`ustx_create`、`ustx_summary`、`ustx_set_tempo`、`ustx_add_track`、
  `ustx_set_track_singer`、`ustx_add_voice_part`、`ustx_add_notes`、`ustx_list_notes`、`ustx_edit_notes`、
  `ustx_delete_notes`、`ustx_set_vibrato`、`ustx_assign_lyrics`、`ustx_add_melody`、`ustx_fit_part`、`ust_import` / `ust_export`（音符ごとの VBR ビブラートと PBS/PBW/PBY/PBM ピッチを保持）
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
.venv\Scripts\python tests\schema_check.py      # 全ツールのスキーマを厳しいクライアントの規則で検査
```

`schema_check.py` はツール一覧を取得する普通の MCP クライアントで、各入力スキーマを Gemini・Codex・VS Code・Cursor の
最も厳しい規則で検査します（規則はファイル冒頭に記載）。`MCP_SERVER_EXE=dist\openutau-mcp.exe` を設定すると `e2e_test.py` を
1ファイル版に対して実行します。`schema_check.py` には exe のパスを渡せます。

ライブテストは一時プロジェクトを開きます。OpenUtau に未保存の変更があるときは実行しません。

## ライセンス

MIT。[LICENSE](LICENSE) を参照。OpenUtau プロジェクトとは無関係です。
