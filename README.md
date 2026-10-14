# KnowBrain スターターキット

学校・仕事・個人の作業を分け、必要な記録を選んでAIへ渡すためのサンプルです。KnowBrainは、活動ごとの指示と記録をまとめる「脳」として使う作業フォルダーです。名前は、脳（のう）とKnow（知る）とBrainを掛けています。CodexかClaude Codeのどちらか一方から始められます。

配布先: [GitHubのサンプル](https://github.com/Qoo-006/atolls-ai-workspace)。

取り込みはAIに任せられます。下の「AIに取り込んでもらう」から始め、[自分の目的に合わせるプロンプト](docs/prompts.md) で用途を決めてください。手順の詳細は [導入手順](docs/setup.md) にあります。

## AIに取り込んでもらう

CodexかClaude Codeを導入済みなら、取り込み先にしたいフォルダーのターミナルで起動し、次の依頼文を渡します。

```text
次のGitHubのスターターキットを、自分用のAI作業環境として取り込みたいです。
https://github.com/Qoo-006/atolls-ai-workspace

今いるフォルダーの中に、KnowBrainという新しいフォルダーを作って取り込んでください。
同じ名前のフォルダーがあれば、上書きせずに止めて私に確認してください。
GitやPython 3.11以上が足りなければ、自分のOSでの入れ方を説明してください。

取り込んだらREADME.mdとdocs/setup.mdを読み、scripts/brain.pyのsetupとdoctorまで進めてください。
コマンドを実行する前に、何をするのかを説明してください。
フックの有効化、ホームフォルダーや既存の設定の変更はしないでください。
最後に、作られたファイルとdoctorの結果を報告してください。
```

AIがコマンドの実行を確認してきたら、内容を読んでから許可します。手で取り込む場合は、既存のプロジェクトと重ならない場所で次を実行します。Macの例です。Windowsは `python3` を `py -3` に置き換えます。

```sh
git clone https://github.com/Qoo-006/atolls-ai-workspace.git KnowBrain
cd KnowBrain
python3 scripts/brain.py setup
python3 scripts/brain.py doctor
```

取り込みが終わったら、その会話は閉じます。KnowBrainのフォルダーで新しくCodexかClaude Codeを起動すると、このキットの基本指示とスキルが読み込まれます。

## 主な機能

- 短い基本指示、Claude Codeの条件別ルール、両ツール用の記録・文脈検索スキルを使う。
- 既定の `school`・`work`・`personal` に加え、`domain add` で自分の活動のドメインを足し、それぞれに目的・索引・引継ぎ・要約を残す。
- Pythonの `setup` で不足する雛形を作り、`record` で確認した要約を新規保存する。
- `search` で指定ドメイン内のMarkdownを文字列検索し、相対パスと行番号を得る。
- `doctor` でローカルの構成とサンプルJSONを検査する。
- Obsidianで同じノートを読み返す。任意で開始時の案内フックを設定する。

## 自分のドメインを決める

ドメインは、AIに頼む活動の区分です。既定では学校（school）・仕事（work）・個人（personal）を用意しています。就活や部活のように別に分けたい活動があれば、自分で足せます。

まずAIに次のように頼み、自分の活動に合う分け方を一緒に決めます。

```text
このKnowBrainで使うドメイン（活動の区分）を、自分の使い方に合わせて決めたいです。
README.mdとnotes/INDEX.mdを読んでから、私がAIに頼みたい活動を一問ずつ聞いてください。

答えが揃ったら、ドメインの分け方を提案してください。
既定のschool・work・personalで足りる活動は、そのまま使ってください。
足りない活動だけ、フォルダー名（英小文字）と日本語の表示名の案を出してください。
例: job-hunt（就活）、club（部活）

私が確認してから、scripts/brain.py domain add <名前> --label <表示名> で作ってください。
使わない既定のドメインは消さずに残してください。
作ったら、PURPOSE.mdとdocs/rules/<名前>.mdに書く内容を一問ずつ一緒に決めてください。
```

手で足す場合は、キットのルートで次を実行します（Windowsは `python3` を `py -3` に置き換えます）。

```sh
python3 scripts/brain.py domain add job-hunt --label 就活
```

`notes/job-hunt/` の目的・索引・引継ぎと `records/`、`docs/rules/job-hunt.md`、Claude Code用の `.claude/rules/job-hunt.md` を作り、`notes/INDEX.md` にリンクを1行足します。名前は英小文字で始まる英小文字・数字・`-` の1〜32文字です。既存のファイルがあれば何も作らずに止まります。使わない既定のドメインは、消さずに残しておいて構いません。

## まず一度試す

ターミナルでキットのルートに移動して実行します。Macの例です。Windowsは `python3` を `py -3` に置き換えます。

```sh
python3 scripts/brain.py setup
python3 scripts/brain.py doctor
python3 scripts/brain.py record --domain personal --name first-note --text "今日は企画の目的を決めた。次は対象読者を確認する。"
python3 scripts/brain.py search "対象読者" --domain personal
```

`notes/personal/records/first-note.md` が見つかったら、そのファイルを開いて内容を確認します。同じ名前では上書きしません。繰り返す場合は別の名前を使ってください。

実際の作業は「目的を決める → そのドメインで作業する → AIに要約を依頼する → 内容を確認して保存する → 次回は検索して読む」の順で進めます。索引のリンクと引継ぎはAIか本人が手で更新します。

## 構成

| 場所 | 役割 |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | Codex / Claude Codeの基本指示 |
| `.zed/settings.json` | 編集用のプロジェクト設定 |
| `.claude/rules/` | 対象パスに応じたClaude Codeのルール |
| `.claude/skills/` / `.agents/skills/` | 各ツールのbrain-context / brain-record |
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
