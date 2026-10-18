#!/usr/bin/env python3
"""ダメ出し台帳（criteria.md）を使う小さな道具（標準ライブラリだけで動く）

  python3 criteria.py brief  criteria.md --type note              作る前に当たる基準を出す
  python3 criteria.py lint   criteria.md 原稿.md --type note --log hits.tsv   機械で見られる基準を当てる
  python3 criteria.py record criteria.md JP-001 --note "説明なし" --log hits.tsv   目で見つけた違反を残す
  python3 criteria.py unused criteria.md --log hits.tsv --days 90  記録のない古い基準を出す

終了コード: 0＝該当なし 1＝該当あり 2＝台帳や原稿が読めない・検出の正規表現が壊れている（検査していない）
Windowsでは python3 を py -3 に置き換える
"""
import argparse
import csv
import re
import sys
from datetime import date, timedelta
from pathlib import Path

SEVERITY = {"出荷不可": 0, "直す": 1, "好み": 2}
FENCE = "`" * 3  # コードブロックの印（記事に貼っても崩れないように分けて書く）


def fail(message):
    """台帳・原稿・設定の不備で検査できないときは、終了コード2で止める"""
    print(message, file=sys.stderr)
    sys.exit(2)


def read_text(path, label):
    p = Path(path)
    if not p.is_file():
        fail(f"{label}が見つかりません: {path}")
    return p.read_text(encoding="utf-8")


def load(path):
    """「## ID」ごとに「- 項目名: 値」を辞書にする"""
    items, cur = [], None
    for line in read_text(path, "台帳").splitlines():
        if line.startswith("## "):
            cur = {"ID": line[3:].strip()}
            items.append(cur)
        elif cur is not None and line.startswith("- ") and ":" in line:
            key, _, value = line[2:].partition(":")
            cur[key.strip()] = value.strip()
    if not items:
        fail("基準が1件も読めません（「## ID」と「- 項目名: 値」の形か確かめてください）")
    return sorted(items, key=lambda i: (SEVERITY.get(i.get("重さ"), 9), i["ID"]))


def applies(item, kind):
    found = [t.strip() for t in item.get("当てる成果物", "*").split(",") if t.strip()]
    return not kind or "*" in found or kind in found


def body_lines(text):
    """先頭のプロパティ（---で囲んだ範囲）とコードブロックを飛ばして1行ずつ返す"""
    lines = text.splitlines()
    in_front = bool(lines) and lines[0].strip() == "---"
    in_code = False
    for no, line in enumerate(lines, 1):
        if in_front:
            if no > 1 and line.strip() == "---":
                in_front = False
            continue
        if line.lstrip().startswith(FENCE):
            in_code = not in_code
            continue
        if not in_code:
            yield no, line


def append_log(path, rows):
    with open(path, "a", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t").writerows(rows)


def cmd_brief(a):
    picked = [i for i in load(a.criteria) if applies(i, a.type)]
    print(f"# 作る前に読む基準（{a.type or 'すべて'}・{len(picked)}件）\n")
    for i in picked:
        ng = f"　✗ {i['ダメな例']}" if i.get("ダメな例") else ""
        print(f"- [{i['ID']}｜{i.get('重さ', '')}｜{i.get('確かめ方', '')}] {i.get('基準', '')}{ng}")
    return 0


def cmd_lint(a):
    checks, broken = [], []
    for i in load(a.criteria):
        if i.get("確かめ方") == "機械" and i.get("検出") and applies(i, a.type):
            try:
                checks.append((i, re.compile(i["検出"])))
            except re.error as e:
                broken.append(f"{i['ID']} の検出（{i['検出']}）が正規表現として読めません: {e}")
    if broken:
        fail("\n".join(broken) + "\n台帳を直してからもう一度実行してください（検査はしていません）")
    if not checks:
        print(f"機械で確かめる基準が0件です（種類「{a.type or 'すべて'}」）。この結果は合格の意味になりません", file=sys.stderr)
    found = []
    for no, line in body_lines(read_text(a.target, "原稿")):
        for item, rx in checks:
            m = rx.search(line)
            if m:
                found.append((no, item, m.group(0), line.strip()))
    for no, item, hit, line in found:
        print(f"{a.target}:{no} [{item['ID']}｜{item.get('重さ', '')}] {item.get('基準', '')}")
        print(f"    該当「{hit}」: {line[:80]}")
    print(f"機械で見た基準 {len(checks)}件・該当 {len(found)}件")
    if a.log and found:
        append_log(a.log, [[date.today().isoformat(), a.target, i["ID"], h] for _, i, h, _ in found])
    return 1 if found else 0


def cmd_record(a):
    if not any(i["ID"] == a.id for i in load(a.criteria)):
        fail(f"{a.id} は台帳にありません")
    append_log(a.log, [[date.today().isoformat(), a.target, a.id, a.note or "手動"]])
    print(f"{a.id} を {a.log} に記録しました")
    return 0


def cmd_unused(a):
    hits = set()
    if Path(a.log).exists():
        with open(a.log, encoding="utf-8", newline="") as f:
            hits = {row[2] for row in csv.reader(f, delimiter="\t") if len(row) >= 3}
    limit = date.today() - timedelta(days=a.days)
    print(f"# {a.days}日以上前に足して、一度も記録がない基準\n")
    rows = []
    for i in load(a.criteria):
        try:
            added = date.fromisoformat(i.get("追加日", ""))
        except ValueError:
            continue
        if i["ID"] not in hits and added <= limit:
            rows.append(f"- {i['ID']}（追加 {added}）{i.get('基準', '')}")
    print("\n".join(rows) if rows else "（該当なし）")
    return 0


def main():
    p = argparse.ArgumentParser(description="ダメ出し台帳を使う")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief")
    b.add_argument("criteria")
    b.add_argument("--type", default="")
    li = sub.add_parser("lint")
    li.add_argument("criteria")
    li.add_argument("target")
    li.add_argument("--type", default="")
    li.add_argument("--log")
    r = sub.add_parser("record")
    r.add_argument("criteria")
    r.add_argument("id")
    r.add_argument("--log", required=True)
    r.add_argument("--target", default="-")
    r.add_argument("--note", default="")
    u = sub.add_parser("unused")
    u.add_argument("criteria")
    u.add_argument("--log", required=True)
    u.add_argument("--days", type=int, default=90)
    a = p.parse_args()
    return {"brief": cmd_brief, "lint": cmd_lint, "record": cmd_record, "unused": cmd_unused}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
