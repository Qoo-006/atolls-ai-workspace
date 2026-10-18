#!/usr/bin/env python3
"""Claude Codeの会話ログ（.jsonl）から、自分が入力した発言だけをMarkdownに書き出す

  python3 extract_my_messages.py ~/.claude/projects/<プロジェクトのフォルダー> -o my_messages.md --since 2026-09-01

サブエージェントへの指示、ツールの結果、コマンドの出力、自動で入る補足は除く
別のAIや自動実行から送った指示もログ上は同じ「user」になるので、書き出した後に目で確かめる
出力先に同じ名前のファイルがあれば上書きせずに止まる
終了コード: 0＝書き出した 1＝発言が0件（ファイルは作らない） 2＝フォルダー・日付・出力先の指定が正しくない
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

SKIP_PREFIXES = ("<command-", "<local-command-", "<system-reminder>", "<task-notification>", "Caveat:")


def texts_from(content):
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return []


def local_time(stamp):
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return None


def iter_messages(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "user" or rec.get("isSidechain") or rec.get("isMeta"):
                continue
            for text in texts_from(rec.get("message", {}).get("content")):
                text = text.strip()
                if text and not text.startswith(SKIP_PREFIXES):
                    yield local_time(rec.get("timestamp", "")), text


def main():
    p = argparse.ArgumentParser(description="会話ログから自分の発言だけを書き出す")
    p.add_argument("folder", help="~/.claude/projects/ の下のプロジェクトのフォルダー")
    p.add_argument("-o", "--output", default="my_messages.md")
    p.add_argument("--since", default="", help="この日付（YYYY-MM-DD）以降だけ")
    p.add_argument("--max-chars", type=int, default=600, help="1発言の最大文字数（長い貼り付けを切る）")
    a = p.parse_args()

    folder = Path(a.folder).expanduser()
    out = Path(a.output)
    if not folder.exists():
        print(f"フォルダーが見つかりません: {folder}", file=sys.stderr)
        return 2
    if not folder.is_dir():
        print(f"フォルダーではありません: {folder}（.jsonl が入ったフォルダーを指定してください）", file=sys.stderr)
        return 2
    if a.since:
        try:
            date.fromisoformat(a.since)
        except ValueError:
            print(f"--since は YYYY-MM-DD の形で指定してください: {a.since}", file=sys.stderr)
            return 2
    if out.exists():
        print(f"{out} がすでにあります（別の名前を指定してください）", file=sys.stderr)
        return 2
    files = [f for f in sorted(folder.rglob("*.jsonl")) if "subagents" not in f.parts]
    if not files:
        print(f"{folder} の中に会話ログ（.jsonl）がありません（フォルダーを確かめてください）", file=sys.stderr)
        return 2
    rows = []
    for f in files:
        for when, text in iter_messages(f):
            if when is None:
                continue
            if a.since and when.date().isoformat() < a.since:
                continue
            rows.append((when, f.stem[:8], text))
    if not rows:
        print(f"発言が0件でした（{len(files)}ファイルを読んだ。--since の日付を確かめてください）。ファイルは作っていません", file=sys.stderr)
        return 1
    rows.sort(key=lambda r: r[0])
    with out.open("x", encoding="utf-8") as w:
        w.write(f"# 自分の発言（{len(rows)}件・{len(files)}ファイル）\n\n")
        for when, sid, text in rows:
            body = text if len(text) <= a.max_chars else text[: a.max_chars] + "…（以下略）"
            w.write(f"## {when:%Y-%m-%d %H:%M} 会話{sid}\n\n{body}\n\n")
    print(f"{len(rows)}件を {out} に書き出しました（{len(files)}ファイル）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
