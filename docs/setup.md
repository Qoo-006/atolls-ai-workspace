# 導入する

## 1. 道具と置き場を用意する

Python 3.11以上、Zed、Obsidian、CodexかClaude Codeを用意します。AIの導入と初回ログインは無料編または公式案内で進めてください。このキットはインストールや認証を代行しません。

- [Python公式ダウンロード](https://www.python.org/downloads/)
- [Codex CLI公式](https://learn.chatgpt.com/docs/codex/cli)
- [Claude Code公式](https://code.claude.com/docs/en/quickstart)
- [Zed公式](https://zed.dev/download)
- [Obsidian公式](https://obsidian.md/download)

配布されたNOフォルダーを、自分で管理する空の場所へ展開します。既存プロジェクトに重ねて展開しないでください。GitHubから受け取る場合は配布者から案内された実URLを使います。公開URLはこのキットに含まれていません。

Zedの「Open Folder」でNOフォルダー全体を開きます。コマンドパレットで `workspace: new terminal` を選び、NOのルート（README.mdがある場所）で次を実行してください。空白や日本語を含むパスは引用符で囲みます。

Mac:

```sh
cd "NO"
python3 --version
python3 scripts/no.py setup
python3 scripts/no.py doctor
```

Windows（PowerShell）:

```powershell
Set-Location -LiteralPath "NO"
py -3 --version
py -3 scripts/no.py setup
py -3 scripts/no.py doctor
```

すでにZedのターミナルがNOにいる場合、最初の移動コマンドは不要です。`py` が見つからず `python --version` で3.11以上が出る環境では、以下の `py -3` を `python` に置き換えます。`doctor: OK` が出たらローカル構成の確認は終了です。

`setup` は不足する雛形だけを作り、再実行しても既存の内容を変えません。設定ファイルやHOMEは変更しません。書き込み先は実行した `scripts/no.py` が入っているキットです。別のコピーを操作しないよう、開いているフォルダーを確認してください。

## 2. AIを始める

NOのルートのターミナルで `codex` または `claude` を起動します。両方を同時に使う必要はありません。[目的の調整](prompts.md) にあるプロンプトを最初に渡します。現在の権限設定と確認操作を使い、承認を省略するオプションは付けません。

設定を新規作成するHOME向けコマンドはありません。親フォルダーの指示や個人設定が適用される場合があるので、読み込み確認で競合も確かめます。Codexがローカルスキルを認識しない場合は、新しいNOコピーを自分の独立したGitリポジトリとして `git init` したうえで再起動して確認できます。この操作は自動では行いません。公開用配布物に `.git` は入れません。

## 3. Obsidianで同じ記録を開く

Obsidianの保管庫選択から「フォルダーを保管庫として開く」を選び、NOの中の `notes` を指定します。`school`、`work`、`personal` と `INDEX.md` が見えることを確認してください。新しい空の保管庫を別の場所に作ると、CLIが保存した記録はそこに表示されません。[Obsidian公式の保管庫案内](https://help.obsidian.md/vault)

保管庫のルートは `notes`、AIの作業場のルートはNOです。CLIの表示する `notes/personal/records/first-note.md` は、Obsidianでは `personal/records/first-note.md` として開きます。外部プラグインや同期サービスの設定は不要です。Obsidian自身が作る `.obsidian` は配布対象にしません。

## 4. 要約を保存して次回へ渡す

AIにno-recordを使うよう依頼し、要約案を確認してから保存します。手で試す場合:

Mac:

```sh
python3 scripts/no.py record --domain personal --name first-note --text "企画の目的を決めた。次は対象読者を確認する。"
python3 scripts/no.py search "対象読者" --domain personal
```

Windows:

```powershell
py -3 scripts/no.py record --domain personal --name first-note --text "企画の目的を決めた。次は対象読者を確認する。"
py -3 scripts/no.py search "対象読者" --domain personal
```

長いMarkdownはUTF-8の標準入力でも渡せます。Mac:

```sh
python3 scripts/no.py record --domain personal --name plan-summary --stdin <<'SUMMARY'
# 企画の要約
## 決まったこと
対象読者を先に決める。
## 次の作業
読者の困りごとを整理する。
SUMMARY
```

Windows（PowerShell。設定はこのターミナル内だけ）:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
@'
# 企画の要約
## 決まったこと
対象読者を先に決める。
## 次の作業
読者の困りごとを整理する。
'@ | py -3 scripts/no.py record --domain personal --name plan-summary --stdin
```

名前は1〜64文字の英数字・日本語・`_`・`-`を使います。拡張子は自動で `.md` を付けます。日付や短い内容を名前に入れ、同名エラーでは別の名前を選びます。Windowsの予約名は使えません。

保存したファイルを開き、ドメインの `INDEX.md` にリンクを追加します。例: `- [企画の要約](records/plan-summary.md)`。`HANDOFF.md` に目的・決定・未確認・次の作業・読む記録を残します。CLIはこの2つを自動更新しません。次の会話ではno-contextで検索し、必要な記録を読ませてから再開します。

## 困ったとき

`doctor` のmissingは配布漏れか、雛形の不足です。notesだけが不足しているならsetupを実行します。同名ファイルやリンクがある場合は、内容を確認してから新しいコピーで試してください。既存のものを自動削除する処理はありません。

検索が0件ならドメインと検索語を確認します。意味が近いだけの文章は一致しないため、別の単語でも試します。フックなしでも手動の保存・検索は使えます。フックを使う場合だけ [別設定の手順](hooks.md) へ進んでください。
