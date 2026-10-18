#!/usr/bin/env python3
"""文体プロファイルに書いた規則で、原稿を1行ずつ見る（Python 3 の標準ライブラリだけで動く）

使い方:
  python3 style_check.py check 文体プロファイル.md 原稿.md --media note
      プロファイルの「## 規則：共通」と、note が入った「## 規則：」の節で原稿を見る
  python3 style_check.py diff 初稿.md 仕上げ.md
      初稿から仕上げで変えた行だけを出す

終了コード:
  0  規則に当たる行がない（diff は比べられたら0）
  1  規則に当たる行がある
  2  止めた。ファイルがない・フォルダーを渡した・UTF-8で読めない・規則の書き方が違う・
     正規表現が壊れている・指定した媒体の節がない・規則が1件もない・本文が空・
     コードブロックや先頭のプロパティが閉じていない

見ない範囲:
  先頭のプロパティ（--- で囲んだ範囲）、コードブロック、` で囲んだコード、URL、
  引用（> で始まる行）、HTMLのコメント

ファイルは読むだけで、書き換えない。
Windows では python3 を py -3 に置き換える。
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

FENCES = ("`" * 3, "~" * 3)  # コードブロックの印（記事に貼っても崩れないように分けて書く）

# 記号は名前で書く。全角と半角をまとめて見る
SYMBOLS = {
    "句点": "[。．]",
    "読点": "[、，]",
    "感嘆符": "[！!]",
    "疑問符": "[？?]",
    "三点リーダー": "[…‥]",
    "絵文字": "[\U0001F300-\U0001FAFF☀-➿]",
}
WORD_RULES = ("使わない", "使わない形", "使わない記号")
NUMBER_RULES = ("同じ文末の連続", "1文の最大字数", "全体の最大字数")
ALL_RULES = WORD_RULES + ("文末に置かない", "回数の上限") + NUMBER_RULES

RULE_HEAD = re.compile(r"^##\s*規則\s*[：:]\s*(.*?)\s*$")
RULE_LINE = re.compile(r"^-\s*([^:：]+?)\s*[:：]\s*(.*?)\s*$")
HEADING = re.compile(r"^#{1,6}\s")
LIST_MARK = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
URL = re.compile(r"https?://\S+")
INLINE_CODE = re.compile(r"`[^`\n]*`")
SPLIT = re.compile(r"(?<=[。．！!？?])")
TAIL = "。．！!？?、，」』）)】…‥ 　"  # 文末を決めるときに外す記号と閉じ括弧


class Stop(Exception):
    """終了コード2で止める理由"""


def read_text(path, what):
    p = Path(path)
    if not p.exists():
        raise Stop(f"{what}が見つかりません: {path}")
    if not p.is_file():
        raise Stop(f"{what}がファイルではありません（フォルダーなど）: {path}")
    try:
        return p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise Stop(f"{what}をUTF-8の文字として読めません: {path}")


def parse_rule(name, value):
    """規則1行を辞書にする。書き方が違えば Stop の理由を返す"""
    if name not in ALL_RULES:
        return None, f"知らない規則です「{name}」（使える規則: {'、'.join(ALL_RULES)}）"
    if not value:
        return None, f"「{name}」の値が空です"
    rule = {"kind": name, "value": value}
    if name == "使わない":
        rule["rx"] = re.compile(re.escape(value))
    elif name == "使わない形":
        try:
            rule["rx"] = re.compile(value)
        except re.error as e:
            return None, f"「使わない形」の正規表現が読めません（{e}）: {value}"
        if rule["rx"].search(""):
            return None, f"「使わない形」が空の文字にも当たるので、どの行にも当たってしまいます: {value}"
    elif name == "使わない記号":
        if value not in SYMBOLS:
            return None, f"記号の名前が違います「{value}」（使える名前: {'、'.join(SYMBOLS)}）"
        rule["rx"] = re.compile(SYMBOLS[value])
    elif name == "回数の上限":
        parts = value.rsplit(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9]+", parts[1]):
            return None, f"「回数の上限」は「言い回し 回数」の形で書きます: {value}"
        rule["word"], rule["limit"] = parts[0], int(parts[1])
    elif name in NUMBER_RULES:
        if not re.fullmatch(r"[0-9]+", value) or int(value) < 1:
            return None, f"「{name}」は1以上の半角数字で書きます: {value}"
        rule["limit"] = int(value)
    return rule, None


def load_rules(path, media):
    """プロファイルの規則を全部確かめてから、共通と指定した媒体の分だけ返す"""
    media = media.strip().lower()
    picked, errors, sections, seen = [], [], [], []
    active = in_rules = False
    common = False
    for no, line in enumerate(read_text(path, "プロファイル").splitlines(), 1):
        head = RULE_HEAD.match(line)
        if head:
            names = [n.strip().lower() for n in re.split(r"[,、，]", head.group(1)) if n.strip()]
            if not names:
                errors.append(f"{path}:{no} 「## 規則：」の後ろに媒体名か「共通」を書きます")
            seen.extend(n for n in names if n != "共通" and n not in seen)
            common = "共通" in names
            active = common or (bool(media) and media in names)
            in_rules = True
            if active:
                sections.append(head.group(1))
            continue
        if line.startswith("#"):
            active = in_rules = False
            continue
        if not in_rules or not line.startswith("-"):
            continue
        m = RULE_LINE.match(line)
        if not m:
            errors.append(f"{path}:{no} 「- 規則名: 値」の形になっていません: {line.strip()}")
            continue
        rule, err = parse_rule(m.group(1), m.group(2))
        if err:
            errors.append(f"{path}:{no} {err}")
        elif active:
            rule["common"] = common
            picked.append(rule)
    if errors:
        raise Stop("規則の書き方が違う行があります\n  " + "\n  ".join(errors))
    if not sections and not seen:
        raise Stop(f"{path} に「## 規則：」の節がありません")
    if media and media not in seen:
        raise Stop(f"「--media {media}」の節がありません（プロファイルにある媒体: {'、'.join(seen) or 'なし'}）")
    if not picked:
        raise Stop("使う規則が1件もありません（このまま見ると、何も見ずに「該当なし」になるので止めます）")
    return picked, sections


def body_rows(text):
    """(行番号, 中身, 種類) を返す。種類は text・list・heading・table・gap（見ない行）"""
    lines = text.splitlines()
    rows = []
    in_front = bool(lines) and lines[0].strip() == "---"
    front_start = 1 if in_front else 0
    fence = None
    fence_line = 0
    in_comment = False
    for no, raw in enumerate(lines, 1):
        s = raw.strip()
        if in_front:
            if no > 1 and s in ("---", "..."):
                in_front = False
            rows.append((no, "", "gap"))
            continue
        if fence:
            if s.startswith(fence):
                fence = None
            rows.append((no, "", "gap"))
            continue
        opened = next((f for f in FENCES if s.startswith(f)), None)
        if opened:
            fence, fence_line = opened, no
            rows.append((no, "", "gap"))
            continue
        line = raw
        if in_comment:
            if "-->" not in line:
                rows.append((no, "", "gap"))
                continue
            line = line.split("-->", 1)[1]
            in_comment = False
        line = re.sub(r"<!--.*?-->", "", line)
        if "<!--" in line:
            line = line.split("<!--", 1)[0]
            in_comment = True
        line = URL.sub("", INLINE_CODE.sub("", line))
        s = line.strip()
        if not s or s.startswith(">"):
            rows.append((no, "", "gap"))
        elif HEADING.match(s):
            rows.append((no, s.lstrip("#").strip(), "heading"))
        elif s.startswith("|"):
            rows.append((no, s, "table"))
        elif LIST_MARK.match(s):
            rows.append((no, LIST_MARK.sub("", s, count=1), "list"))
        else:
            rows.append((no, s, "text"))
    if in_front:
        raise Stop(f"{front_start}行目からの先頭のプロパティ（---）が閉じていません")
    if fence:
        raise Stop(f"{fence_line}行目のコードブロックが閉じていません（ここから後ろを見られません）")
    return rows


def sentences(text):
    return [p.strip() for p in SPLIT.split(text) if p.strip()]


def pick_number(rules, kind):
    """数字の規則は、媒体の節に書いた値を共通の節より優先する"""
    found = [r for r in rules if r["kind"] == kind]
    media_side = [r for r in found if not r["common"]]
    chosen = (media_side or found)[-1:] if found else []
    return chosen[0]["limit"] if chosen else None


def cmd_check(a):
    rules, sections = load_rules(a.profile, a.media)
    rows = body_rows(read_text(a.target, "原稿"))
    content = [r for r in rows if r[2] != "gap"]
    if not content:
        raise Stop(f"{a.target} の本文が空です（見ない範囲を除くと何も残りません）")

    symbol_rules = [r for r in rules if r["kind"] == "使わない記号"]

    def mask(s):
        for r in symbol_rules:
            s = r["rx"].sub(f"【{r['value']}】", s)
        return s

    hits = []
    # 1. 言い回し・正規表現・記号（見出し・表・箇条書きも見る）
    for no, s, kind in content:
        for r in rules:
            if r["kind"] not in WORD_RULES:
                continue
            found = list(r["rx"].finditer(s))
            if not found:
                continue
            m = found[0]
            shown = r["value"] if r["kind"] == "使わない記号" else m.group(0)
            more = f"（{len(found)}か所）" if len(found) > 1 else ""
            near = mask(s[max(0, m.start() - 20):m.start()]) + f"【{shown}】" + mask(s[m.end():m.end() + 10])
            hits.append((no, r["kind"], f"{near}{more}"))

    # 2. 文ごとの規則（本文と箇条書き。見出しと表は見ない）
    ends = [r for r in rules if r["kind"] == "文末に置かない"]
    max_len = pick_number(rules, "1文の最大字数")
    max_run = pick_number(rules, "同じ文末の連続")
    run_key, run_len, run_start, reported = None, 0, 0, False
    for no, s, kind in rows:
        if kind not in ("text", "list"):
            run_key, run_len = None, 0
            continue
        for sent in sentences(s):
            core = sent.rstrip(TAIL)
            for r in ends:
                if core.endswith(r["value"]):
                    stem = core[: len(core) - len(r["value"])]
                    hits.append((no, "文末に置かない", f"{mask(stem[-15:])}【{r['value']}】"))
            length = len(re.sub(r"\s", "", sent))
            if max_len and length > max_len:
                hits.append((no, "1文の最大字数", f"{length}字（上限{max_len}字）「{mask(sent[:20])}」から始まる文"))
            if kind == "list" or not max_run:
                run_key, run_len = None, 0
                continue
            key = core[-2:] if len(core) >= 2 else None
            if key and key == run_key:
                run_len += 1
            else:
                run_key, run_len, run_start, reported = key, 1, no, False
            if run_len >= max_run and not reported:
                hits.append((run_start, "同じ文末の連続", f"「〜{key}」で終わる文が{max_run}つ続いてる（{run_start}〜{no}行目）"))
                reported = True

    # 3. 回数の上限（原稿全体で数える。媒体の節の値を共通より優先する）
    limits = {}
    for r in sorted((r for r in rules if r["kind"] == "回数の上限"), key=lambda r: not r["common"]):
        limits[r["word"]] = r["limit"]
    for word, limit in limits.items():
        where = [no for no, s, _ in content for _ in range(s.count(word))]
        if len(where) > limit:
            lines = "・".join(str(n) for n in sorted(set(where)))
            hits.append((where[0], "回数の上限", f"「{word}」が{len(where)}回（上限{limit}回）{lines}行目"))

    # 4. 全体の字数（URLは数えない）
    max_total = pick_number(rules, "全体の最大字数")
    total = sum(len(re.sub(r"\s", "", s)) for _, s, _ in content)
    if max_total and total > max_total:
        hits.append((0, "全体の最大字数", f"{total}字（上限{max_total}字）"))

    for no, kind, detail in sorted(hits, key=lambda h: h[0]):
        place = f"{a.target}:{no}" if no else f"{a.target}"
        print(f"{place} [{kind}] {detail}")
    media = a.media or "指定なし"
    print(f"媒体 {media}・規則 {len(rules)}件（{' / '.join(sections)}）で見て、該当 {len(hits)}件")
    return 1 if hits else 0


def cmd_diff(a):
    old = read_text(a.draft, "初稿").splitlines()
    new = read_text(a.final, "仕上げ").splitlines()
    removed = added = 0
    for i, line in enumerate(difflib.unified_diff(old, new, a.draft, a.final, n=0, lineterm="")):
        print(line)
        if i < 2:
            continue
        if line.startswith("-"):
            removed += 1
        elif line.startswith("+"):
            added += 1
    if removed == added == 0:
        print("初稿と仕上げが同じです（変えた行がありません）")
    else:
        print(f"初稿から消した行 {removed}・足した行 {added}")
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    p = argparse.ArgumentParser(description="文体プロファイルの規則で原稿を見る")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True
    c = sub.add_parser("check", help="規則に当たる行を出す")
    c.add_argument("profile")
    c.add_argument("target")
    c.add_argument("--media", default="", help="note・x・linkedin など、プロファイルの「## 規則：」に書いた媒体名")
    d = sub.add_parser("diff", help="初稿から変えた行だけを出す")
    d.add_argument("draft")
    d.add_argument("final")
    a = p.parse_args()
    try:
        return {"check": cmd_check, "diff": cmd_diff}[a.cmd](a)
    except Stop as e:
        print(f"止めました: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
