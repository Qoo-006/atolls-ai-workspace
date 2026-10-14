# 任意の開始時フック

基本の保存・検索にフックは不要です。このキットのフックは `SessionStart` に固定の案内を返すだけです。会話全文、ノート、認証情報を読まず、ファイルも書きません。選ぶドメインの情報を自動投入する機能ではありません。

## 設定する前に

`docs/hooks/` にツール・OS別のJSON例があります。既定ではどれも有効になりません。まず `python3 scripts/session_start.py`（Windowsは `py -3`）を実行し、JSONの `hookSpecificOutput` に `hookEventName: SessionStart` と `additionalContext` があることを確認します。

公式仕様では両ツールにSessionStartの文脈追加があります。Claude Codeの設定は `.claude/settings.local.json`、Codexは `.codex/hooks.json` を使う例を用意しました。Codexは信頼済みプロジェクトのローカル設定を対象とし、フック自体もレビューが必要です。[Claude Code公式フック](https://code.claude.com/docs/en/hooks)／[Codex公式フック](https://learn.chatgpt.com/docs/hooks)

## 自分で有効にする

Macは `*-mac.json`、Windowsは `*-windows.json` を選びます。Claude Codeの例は現行公式のexec形式（commandとargs）を使います。未対応の古い版で動作を約束しません。

コピー先がまだ存在しない場合にだけ、以下を実行します。既存設定がある場合、このコマンドは失敗して内容を保ちます。既存設定への自動マージは行いません。必要なら設定を読んで該当するSessionStart項目を手で追加してください。他のフックや権限設定を置き換えないでください。

Mac、Claude Code:

```sh
python3 -c 'from pathlib import Path; text=Path("docs/hooks/claude-mac.json").read_text(encoding="utf-8"); f=Path(".claude/settings.local.json").open("x", encoding="utf-8"); f.write(text); f.close()'
```

Mac、Codex:

```sh
python3 -c 'from pathlib import Path; Path(".codex").mkdir(exist_ok=True); text=Path("docs/hooks/codex-mac.json").read_text(encoding="utf-8"); f=Path(".codex/hooks.json").open("x", encoding="utf-8"); f.write(text); f.close()'
```

Windows、Claude Code:

```powershell
$hookBytes = [System.IO.File]::ReadAllBytes((Join-Path $PWD "docs/hooks/claude-windows.json"))
$hookFile = [System.IO.File]::Open((Join-Path $PWD ".claude/settings.local.json"), [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
try { $hookFile.Write($hookBytes, 0, $hookBytes.Length) } finally { $hookFile.Dispose() }
```

Windows、Codex:

```powershell
[System.IO.Directory]::CreateDirectory((Join-Path $PWD ".codex")) | Out-Null
$hookBytes = [System.IO.File]::ReadAllBytes((Join-Path $PWD "docs/hooks/codex-windows.json"))
$hookFile = [System.IO.File]::Open((Join-Path $PWD ".codex/hooks.json"), [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
try { $hookFile.Write($hookBytes, 0, $hookBytes.Length) } finally { $hookFile.Dispose() }
```

Windowsは各ブロックをまとめて実行し、エラーが出た場合はそこで止めます。コピーを手で行っても同じ設定になります。HOMEの設定は編集しません。

## 読み込みを確認する

AIは毎回NOのルートから起動します。Codexの例はセッションの作業ディレクトリに対する相対パスです。サブフォルダーから起動すると見つからないため、ルートへ戻してください。Claude Codeはプロジェクトのルートを公式のプレースホルダーで参照します。

新しいセッションで `/hooks` を開き、SessionStartの内容と実行コマンドを確認します。ツールの通常の確認手順で有効にし、再起動します。AIに開始時案内の識別子と内容を尋ね、`NO-START` が出るか確認します。自動読み込みを確認するにはフック一覧とログも照合してください。JSON単体のテストだけで、セッション内に届いたとは判断しません。

無効にする場合は `/hooks` で該当項目を無効にするか、このキット用のSessionStart項目だけを手で取り除きます。任意設定に加えた他の項目は残します。

2026-10-14に、MacのClaude Codeでは実際の会話に `NO-START` が届くことを確認しました。Codexでは、信頼済みにしていないプロジェクトで `codex exec` を実行した会話には届きませんでした。Codexで使う場合は、プロジェクトを信頼済みにし、`/hooks` でフックを確認して承認してから試してください。CLI本体の保存・検索はフックなしで使えます。公式仕様の確認日: 2026-10-13。
