#!/usr/bin/env python3
"""原稿の中のURLを抜き出して、開けるかどうかを一覧にする（Python 3 の標準ライブラリだけで動く）

  python3 link_check.py 原稿.md
  python3 link_check.py 原稿.md --timeout 10 --ignore example.com
  python3 link_check.py 原稿.md -o link_check_結果.md

- 同じURLは1回だけ確かめる
- 転送（リダイレクト）は最大5回までたどり、最後に着いたURLを出す
- HEAD（中身を取らない問い合わせ）で断られたときは、GETで取り直す
- -o の書き出し先がすでにあるときは、上書きせずに止まる
- 開けた（応答が200番台）ことは、そのページに主張が書いてあることの確認にはならない

終了コード
  0  すべて開けた（転送ありを含む）
  1  開けない・見つからない・拒否されたURLがある
  2  使い方の誤り（入力ファイルがない、フォルダーを渡した、文字コードが違う、URLが1件もない、
     書き出し先がすでにある、--timeout が0以下 など）

Windowsでは python3 を py -3 に置き換える
"""
import argparse
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

MAX_HOPS = 5
USER_AGENT = "link_check.py (Python urllib)"

# URLの終わりとみなす文字（空白、山かっこ、引用符、全角の句読点とかっこ）
URL_RE = re.compile(r"https?://[^\s<>\"'`、。（）「」『』【】]+")
TRAILING = ".,;:!?*_~"

LABELS = {
    "ok": "開けた",
    "moved": "転送あり",
    "notfound": "見つからない",
    "denied": "拒否",
    "limited": "回数制限",
    "server": "相手側のエラー",
    "other": "要確認",
    "loop": "転送が多すぎる",
    "fail": "開けない",
}
GOOD = {"ok", "moved"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """転送を自動でたどらず、3xxの応答をそのまま受け取る"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def clean_url(url):
    """文末の記号と、対になっていない閉じかっこを外す"""
    while url:
        if url[-1] in TRAILING:
            url = url[:-1]
        elif url[-1] == ")" and url.count("(") < url.count(")"):
            url = url[:-1]
        elif url[-1] == "]" and url.count("[") < url.count("]"):
            url = url[:-1]
        else:
            break
    return url


def find_urls(text, ignore):
    """URLを出てきた順に、重複を除いて返す（値は出てきた行番号のリスト）"""
    found = {}
    for no, line in enumerate(text.splitlines(), 1):
        for m in URL_RE.finditer(line):
            url = clean_url(m.group(0))
            if not urlsplit(url).netloc:
                continue
            if any(word in url for word in ignore):
                continue
            found.setdefault(url, []).append(no)
    return found


def describe(err):
    reason = getattr(err, "reason", err)
    if isinstance(reason, socket.gaierror):
        return "名前解決できない（ドメインがない）"
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "時間切れ"
    if isinstance(reason, ssl.SSLError):
        return "証明書・暗号化のエラー"
    if isinstance(reason, ConnectionRefusedError):
        return "接続を拒否された"
    return type(reason).__name__


def request_once(url, method, timeout):
    """1回だけ問い合わせて (応答コード, 転送先, エラーの説明) を返す"""
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with OPENER.open(req, timeout=timeout) as res:
            return res.status, None, ""
    except urllib.error.HTTPError as e:
        location = e.headers.get("Location") if e.headers else None
        e.close()
        return e.code, location, ""
    except urllib.error.URLError as e:
        return None, None, describe(e)
    except Exception as e:  # 時間切れ、接続の切断など
        return None, None, describe(e)


def check(url, timeout):
    codes, current = [], url
    for _ in range(MAX_HOPS + 1):
        code, location, err = request_once(current, "HEAD", timeout)
        if code is None or code >= 400:
            # HEADを受け付けないサーバーがあるので、GETで取り直す
            code, location, err = request_once(current, "GET", timeout)
        if code is None:
            return {"kind": "fail", "codes": codes, "final": current, "note": err}
        codes.append(code)
        if 300 <= code < 400 and location:
            current = urljoin(current, location)
            continue
        return {"kind": classify(code, len(codes) > 1), "codes": codes, "final": current, "note": ""}
    return {"kind": "loop", "codes": codes, "final": current, "note": f"{MAX_HOPS}回を超える転送"}


def classify(code, moved):
    if 200 <= code < 300:
        return "moved" if moved else "ok"
    if code in (404, 410):
        return "notfound"
    if code in (401, 403):
        return "denied"
    if code == 429:
        return "limited"
    if code >= 500:
        return "server"
    return "other"


def listing(rows):
    """1件を「番号. 判定：応答」と、その下の行番号・URL・着いたURLで書く"""
    out = []
    for i, (url, lines, r) in enumerate(rows, 1):
        codes = " → ".join(str(c) for c in r["codes"])
        if r["note"]:
            codes = f"{codes}（{r['note']}）" if codes else r["note"]
        where = ", ".join(str(n) for n in lines[:3]) + ("…" if len(lines) > 3 else "")
        out.append(f"{i}. {LABELS[r['kind']]}：{codes}")
        out.append(f"   {where}行目 {url}")
        if r["final"] != url:
            out.append(f"   着いたURL {r['final']}")
    return out


def stop(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def main():
    p = argparse.ArgumentParser(description="原稿の中のURLが開けるかを一覧にする")
    p.add_argument("target", help="確かめる原稿（Markdownやテキスト）")
    p.add_argument("--timeout", type=float, default=10.0, help="1回の問い合わせを待つ秒数（既定10）")
    p.add_argument("--wait", type=float, default=0.3, help="問い合わせの間をあける秒数（既定0.3）")
    p.add_argument("--ignore", action="append", default=[], help="この文字を含むURLは確かめない（何回でも指定できる）")
    p.add_argument("-o", "--output", help="結果を書き出すファイル（すでにあるときは止まる）")
    a = p.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:
            pass

    if a.timeout <= 0:
        stop("--timeout は0より大きい秒数で指定してください")
    if a.wait < 0:
        stop("--wait は0以上で指定してください")
    target = Path(a.target)
    if not target.exists():
        stop(f"{target} が見つかりません")
    if not target.is_file():
        stop(f"{target} はファイルではありません（フォルダーではなく原稿のファイルを渡してください）")
    out = Path(a.output) if a.output else None
    if out is not None:
        if out.exists():
            stop(f"{out} はすでにあります（上書きしないので、別の名前を指定してください）")
        if not out.parent.is_dir():
            stop(f"{out.parent} というフォルダーがありません")
    try:
        text = target.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        stop(f"{target} をUTF-8の文章として読めません（画像やPDFではなく、原稿のファイルを渡してください）")

    urls = find_urls(text, a.ignore)
    if not urls:
        stop(f"{target} にURLが1件も見つかりません（ファイルを取り違えていないか確かめてください）")

    rows = []
    for i, (url, lines) in enumerate(urls.items()):
        if i:
            time.sleep(a.wait)
        rows.append((url, lines, check(url, a.timeout)))

    counts = {}
    for _, _, r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    summary = "・".join(f"{LABELS[k]} {n}" for k, n in counts.items())
    lines = [f"# URLの確認（{target.name}・{time.strftime('%Y-%m-%d %H:%M')}）", ""]
    lines += listing(rows)
    lines += ["", f"URL {len(rows)}件（重複を除く）・{summary}"]
    report = "\n".join(lines)

    print(report)
    if out is not None:
        try:
            with open(out, "x", encoding="utf-8", newline="\n") as f:
                f.write(report + "\n")
        except FileExistsError:
            stop(f"{out} はすでにあります（上書きしないので、別の名前を指定してください）")
        print(f"\n{out} に書き出しました")
    return 0 if all(r["kind"] in GOOD for _, _, r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
