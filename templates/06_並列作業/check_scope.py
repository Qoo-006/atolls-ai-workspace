#!/usr/bin/env python3
"""worktreeの変更が、依頼書で決めた「触ってよいファイル」の中に収まっているかを確かめる

使い方（worktreeのフォルダーの中で実行する）
  python3 check_scope.py --base main --allow src/sort.py --allow tests/
  python3 check_scope.py --base main --allow-file allow.txt --out ../受け入れ記録_sort.md
  python3 check_scope.py -C ../myapp-sort --base main --allow src/sort.py

見ること
  1 mainから分かれた後の変更（コミット済み・未コミット・gitに入っていないファイル）が、触ってよいファイルの中だけか
  2 未コミットの変更や、gitに入っていないファイルが残っていないか
  3 mainへ早送りで統合できるか（mainがこのブランチの祖先か）

触ってよいファイルの書き方（リポジトリの一番上からの相対パス）
  src/sort.py   そのファイルだけ
  tests/        そのフォルダーの下全部（末尾の / は省いてもよい）
  src/*.py      * は何文字でも当たる（フォルダーの区切りもまたぐ）
  絶対パス、.. を含むもの、* だけのもの（全部を許す指定）は受け付けずに止まる

終了コード
  0 問題なし ／ 1 確認が必要な点がある ／ 2 実行できなかった（指定の誤り・フォルダーが無い等）

このスクリプトはファイルの書き換え・コミット・統合をしない
--out を付けたときだけ結果をファイルに書き、同じ名前のファイルがあれば何もせずに止まる
標準ライブラリだけで書いた（Windowsは python3 を py -3 に置き換える）
動作を確かめた範囲: macOS 26・Python 3.14・git 2.50 で試験した。Windows実機と他のPython・gitの版は未確認
"""
import argparse
import fnmatch
import os
import subprocess
import sys


def git(args, cwd, check=True):
    """gitを実行して、標準出力を文字列で返す"""
    proc = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError("git " + " ".join(args) + " が失敗した: " + err)
    return proc.returncode, out


def split_z(text):
    """-z の出力（区切りがNUL文字）を分ける"""
    return [p for p in text.split("\0") if p]


GLOB_CHARS = set("*?[")


def read_patterns(args):
    """触ってよいファイルの指定を集めて、確認にならない書き方を弾く"""
    patterns = list(args.allow or [])
    if args.allow_file:
        if not os.path.isfile(args.allow_file):
            raise ValueError("--allow-file " + args.allow_file + " がファイルとして見つからない")
        with open(args.allow_file, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    cleaned = []
    for raw in patterns:
        p = raw.strip().replace("\\", "/")
        while p.startswith("./"):
            p = p[2:]
        if not p:
            continue
        if p.startswith("/") or (len(p) > 1 and p[1] == ":"):
            raise ValueError("「" + raw + "」は絶対パスになっている。リポジトリの中の相対パスで書く")
        if ".." in p.split("/"):
            raise ValueError("「" + raw + "」に .. が入っている。リポジトリの中の相対パスで書く")
        if p.strip("*/") == "":
            raise ValueError("「" + raw + "」は全部のファイルを許すので確認にならない")
        if p.count("[") != p.count("]"):
            raise ValueError("「" + raw + "」の [ と ] の数が合っていない")
        cleaned.append(p)
    return cleaned


def allowed(path, patterns):
    for p in patterns:
        if p.endswith("/"):
            if path.startswith(p):
                return True
        elif GLOB_CHARS & set(p):
            if fnmatch.fnmatchcase(path, p):
                return True
        elif path == p or path.startswith(p + "/"):
            # * などを含まない名前は、そのファイルか、その名前のフォルダーの下全部
            return True
    return False


def parse_status(text):
    """git status --porcelain=v1 -z を、未コミットの変更とgitに入っていないファイルに分ける"""
    changed, untracked = [], []
    parts = split_z(text)
    i = 0
    while i < len(parts):
        entry = parts[i]
        code, path = entry[:2], entry[3:]
        if code == "??":
            untracked.append(path)
        else:
            changed.append(path)
            if "R" in code or "C" in code:
                # 名前の変更は、元の名前が次の要素に入っている
                i += 1
                if i < len(parts):
                    changed.append(parts[i])
        i += 1
    return changed, untracked


def main():
    ap = argparse.ArgumentParser(
        description="worktreeの変更が、触ってよいファイルの中だけかを確かめる"
    )
    ap.add_argument("--base", default="main", help="統合先のブランチ（既定 main）")
    ap.add_argument("--allow", action="append", help="触ってよいファイル（何回でも指定できる）")
    ap.add_argument("--allow-file", help="触ってよいファイルを1行に1つ書いたテキスト")
    ap.add_argument("-C", dest="repo", default=".", help="確かめるworktreeのフォルダー（既定は今のフォルダー）")
    ap.add_argument("--out", help="結果を書き出すファイル（既にあれば書かずに止まる）")
    args = ap.parse_args()

    if args.out:
        if os.path.exists(args.out):
            print("書き出し先 " + args.out + " が既にあるので、何もせずに止めた", file=sys.stderr)
            print("別の名前を付けるか、中身を確かめてから自分で動かす", file=sys.stderr)
            return 2
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if not os.path.isdir(out_dir):
            print("書き出し先のフォルダー " + out_dir + " が無い", file=sys.stderr)
            return 2

    try:
        patterns = read_patterns(args)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print("--allow-file を読めなかった: " + str(e), file=sys.stderr)
        return 2
    if not patterns:
        print("触ってよいファイルが1つも指定されていない（--allow か --allow-file で指定する）", file=sys.stderr)
        return 2

    if not os.path.isdir(args.repo):
        print("-C で指定したフォルダー " + args.repo + " が見つからない（フォルダーを指定する）", file=sys.stderr)
        return 2

    try:
        code, _ = git(["rev-parse", "--is-inside-work-tree"], args.repo, check=False)
        if code != 0:
            print(os.path.abspath(args.repo) + " はgitのリポジトリの中ではない", file=sys.stderr)
            return 2
        _, top = git(["rev-parse", "--show-toplevel"], args.repo)
        top = top.strip()
        code, _ = git(["rev-parse", "--verify", "--quiet", args.base + "^{commit}"], top, check=False)
        if code != 0:
            print("統合先のブランチ " + args.base + " が見つからない", file=sys.stderr)
            return 2
        _, branch = git(["rev-parse", "--abbrev-ref", "HEAD"], top)
        branch = branch.strip()
        if branch == args.base:
            print("今のフォルダーは " + args.base + " そのものを開いている", file=sys.stderr)
            print("確かめたい仕事のworktreeの中で実行するか、-C でそのフォルダーを指定する", file=sys.stderr)
            return 2
        code, mb = git(["merge-base", args.base, "HEAD"], top, check=False)
        if code != 0:
            print(args.base + " とこのブランチに共通の祖先が無い", file=sys.stderr)
            return 2
        mb = mb.strip()
        _, committed = git(["diff", "--name-only", "--no-renames", "-z", mb, "HEAD"], top)
        committed = split_z(committed)
        _, status = git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], top)
        uncommitted, untracked = parse_status(status)
        _, ahead = git(["rev-list", "--count", args.base + "..HEAD"], top)
        ahead = int(ahead.strip() or 0)
        ff_code, _ = git(["merge-base", "--is-ancestor", args.base, "HEAD"], top, check=False)
    except (OSError, RuntimeError) as e:
        print("gitを実行できなかった: " + str(e), file=sys.stderr)
        return 2

    touched = sorted(set(committed) | set(uncommitted) | set(untracked))
    outside = [p for p in touched if not allowed(p, patterns)]
    ff_ok = ff_code == 0

    lines = []
    name = branch if branch != "HEAD" else "（ブランチ名なし・detached HEAD）"
    lines.append("# 受け入れ確認  " + name + " → " + args.base)
    lines.append("")
    lines.append("- worktree: " + top)
    lines.append("- 触ってよいファイル: " + "、".join(patterns))
    lines.append("- " + args.base + " から分かれた後のコミット: " + str(ahead) + "件")
    lines.append("")
    lines.append("## 変更されたファイル " + str(len(touched)) + "件")
    for p in touched:
        lines.append(("- OK  " if allowed(p, patterns) else "- 外  ") + p)
    lines.append("")
    lines.append("## 残っているもの")
    lines.append("- 未コミットの変更: " + str(len(set(uncommitted))) + "件")
    for p in sorted(set(uncommitted)):
        lines.append("    - " + p)
    lines.append("- gitに入っていないファイル: " + str(len(untracked)) + "件")
    for p in sorted(untracked):
        lines.append("    - " + p)
    lines.append("")
    lines.append("## " + args.base + " への早送り: " + ("できる" if ff_ok else "できない（" + args.base + " が先に進んでいる）"))
    if branch == "HEAD":
        lines.append("- ブランチ名が無いので、統合の前に git switch -c <名前> で名前を付ける")
    lines.append("")

    problems = []
    if outside:
        problems.append("触ってよい範囲の外 " + str(len(outside)) + "件")
    if uncommitted:
        problems.append("未コミットの変更あり")
    if untracked:
        problems.append("gitに入っていないファイルあり")
    if not ff_ok:
        problems.append("早送りできない")
    if ahead == 0 and not uncommitted and not untracked:
        problems.append("統合するコミットが無い")

    if problems:
        lines.append("結果: 要確認（" + "／".join(problems) + "）")
    else:
        lines.append("結果: 問題なし（受け入れ確認表の残りの項目を自分で確かめる）")
    report = "\n".join(lines) + "\n"
    print(report, end="")

    if args.out:
        try:
            with open(args.out, "x", encoding="utf-8") as f:
                f.write(report)
            print("書き出した: " + args.out)
        except FileExistsError:
            print("書き出し先 " + args.out + " が途中でできていたので書かなかった", file=sys.stderr)
            return 2
        except OSError as e:
            print("書き出せなかった: " + str(e), file=sys.stderr)
            return 2

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
