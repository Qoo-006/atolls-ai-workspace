#!/usr/bin/env python3
"""Claude Codeの会話ログ（.jsonl）から、何にどれだけ使っているかを集計する（標準ライブラリだけで動く）

  python3 usage_report.py                                   ~/.claude/projects 以下をすべて集計
  python3 usage_report.py --since 2026-10-01 --until 2026-10-07
  python3 usage_report.py <フォルダーか .jsonl ファイル> --big 500000 --top 10
  python3 usage_report.py --history                         指示の数を月ごとに数える
  python3 usage_report.py --csv sessions.csv                会話ごとの数字をCSVに書き出す

会話の本文は表示しない。表示するのは、数字・日時・会話IDの先頭8文字・プロジェクトのフォルダー名だけ。
--hide-project を付けると、フォルダー名も伏せる（画面を人に見せるとき用）。

数え方
- AIの返事1回ごとの message.usage を足す。同じ message.id が複数行に出るので1回だけ数える
- 文脈の大きさ = 入力 + キャッシュ書き込み + キャッシュ読み込み（出力は含めない）
- 重み付き = 入力×1 + キャッシュ書き込み（5分）×1.25 + キャッシュ書き込み（1時間）×2
             + キャッシュ読み込み×0.1 + 出力×5
  APIの単価の比率で、会話どうしを比べるための物差し。プランの上限の計算式そのものではない
  キャッシュ読み込みの比率は --read-weight で変えられる
- 上限に当たった日時は、エラーの行（isApiErrorMessage）から取る
- サブエージェントの記録（<会話ID>/subagents/ の下）は、呼び出した会話の分として足す

終了コード: 0 = 集計できた / 1 = 対象の記録が1件もない / 2 = 入力や設定が正しくない
Windowsでは python3 を py -3 に置き換える
"""
import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

W_INPUT, W_WRITE_5M, W_WRITE_1H, W_OUTPUT = 1.0, 1.25, 2.0, 5.0
LIMIT_KINDS = (
    ("session limit", "5時間枠"),
    ("weekly limit", "週の上限"),
    ("opus limit", "モデル別の上限"),
    ("sonnet limit", "モデル別の上限"),
    ("spend limit", "追加利用の上限"),
    ("shared budget", "追加利用の上限"),
    ("usage limit", "利用の上限"),
)


def fail(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def parse_day(text):
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"日付は YYYY-MM-DD で書いてください: {text}")


def positive_int(text):
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"整数で書いてください: {text}")
    if n <= 0:
        raise argparse.ArgumentTypeError(f"1以上で書いてください: {text}")
    return n


def non_negative_float(text):
    try:
        x = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"数で書いてください: {text}")
    if x < 0:
        raise argparse.ArgumentTypeError(f"0以上で書いてください: {text}")
    return x


def local_time(stamp):
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def man(n):
    """トークン数を「万」で短く書く"""
    if n < 10000:
        return f"{int(n):,}"
    text = f"{n / 10000:,.1f}"
    return (text[:-2] if text.endswith(".0") else text) + "万"


def pct(part, whole):
    return f"{part / whole * 100:.1f}%" if whole else "-"


def project_label(path, root, hide):
    if hide:
        return "-"
    for parent in path.parents:
        if parent.parent.name == "projects":
            name = parent.name
            break
    else:
        name = root.name if root.is_dir() else path.parent.name
    home = re.sub(r"[^A-Za-z0-9]", "-", str(Path.home()))
    return "~" + name[len(home):] if name.startswith(home) else name


def collect_files(targets, since):
    files = []
    for target in targets:
        if not target.exists():
            fail(f"見つかりません: {target}")
        if target.is_file():
            if target.suffix != ".jsonl":
                fail(f".jsonl ファイルかフォルダーを指定してください: {target}")
            files.append((target, target))
        elif target.is_dir():
            files.extend((f, target) for f in sorted(target.rglob("*.jsonl")))
        else:
            fail(f"ファイルでもフォルダーでもありません: {target}")
    if since:
        start = datetime.combine(since, datetime.min.time()).timestamp()
        files = [(f, r) for f, r in files if f.stat().st_mtime >= start]
    return files


def usage_numbers(usage):
    inp = usage.get("input_tokens") or 0
    write = usage.get("cache_creation_input_tokens") or 0
    read = usage.get("cache_read_input_tokens") or 0
    out = usage.get("output_tokens") or 0
    detail = usage.get("cache_creation") or {}
    w5 = detail.get("ephemeral_5m_input_tokens")
    w1 = detail.get("ephemeral_1h_input_tokens")
    if w5 is None and w1 is None:
        w5, w1 = 0, write  # 内訳のない古い行は1時間として数える
    return inp, w5 or 0, w1 or 0, read, out


def limit_kind(text):
    """「5時間枠」「週の上限」など。追加利用の上限にも達しているときは「＋」でつなぐ"""
    low = text.lower()
    labels = []
    for key, label in LIMIT_KINDS:
        if key in low and label not in labels:
            labels.append(label)
    if len(labels) > 1 and "利用の上限" in labels:
        labels.remove("利用の上限")
    return "＋".join(labels) or "その他の上限"


def read_logs(files, hide):
    messages = {}
    limits = {}
    broken = 0
    for path, root in files:
        is_sub_file = "subagents" in path.parts
        label = project_label(path, root, hide)
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                has_usage = '"usage"' in line and '"assistant"' in line
                has_error = "isApiErrorMessage" in line
                if not (has_usage or has_error):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    broken += 1
                    continue
                if not isinstance(rec, dict):
                    continue
                when = local_time(rec.get("timestamp"))
                if when is None:
                    continue
                msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
                if rec.get("isApiErrorMessage"):
                    content = msg.get("content")
                    if isinstance(content, list):
                        text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                    else:
                        text = str(content or "")
                    if rec.get("error") == "rate_limit" or "you've hit your" in text.lower():
                        reset = re.search(r"resets? ([^·\n]{1,30})", text)
                        key = (when.strftime("%Y-%m-%d %H:%M"), limit_kind(text))
                        limits[key] = reset.group(0).strip() if reset else ""
                    continue
                if rec.get("type") != "assistant" or not isinstance(msg.get("usage"), dict):
                    continue
                nums = usage_numbers(msg["usage"])
                if not any(nums):
                    continue
                mid = msg.get("id") or rec.get("uuid") or f"{path}:{when.isoformat()}"
                sid = rec.get("sessionId") or path.stem
                is_sub = is_sub_file or bool(rec.get("isSidechain"))
                old = messages.get(mid)
                if old is None or nums[4] > old["nums"][4]:
                    messages[mid] = {
                        "sid": sid, "project": label, "when": when, "sub": is_sub,
                        "model": msg.get("model") or "?", "nums": nums,
                    }
    return messages, limits, broken


def weighted(nums, read_weight):
    inp, w5, w1, read, out = nums
    return inp * W_INPUT + w5 * W_WRITE_5M + w1 * W_WRITE_1H + read * read_weight + out * W_OUTPUT


def in_range(when, since, until):
    d = when.date()
    return (not since or d >= since) and (not until or d <= until)


def build_sessions(messages, since, until, read_weight):
    first_main = {}
    for m in messages.values():
        if not m["sub"]:
            cur = first_main.get(m["sid"])
            if cur is None or m["when"] < cur["when"]:
                first_main[m["sid"]] = m
    sessions = {}
    models = Counter()
    for m in messages.values():
        if not in_range(m["when"], since, until):
            continue
        s = sessions.setdefault(m["sid"], {
            "sid": m["sid"], "project": m["project"], "start": m["when"], "end": m["when"],
            "n": 0, "sums": [0, 0, 0, 0, 0], "weighted": 0.0, "sub_weighted": 0.0,
            "max_ctx": 0, "first_ctx": None,
        })
        w = weighted(m["nums"], read_weight)
        inp, w5, w1, read, _ = m["nums"]
        s["n"] += 1
        s["sums"] = [a + b for a, b in zip(s["sums"], m["nums"])]
        s["weighted"] += w
        if m["sub"]:
            s["sub_weighted"] += w
        else:
            s["project"] = m["project"]
            s["max_ctx"] = max(s["max_ctx"], inp + w5 + w1 + read)
        s["start"] = min(s["start"], m["when"])
        s["end"] = max(s["end"], m["when"])
        models[m["model"]] += w
    for sid, s in sessions.items():
        first = first_main.get(sid)
        if first and in_range(first["when"], since, until):
            inp, w5, w1, read, _ = first["nums"]
            s["first_ctx"] = inp + w5 + w1 + read
        if s["max_ctx"] == 0:  # サブエージェントの記録しか残っていない会話
            s["max_ctx"] = None
    return sessions, models


def count_history(path, since, until):
    months = Counter()
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or not isinstance(rec.get("timestamp"), (int, float)):
                continue
            if str(rec.get("display", "")).startswith("/"):
                continue
            when = datetime.fromtimestamp(rec["timestamp"] / 1000)
            if in_range(when, since, until):
                months[when.strftime("%Y-%m")] += 1
    return months


def write_csv(path, sessions):
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["会話ID", "プロジェクト", "開始", "終了", "応答数", "入力", "キャッシュ書き込み5分",
                    "キャッシュ書き込み1時間", "キャッシュ読み込み", "出力", "重み付き", "文脈の最大",
                    "最初の応答の文脈", "サブエージェントの重み付き"])
        for s in sorted(sessions.values(), key=lambda s: s["start"]):
            w.writerow([s["sid"], s["project"], s["start"].strftime("%Y-%m-%d %H:%M"),
                        s["end"].strftime("%Y-%m-%d %H:%M"), s["n"], *s["sums"], round(s["weighted"]),
                        s["max_ctx"] if s["max_ctx"] is not None else "",
                        s["first_ctx"] if s["first_ctx"] is not None else "", round(s["sub_weighted"])])


def report(sessions, models, limits, broken, a):
    rows = list(sessions.values())
    total = sum(s["weighted"] for s in rows)
    sums = [sum(s["sums"][i] for s in rows) for i in range(5)]
    inp, w5, w1, read, out = sums
    first_day = min(s["start"] for s in rows).date()
    last_day = max(s["end"] for s in rows).date()
    print("# Claude Codeの消費の集計\n")
    print(f"期間: {a.since or first_day} 〜 {a.until or last_day}（記録が残っている範囲: {first_day} 〜 {last_day}）")
    print(f"会話 {len(rows)}本・応答 {sum(s['n'] for s in rows):,}回")
    print(f"重み: 入力1 / キャッシュ書き込み 5分1.25・1時間2 / キャッシュ読み込み{a.read_weight:g} / 出力5（入力に換算）")
    if broken:
        print(f"読めなかった行: {broken}行（集計から外した）")

    print("\n## 全体")
    print(f"重み付きの合計: {man(total)}")
    print(f"  入力 {pct(inp * W_INPUT, total)} / キャッシュ書き込み {pct(w5 * W_WRITE_5M + w1 * W_WRITE_1H, total)}"
          f" / キャッシュ読み込み {pct(read * a.read_weight, total)} / 出力 {pct(out * W_OUTPUT, total)}")
    print(f"  サブエージェントの分 {pct(sum(s['sub_weighted'] for s in rows), total)}")
    print("  モデル別: " + " / ".join(f"{k} {pct(v, total)}" for k, v in models.most_common(4)))

    big = [s for s in rows if (s["max_ctx"] or 0) > a.big]
    print(f"\n## 文脈が{man(a.big)}を超えた会話")
    print(f"{len(big)}本 / {len(rows)}本（{pct(len(big), len(rows))}）・重み付き合計の {pct(sum(s['weighted'] for s in big), total)}")

    top = sorted(rows, key=lambda s: s["weighted"], reverse=True)[: a.top]
    print(f"\n## 重い会話 上位{len(top)}本（合計の {pct(sum(s['weighted'] for s in top), total)}）")
    for i, s in enumerate(top, 1):
        ctx = man(s["max_ctx"]) if s["max_ctx"] is not None else "-"
        print(f"{i:>2}. {s['start']:%m/%d %H:%M}  {s['sid'][:8]}  {s['project']}  応答{s['n']}回"
              f"  文脈の最大 {ctx}  {pct(s['weighted'], total)}")

    firsts = [s["first_ctx"] for s in rows if s["first_ctx"] is not None]
    print("\n## 起動時の重さ（各会話の最初の応答の文脈）")
    if firsts:
        print(f"中央値 {man(statistics.median(firsts))}・最小 {man(min(firsts))}・最大 {man(max(firsts))}"
              f"（最初の応答が期間内にある会話 {len(firsts)}本）")
    else:
        print("（期間内に始まった会話がない）")

    weeks = defaultdict(list)
    for s in rows:
        d = s["start"].date()
        weeks[d - timedelta(days=d.weekday())].append(s)
    print("\n## 週ごと（月曜始まり・会話が始まった週で数える）")
    print(f"週の始まり  会話  重み付き  {man(a.big)}超  最初の応答の文脈（中央値）")
    for monday in sorted(weeks):
        ws = weeks[monday]
        wf = [s["first_ctx"] for s in ws if s["first_ctx"] is not None]
        med = man(statistics.median(wf)) if wf else "-"
        nbig = sum(1 for s in ws if (s["max_ctx"] or 0) > a.big)
        print(f"{monday}  {len(ws):>3}本  {man(sum(s['weighted'] for s in ws))}  {nbig}本  {med}")

    hits = sorted((k, v) for k, v in limits.items() if in_range(datetime.strptime(k[0], "%Y-%m-%d %H:%M"), a.since, a.until))
    print(f"\n## 上限に当たった記録（{len(hits)}回・同じ分の重複は1回）")
    for (when, kind), reset in hits[-a.top:]:
        print(f"{when}  {kind}  {reset}".rstrip())
    if len(hits) > a.top:
        print(f"（古い{len(hits) - a.top}回は省略）")
    kinds = Counter(kind for (_, kind), _ in hits)
    if kinds:
        print("種類別: " + " / ".join(f"{k} {n}回" for k, n in kinds.most_common()))


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:
            pass
    default_root = Path.home() / ".claude" / "projects"
    p = argparse.ArgumentParser(description="Claude Codeの会話ログから消費を集計する")
    p.add_argument("targets", nargs="*", help=f"フォルダーか .jsonl（省略すると {default_root}）")
    p.add_argument("--since", type=parse_day, help="この日（YYYY-MM-DD）以降だけ")
    p.add_argument("--until", type=parse_day, help="この日（YYYY-MM-DD）まで")
    p.add_argument("--big", type=positive_int, default=500000, help="文脈が大きい会話の境目（既定 500000）")
    p.add_argument("--top", type=positive_int, default=10, help="上位として出す会話の数（既定 10）")
    p.add_argument("--read-weight", type=non_negative_float, default=0.1, help="キャッシュ読み込みの重み（既定 0.1）")
    p.add_argument("--history", nargs="?", const=str(Path.home() / ".claude" / "history.jsonl"),
                   help="指示の数を月ごとに数える（場所を省略すると ~/.claude/history.jsonl）")
    p.add_argument("--csv", help="会話ごとの数字をこのCSVに書く（同じ名前があれば止まる）")
    p.add_argument("--hide-project", action="store_true", help="プロジェクトのフォルダー名を伏せる")
    a = p.parse_args()

    if a.since and a.until and a.since > a.until:
        fail("--since が --until より後になっています")
    csv_path = Path(a.csv).expanduser() if a.csv else None
    if csv_path and csv_path.exists():
        fail(f"{csv_path} がすでにあります（別の名前を指定してください）")
    history = Path(a.history).expanduser() if a.history else None
    if history and not history.is_file():
        fail(f"指示の履歴が見つかりません: {history}")

    targets = [Path(t).expanduser() for t in a.targets] or [default_root]
    files = collect_files(targets, a.since)
    messages, limits, broken = read_logs(files, a.hide_project)
    sessions, models = build_sessions(messages, a.since, a.until, a.read_weight)
    if not sessions:
        print(f"集計できる記録がありませんでした（.jsonl {len(files)}件を確認）", file=sys.stderr)
        return 1
    report(sessions, models, limits, broken, a)
    if history:
        months = count_history(history, a.since, a.until)
        print("\n## 指示の数（history.jsonl・/で始まるコマンドを除く）")
        print("\n".join(f"{m}  {n:,}件" for m, n in sorted(months.items())) or "（期間内の記録なし）")
    if csv_path:
        write_csv(csv_path, sessions)
        print(f"\n会話ごとの数字を {csv_path} に書き出しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
