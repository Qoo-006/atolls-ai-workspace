# worktree の手順（作る → 確かめる → 統合する → 片付ける）

git のコマンドは Mac と Windows で同じ。Mac はターミナル、Windows は PowerShell か Git Bash で実行する。
例のリポジトリ（コードと変更の記録をまとめた場所）は myapp、統合先のブランチは main、仕事は sort-reverse。自分の名前に置き換える。
worktree はリポジトリの外（隣のフォルダー）に作る。中に作ると main 側から「gitに入っていないファイル」に見える。

## 0. 練習（初めてなら、本物のリポジトリの前に1周する）

```sh
mkdir worktree-practice
cd worktree-practice
git init -b main myapp
cd myapp
echo "hello" > README.md
git add README.md
git commit -m "init"
```

この下の 1〜5 を、この練習用のリポジトリで流す。終わったら worktree-practice フォルダーごとゴミ箱へ移す。

## 1. 作る（main を開いたフォルダーで）

```sh
git switch main
git worktree add -b task/sort-reverse ../myapp-sort-reverse main
git worktree list
```

- `-b` で新しいブランチを作り、`../myapp-sort-reverse` に取り出す
- 同じブランチは2か所で取り出せない。`is already used by worktree` と出たら、別のブランチ名にする（--force で越えない）
- worktree は git に入っているファイルだけが入った新しいフォルダー。`.env` のような git の外のファイルや、依存のインストールは作り直しが要る

AIはこのフォルダーの中で起動して、依頼書を渡す。

```sh
cd ../myapp-sort-reverse
claude      # Codex なら codex
```

### Claude Code の --worktree を使う場合

```sh
claude --worktree sort-reverse
```

- `.claude/worktrees/sort-reverse/` に作られ、ブランチ名は `worktree-sort-reverse` になる
- 起点は、既定ではリモートの既定ブランチ（多くは origin の main）。手元にだけあるコミット（変更の記録）は入らない。今の手元の状態から始めたいときは、設定の `worktree.baseRef` を `"head"` にするか、上の git worktree add で作る
- `.claude/worktrees/` を `.gitignore` に足しておく
- 会話を終えると、変更が無ければ（名前を付けていない会話なら）自動で消え、変更があれば残すか消すかを聞かれる。受け入れる前なら「残す」を選ぶ

### Codex の場合

ChatGPT のデスクトップアプリの Codex には worktree の機能があり、ブランチに乗らない状態（detached HEAD）で作られる。統合の前に作業場所の中で `git switch -c task/名前` でブランチ名を付ける。
Codex CLI（ターミナルで動かす版）での worktree の公式の記載は見つけられなかったので、CLI のときは上の git worktree add で作ったフォルダーで codex を起動する。

## 2. 受け入れの確認（仕事の作業場所の中で）

スクリプトを使う場合（キットのフォルダーはリポジトリの外に置き、パスを付けて呼ぶ。例は myapp と同じ階層に 06_並列作業 を置いたとき）

```sh
python3 ../06_並列作業/check_scope.py --base main --allow src/sort.py --allow tests/
```

git のコマンドだけで見る場合

```sh
git diff --name-only main...HEAD    # main から分かれた後にコミットした変更
git status --short                  # 未コミットの変更と、gitに入っていないファイル
git rev-list --count HEAD..main     # 0 なら main へ早送りできる
```

残りは 受け入れ確認表.md の項目を自分で確かめる。

## 3. main へ早送りで統合する（main を開いたフォルダーで）

```sh
git switch main
git merge --ff-only task/sort-reverse
```

`Not possible to fast-forward, aborting.` と出たら、main が先に進んでいる。統合はされていない。
仕事の作業場所の中で main を取り込み、確かめ方とこの確認をやり直してから、もう一度 3 を流す。

```sh
git merge --no-edit main
```

ここで `CONFLICT` と出たら、同じファイルを別の仕事が先に変えている。
解き方が分からなければ `git merge --abort` で取り込む前に戻し、順番表を見直す。

## 4. 片付ける（main を開いたフォルダーで）

```sh
git worktree remove ../myapp-sort-reverse
git branch -d task/sort-reverse
git worktree list
```

- 未コミットの変更や gitに入っていないファイルがあると、remove は止まる。--force を付けずに中身を確かめる
- `git branch -d` は main に統合済みのブランチだけを消す。統合していないと `not fully merged` で止まる
- worktree で取り出したままのブランチは消せない（`used by worktree`）。先に remove する
- ずっと使う作業場所（main を開いたフォルダーなど）は消さない。消すのは仕事ごとに作ったものだけ

## 5. フォルダーを手で動かしたり消したりした場合

```sh
git worktree list           # 消えたものに prunable と付く
git worktree prune -n -v    # 何が消えるかだけを見る
git worktree prune          # 記録を消す
```
