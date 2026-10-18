#!/usr/bin/env python3
"""Claude Code の会話を、1会話1ファイルのMarkdownに書き出す

フック（Stop・SessionEnd）から呼ぶ使い方:
  python3 save_log.py --out <保存先のフォルダー>
  標準入力に Claude Code から渡される JSON（session_id・transcript_path など）を受け取る

手で1件だけ書き出す使い方:
  python3 save_log.py --out <保存先のフォルダー> --transcript <会話ログ.jsonl>

保存先は --out か環境変数 SAVE_LOG_DIR で指定する（どちらも無ければ止まる）
環境変数 SAVE_LOG_OFF に 0 以外の値が入っていると、何もせずに終わる

書くもの: 自分の発言とAIの返事だけ
除くもの: ツールの結果、AIの考え中の内容、サブエージェントの会話、自動で入る補足や通知
（--keep-auto を付けると、自動で入った分も「自動」として残す）

保存の決まり:
- 1つの会話（session_id）は1つのファイルにする
- 新しい会話は <保存先>/inbox/日付_会話IDの先頭8文字.md に作る
- 同じ会話のファイルが inbox か archive にあれば、そのファイルを書き直す
- このスクリプトが作ったものではないファイルや、別の会話のファイルは上書きしない
- 整理のときに書いた frontmatter の topic は、書き直しても残す

終了コード: 0 = 保存した、または保存するものが無かった / 1 = 設定か入力の誤りで止めた
2 は使わない（Stop フックで 2 を返すと、Claude Code が返事を終われなくなるため）

動作を確かめた範囲: macOS・Python 3.9 と 3.14、サンプルの会話ログ（Windows は未確認）
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

MARK = "save_log.py"
AUTO_PREFIXES = (
    "<command-",
    "<local-command-",
    "<system-reminder>",
    "<task-notification>",
    "<scheduled-task",
    "[Request interrupted by user",
    "Caveat:",
)


class Stop(Exception):
    """設定や入力の誤り。メッセージを出して終了コード1で止める"""


class Parser(argparse.ArgumentParser):
    # argparse は引数の誤りで終了コード2を返す
    # Stop フックでは2が「返事を終わらせない」意味になるので、1に変える
    def error(self, message):
        raise Stop("引数の誤り: " + message)


def say(text):
    try:
        print(text, file=sys.stderr)
    except Exception:
        pass


def local_time(stamp):
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def text_of(content):
    """message.content から読める文字だけを取り出す（ツールの結果・考え中の内容は捨てる）"""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block.get("type") == "image":
            parts.append("[画像]")
    return "\n\n".join(p.strip() for p in parts if p.strip())


def read_transcript(path):
    """会話ログ（.jsonl）を読み、(発言のリスト, 除いた自動の記録の数, 読めた記録の数, 作業フォルダー) を返す"""
    turns = []
    auto = []
    records = 0
    cwd = ""
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            records += 1
            if not cwd and isinstance(rec.get("cwd"), str):
                cwd = rec["cwd"]
            if rec.get("isSidechain"):
                continue
            kind = rec.get("type")
            if kind not in ("user", "assistant"):
                continue
            message = rec.get("message")
            if not isinstance(message, dict):
                continue
            text = text_of(message.get("content"))
            if not text:
                continue
            when = local_time(rec.get("timestamp"))
            if kind == "assistant":
                speaker = "AI"
            elif rec.get("isMeta") or rec.get("isCompactSummary") or text.startswith(AUTO_PREFIXES):
                speaker = "自動"
            else:
                speaker = "自分"
            item = {"speaker": speaker, "time": when, "text": text}
            if speaker == "自動":
                auto.append(item)
            turns.append(item)
    return turns, len(auto), records, cwd


def merge(turns, keep_auto):
    """同じ話し手が続く分を1つにまとめる（AIの返事は細かく分かれて記録されるため）"""
    out = []
    for t in turns:
        if t["speaker"] == "自動" and not keep_auto:
            continue
        if out and out[-1]["speaker"] == t["speaker"]:
            out[-1]["text"] += "\n\n" + t["text"]
        else:
            out.append(dict(t))
    return out


def add_last_reply(turns, last):
    """Stop の時点では、最後の返事がまだ会話ログに入っていないことがある
    フックに渡される last_assistant_message で補う（次に保存するときは会話ログから作り直す）"""
    last = (last or "").strip()
    if not last:
        return
    if turns and turns[-1]["speaker"] == "AI":
        if last not in turns[-1]["text"]:
            turns[-1]["text"] += "\n\n" + last
        return
    turns.append({"speaker": "AI", "time": datetime.now().astimezone(), "text": last})


def read_front(path):
    """frontmatter（先頭の --- で囲んだ部分）を {名前: 値} で返す"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    front = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            front[key.strip()] = value.strip()
    return front


def is_ours(path, session_id):
    front = read_front(path)
    return front.get("saved_by") == MARK and front.get("session_id") == session_id


def find_existing(root, session_id):
    """inbox と archive から、同じ会話のファイルを探す"""
    for short in (session_id[:8], session_id[:12]):
        for folder in (root / "inbox", root / "archive"):
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*_" + short + ".md")):
                if is_ours(path, session_id):
                    return path
    return None


def new_path(root, session_id, day):
    """新しく作るファイルの場所を決める（よそのファイルの名前とぶつかったら長い名前にする）"""
    inbox = root / "inbox"
    for short in (session_id[:8], session_id[:12]):
        path = inbox / "{}_{}.md".format(day, short)
        if not path.exists() or is_ours(path, session_id):
            return path
    raise Stop("同じ名前のファイルがすでにあり、このスクリプトのものではないので上書きしません: " + str(path))


def quote(value):
    return json.dumps(value, ensure_ascii=False)


def render(turns, session_id, project, topic, auto_count):
    first = next(t for t in turns if t["speaker"] == "自分")
    title = first["text"].strip().splitlines()[0][:40]
    times = [t["time"] for t in turns if t["time"]]
    start = times[0] if times else datetime.now().astimezone()
    lines = [
        "---",
        "title: " + quote(title),
        "date: " + start.strftime("%Y-%m-%d"),
        "started: " + start.strftime("%Y-%m-%d %H:%M"),
        "updated: " + datetime.now().strftime("%Y-%m-%d %H:%M"),
        "project: " + quote(project),
        "session_id: " + session_id,
        "messages: {}".format(sum(1 for t in turns if t["speaker"] == "自分")),
        "skipped_auto: {}".format(auto_count),
        "topic: " + topic,
        "saved_by: " + MARK,
        "---",
        "",
        "# " + title,
        "",
    ]
    for t in turns:
        stamp = t["time"].strftime("%m-%d %H:%M") if t["time"] else ""
        lines += ["### {} {}".format(t["speaker"], stamp).rstrip(), "", t["text"], ""]
    return "\n".join(lines)


def write_safely(path, text):
    """書きかけのファイルが残らないように、一時ファイルに書いてから置き換える"""
    tmp = path.with_name(".{}.{}.tmp".format(path.name, os.getpid()))
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(str(tmp), str(path))


def run(argv):
    p = Parser(description="Claude Code の会話を1会話1ファイルのMarkdownに書き出す")
    p.add_argument("--out", default="", help="保存先のフォルダー（SAVE_LOG_DIR でも指定できる）")
    p.add_argument("--transcript", default="", help="手で書き出すときの会話ログ（.jsonl）")
    p.add_argument("--keep-auto", action="store_true", help="自動で入った補足や通知も「自動」として残す")
    a = p.parse_args(argv)

    if os.environ.get("SAVE_LOG_OFF", "") not in ("", "0"):
        return 0

    out = a.out or os.environ.get("SAVE_LOG_DIR", "")
    if not out:
        raise Stop("保存先がありません（--out か環境変数 SAVE_LOG_DIR でフォルダーを指定してください）")
    root = Path(out).expanduser()
    if not root.exists():
        raise Stop("保存先のフォルダーが見つかりません: " + str(root))
    if not root.is_dir():
        raise Stop("保存先がフォルダーではありません: " + str(root))

    last = ""
    project = ""
    if a.transcript:
        transcript = Path(a.transcript).expanduser()
        session_id = transcript.name[: -len(".jsonl")] if transcript.name.endswith(".jsonl") else ""
        if "." in session_id:
            raise Stop("会話ログの本体ではありません（退避された古い版など）: " + str(transcript))
    else:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        try:
            event = json.loads(raw)
        except ValueError:
            raise Stop("標準入力がJSONではありません（フックから呼ばれているか確かめてください）")
        if not isinstance(event, dict):
            raise Stop("標準入力のJSONの形が違います")
        if not event.get("transcript_path"):
            raise Stop("標準入力に transcript_path がありません")
        transcript = Path(str(event["transcript_path"])).expanduser()
        session_id = str(event.get("session_id") or "")
        last = event.get("last_assistant_message") or ""
        project = Path(str(event.get("cwd") or "")).name

    if not transcript.exists():
        raise Stop("会話ログが見つかりません: " + str(transcript))
    if not transcript.is_file() or transcript.suffix != ".jsonl":
        raise Stop("会話ログ（.jsonl のファイル）ではありません: " + str(transcript))
    if not session_id or not re.fullmatch(r"[A-Za-z0-9_-]{8,}", session_id):
        raise Stop("会話ID（session_id）が読めません: " + repr(session_id))

    turns, auto_count, records, cwd = read_transcript(transcript)
    if records == 0 and transcript.stat().st_size > 0:
        raise Stop("JSONLとして読める行がありません（会話ログではないファイルかもしれません）: " + str(transcript))
    if not project and cwd:
        project = Path(cwd).name
    turns = merge(turns, a.keep_auto)
    add_last_reply(turns, last)
    if not any(t["speaker"] == "自分" for t in turns):
        say("保存する自分の発言がないので、ファイルは作りませんでした")
        return 0

    existing = find_existing(root, session_id)
    topic = read_front(existing).get("topic", "") if existing else ""
    times = [t["time"] for t in turns if t["time"]]
    day = (times[0] if times else datetime.now().astimezone()).strftime("%Y-%m-%d")
    if existing:
        path = existing
    else:
        (root / "inbox").mkdir(exist_ok=True)
        path = new_path(root, session_id, day)
    write_safely(path, render(turns, session_id, project, topic, auto_count))
    mine = sum(1 for t in turns if t["speaker"] == "自分")
    ai = sum(1 for t in turns if t["speaker"] == "AI")
    print("保存: {}（自分 {}件・AI {}件・除いた自動の記録 {}件）".format(path.relative_to(root), mine, ai, auto_count))
    return 0


def main():
    try:
        return run(sys.argv[1:])
    except Stop as e:
        say("[save_log] " + str(e))
        return 1
    except Exception as e:  # 想定外の失敗も2にはしない
        say("[save_log] 想定外のエラー: {}: {}".format(type(e).__name__, e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
