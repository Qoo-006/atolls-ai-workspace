# NO スターターキット

学校・仕事・個人の作業を分け、必要な記録を選んでAIへ渡すためのサンプルです。NOは全体の窓口の名前です。CodexかClaude Codeのどちらか一方から始められます。

配布先: [GitHubのサンプル](https://github.com/Qoo-006/atolls-ai-workspace)。

まず [導入手順](docs/setup.md) を開き、[自分の目的に合わせるプロンプト](docs/prompts.md) で用途を決めてください。

## 主な機能

- 短い基本指示、Claude Codeの条件別ルール、両ツール用の記録・文脈検索スキルを使う。
- `notes/school`、`notes/work`、`notes/personal` に目的・索引・引継ぎ・要約を残す。
- Pythonの `setup` で不足する雛形を作り、`record` で確認した要約を新規保存する。
- `search` で指定ドメイン内のMarkdownを文字列検索し、相対パスと行番号を得る。
- `doctor` でローカルの構成とサンプルJSONを検査する。
- Obsidianで同じノートを読み返す。任意で開始時の案内フックを設定する。

## まず一度試す

ターミナルでキットのルートに移動して実行します。Macの例です。Windowsは `python3` を `py -3` に置き換えます。

```sh
python3 scripts/no.py setup
python3 scripts/no.py doctor
python3 scripts/no.py record --domain personal --name first-note --text "今日は企画の目的を決めた。次は対象読者を確認する。"
python3 scripts/no.py search "対象読者" --domain personal
```

`notes/personal/records/first-note.md` が見つかったら、そのファイルを開いて内容を確認します。同じ名前では上書きしません。繰り返す場合は別の名前を使ってください。

実際の作業は「目的を決める → そのドメインで作業する → AIに要約を依頼する → 内容を確認して保存する → 次回は検索して読む」の順で進めます。索引のリンクと引継ぎはAIか本人が手で更新します。

## 構成

| 場所 | 役割 |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | Codex / Claude Codeの基本指示 |
| `.zed/settings.json` | 編集用のプロジェクト設定 |
| `.claude/rules/` | 対象パスに応じたClaude Codeのルール |
| `.claude/skills/` / `.agents/skills/` | 各ツールのno-context / no-record |
| `docs/rules/` | 必要なときに読む共通の説明 |
| `notes/` | Obsidianで開く記録 |
| `scripts/` | Python標準ライブラリだけで動くCLI（文字のコマンドで操作するプログラム）と任意フック |
| `docs/hooks/` | ツール・OS別の任意設定例（既定では無効） |
| `tests/` | 一時フォルダーで動く検証 |

## 限界

会話全文の自動保存、AIによる自動要約、意味検索、グラフ検索、複数端末の同期は実装していません。検索は大文字小文字を区別しない文字列一致です。該当ドメインの `.md` だけを読み、最大30件の一致行を表示します。`--limit` で件数を変えられます。

ドメイン分けは作業時に読む情報を選ぶための仕組みです。CLIは別ドメインを検索せず、リンク先も追いませんが、同じフォルダーを開いたAIやObsidianには他ドメインを読む能力があります。アクセス権の隔離が必要な資料は別の作業場で扱ってください。読み込んだ本文は通常のオンライン利用でモデルへ渡り得ます。

CLIの書き込み先はこのキット内です。ノート雛形と記録以外の設定は変更しません。既存ファイルは置き換えず、シンボリックリンク・ジャンクションを使った保存先も拒否します。同時に別プロセスがディレクトリを差し替える状況の防御や、AIの編集範囲の強制は行いません。

`doctor` はローカルのファイルとJSONだけを検査し、ログインやAIの読み込みまでは確かめません。AIの会話で読み込まれたかは [確認手順](docs/prompts.md) で確かめてください。2026-10-14に、MacのClaude Code（基本指示・条件別ルール・二つのスキル・開始時フック）とCodex（基本指示・二つのスキル）で、実際の会話に読み込まれることを確認しています。

追加のサービス、API（外部サービスを呼び出すための窓口）のキー、ネットワーク接続は、CLIには要りません。AIの利用料金とアカウントは別途必要です。MITライセンスで配布します。条件は [LICENSE](LICENSE) を確認してください。

検証を再実行する場合は `python3 -B -m unittest discover -s tests -v` を使います。公開前の検査は `python3 -B scripts/check_distribution.py` です。内容の確認も配布者が行ってください。
