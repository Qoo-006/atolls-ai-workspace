# settings.json に足すフックの例

`~/.claude/settings.json`（自分のパソコンの全プロジェクトに効く Claude Code の設定）に足す例です。
`$HOME/ai-tools/save_log.py` と `$HOME/Documents/MyVault/AIログ` は記入例なので、自分の置き場所に書き換えてください。

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/ai-tools/save_log.py\" --out \"$HOME/Documents/MyVault/AIログ\""
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/ai-tools/save_log.py\" --out \"$HOME/Documents/MyVault/AIログ\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

## 2つのフックを登録する理由

- Stop は、AIが返事を終えるたびに動きます。会話の途中でもファイルが最新になります。
- ただし公式の文書によると、ユーザーが途中で止めた（中断した）ときは Stop が動きません。
- SessionEnd は会話を閉じたとき（終了、`/clear`、`/resume` で切り替えたとき など）に動きます。中断したまま閉じた会話も、ここで書き直されます。
- SessionEnd のフックは、既定では全体で1.5秒しか待ってもらえません。`"timeout": 10` を付けると、待ち時間が10秒まで延びます（上限60秒）。

## 既存の設定に足すとき

先にバックアップを取ります。

```sh
cp ~/.claude/settings.json ~/.claude/settings.json.bak
```

| 今の settings.json | 足し方 |
|---|---|
| ファイルが無い | 上の例をそのまま保存する |
| `"hooks"` が無い | いちばん外側の `{ }` の中に、`"hooks": { ... }` を1項目として足す（前の項目の後ろにカンマを付ける） |
| `"hooks"` はあるが `"Stop"` が無い | `"hooks"` の中に `"Stop": [ ... ]` と `"SessionEnd": [ ... ]` を足す |
| `"Stop"` がすでにある | `"Stop"` の `[ ]` の中に、`{ "hooks": [ ... ] }` をもう1つ足す（既存のフックは消さない） |

足したら、JSONとして壊れていないかを確かめます。

```sh
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo OK
```

`OK` と出なければ、カンマの過不足か、かっこの閉じ忘れです。バックアップから戻して、もう一度足してください。

Claude Code を起動して `/hooks` を開くと、登録されたフックを一覧で確かめられます（見るだけの画面です）。

## 注意

- パスに空白が入るとき（iCloud の Obsidian 保管庫など）は、例のように `\"` で囲みます。
- フックは自分のユーザー権限でそのままコマンドを実行します。中身を読んで理解したスクリプトだけを登録してください。
- 初めて開くフォルダーでは、フォルダーを信頼するかの確認に答えるまで、フックは動きません。
- Windows では `python3` を `py -3` に置き換える必要があるかもしれません。Windows の実機では確かめていません。

## 公式の文書

- フック: https://code.claude.com/docs/en/hooks
- 会話ログの保存場所と自動削除: https://code.claude.com/docs/en/claude-directory
