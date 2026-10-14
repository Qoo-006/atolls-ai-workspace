#!/usr/bin/env python3
"""KnowBrain: local Markdown setup, literal search, and manual summary recording."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOMAINS = ("school", "work", "personal")
DOMAIN_NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def local(relative):
    """Reject symlinks/junctions, including in ancestors below the kit root."""
    path = ROOT / relative
    path.relative_to(ROOT)
    current = ROOT
    for part in Path(relative).parts:
        if part in ("..", ".") or Path(part).is_absolute():
            raise ValueError("キット外へのパスは使用できません")
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("リンクを含む保存先は使用できません")
    if not path.resolve().is_relative_to(ROOT) or path.resolve() != path:
        raise ValueError("キット外へのパスは使用できません")
    return path


def domains():
    """Default domains plus notes/<name>/ folders that have PURPOSE.md."""
    found = list(DEFAULT_DOMAINS)
    try:
        notes = local("notes")
        children = sorted(notes.iterdir()) if notes.is_dir() else []
    except (OSError, ValueError):
        children = []
    for child in children:
        name = child.name
        if name in found or not DOMAIN_NAME.fullmatch(name) or name.upper() in RESERVED:
            continue
        try:
            if local(f"notes/{name}").is_dir() and local(f"notes/{name}/PURPOSE.md").is_file():
                found.append(name)
        except (OSError, ValueError):
            continue
    return found


def known_domain(name):
    available = domains()
    if name not in available:
        raise ValueError("ドメインがありません。使えるドメイン: " + ", ".join(available))
    return name


def label_of(domain):
    """Display name from the PURPOSE.md heading, or the folder name."""
    try:
        first = local(f"notes/{domain}/PURPOSE.md").read_text(encoding="utf-8").splitlines()[0]
        match = re.fullmatch(r"# (.+) の目的", first)
        return match.group(1) if match else domain
    except (OSError, ValueError, IndexError, UnicodeError):
        return domain


def note_files(domain, label):
    return {
        f"notes/{domain}/PURPOSE.md": (
            f"# {label} の目的\n\n"
            "## 頼みたいこと\n自分の目的を書く。\n\n"
            "## 読んでよい資料\n今回必要なファイルだけを指定する。\n\n"
            "## 完了条件\n結果をどう確認するかを書く。\n"
        ),
        f"notes/{domain}/INDEX.md": (
            f"# {label} の索引\n\n- [目的](PURPOSE.md)\n"
            "- [引継ぎ](HANDOFF.md)\n\n"
            "記録は records に保存する。必要な記録へのリンクをここに手で追加する。\n"
        ),
        f"notes/{domain}/HANDOFF.md": (
            f"# {label} の引継ぎ\n\n## 目的\n\n## 決まったこと\n\n"
            "## 未確認\n\n## 次の作業\n\n## 読む記録\n"
        ),
    }


def rule_files(domain, label):
    body = (
        f"# {label} のルール\n\n"
        f"確認用識別子: BRAIN-{domain.upper()}\n\n"
        f"{label}の作業を扱う。目的・決定・未確認を分け、このドメインで守る条件をここに書き足す。\n\n"
        "別ドメインの記録は明示指定がある場合だけ参照する。\n"
    )
    return {
        f"docs/rules/{domain}.md": body,
        f".claude/rules/{domain}.md": f'---\npaths:\n  - "notes/{domain}/**/*.md"\n---\n\n' + body,
    }


def scaffold(names=None):
    names = domains() if names is None else names
    files = {"notes/INDEX.md": "# 記録の索引\n\n" + "\n".join(
        f"- [{label_of(domain)}]({domain}/INDEX.md)" for domain in names
    ) + "\n"}
    for domain in names:
        files.update(note_files(domain, label_of(domain)))
    return files


def preflight(directories, files):
    # Check every target before starting; nothing is created on a conflict.
    for name in directories:
        path = local(name)
        if path.exists() and not path.is_dir():
            raise ValueError(f"作成先に同名のファイルがあります: {name}")
    for name in files:
        path = local(name)
        if path.exists() and not path.is_file():
            raise ValueError(f"作成先に同名のディレクトリがあります: {name}")


def write_new(files):
    created = []
    for name, content in files.items():
        try:
            with local(name).open("x", encoding="utf-8", newline="\n") as out:
                out.write(content)
            created.append(name)
        except FileExistsError:
            pass
    return created


def setup():
    names = domains()
    files = scaffold(names)
    directories = ["notes"]
    for domain in names:
        directories += [f"notes/{domain}", f"notes/{domain}/records"]
    preflight(directories, files)
    for name in directories:
        local(name).mkdir(parents=True, exist_ok=True)
    created = write_new(files)
    print(f"setup: {len(created)} files created; existing files preserved")


def domain_add(args):
    name = args.name
    if not DOMAIN_NAME.fullmatch(name) or name.upper() in RESERVED:
        raise ValueError("nameは英小文字で始まる1〜32文字の英小文字・数字・-で指定してください（例: club、job-hunt）")
    label = (args.label or name).strip()
    if not label or len(label) > 40 or any(ord(c) < 32 or c in "[]()#" for c in label):
        raise ValueError("labelは1〜40文字で、改行と [ ] ( ) # を含めずに指定してください")
    if name in domains():
        raise ValueError("同じ名前のドメインがすでにあります")
    index = local("notes/INDEX.md")
    if not index.is_file():
        raise ValueError("先にsetupを実行してください")
    folder = local(f"notes/{name}")
    if folder.exists():
        raise ValueError(f"notes/{name} がすでにあります。中身を確認するか、別の名前にしてください")
    files = {**note_files(name, label), **rule_files(name, label)}
    directories = [f"notes/{name}", f"notes/{name}/records", "docs/rules", ".claude/rules"]
    preflight(directories, files)
    existing = [path for path in files if local(path).exists()]
    if existing:
        raise ValueError("既存のファイルがあるため作成しません: " + ", ".join(existing))
    for directory in directories:
        local(directory).mkdir(parents=True, exist_ok=True)
    created = write_new(files)
    link = f"- [{label}]({name}/INDEX.md)"
    text = index.read_text(encoding="utf-8")
    if f"({name}/INDEX.md)" not in text:
        with index.open("a", encoding="utf-8", newline="\n") as out:
            out.write(("" if text.endswith("\n") else "\n") + link + "\n")
        created.append("notes/INDEX.md（リンクを追加）")
    for path in created:
        print(path)
    print(f"domain add: {name} を作成しました。PURPOSE.mdとdocs/rules/{name}.mdを自分の用途に合わせて書き換えてください")


def record(args):
    if (not re.fullmatch(r"[\w-]{1,64}", args.name)
            or args.name.upper() in RESERVED):
        raise ValueError("nameは1〜64文字の英数字・日本語・_・-で指定してください")
    if args.stdin:
        content = sys.stdin.buffer.read().decode("utf-8-sig")
    else:
        content = args.text
    if not content.strip():
        raise ValueError("空の要約は保存できません")
    destination = local(f"notes/{known_domain(args.domain)}/records/{args.name}.md")
    if not destination.parent.is_dir():
        raise ValueError("先にsetupを実行してください")
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with destination.open("x", encoding="utf-8", newline="\n") as out:
        out.write(f"<!-- KnowBrain manual summary | {args.domain} | {stamp} -->\n\n")
        out.write(content.rstrip() + "\n")
    print(destination.relative_to(ROOT).as_posix())


def search(args):
    if not args.query.strip():
        raise ValueError("空の検索語は指定できません")
    base = local(f"notes/{known_domain(args.domain)}")
    if not base.is_dir():
        raise ValueError("先にsetupを実行してください")
    query = args.query.casefold()
    hits = 0
    for directory, folders, files in os.walk(base, followlinks=False):
        safe_folders = []
        for name in sorted(folders):
            try:
                local((Path(directory) / name).relative_to(ROOT))
                safe_folders.append(name)
            except ValueError:
                continue
        folders[:] = safe_folders
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            relative = (Path(directory) / name).relative_to(ROOT)
            try:
                path = local(relative)
            except ValueError:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if query in line.casefold():
                    print(f"{relative.as_posix()}:{number}: {line}")
                    hits += 1
                    if hits >= args.limit:
                        print("search: result limit reached")
                        return
    if not hits:
        print("search: 0 matches")


def doctor():
    issues = []
    required = list(scaffold()) + [
        "AGENTS.md", "CLAUDE.md", ".zed/settings.json",
        "docs/setup.md", "docs/prompts.md", "docs/hooks.md",
        "scripts/session_start.py",
    ]
    for domain in domains():
        required += [f"docs/rules/{domain}.md", f".claude/rules/{domain}.md"]
        try:
            if not local(f"notes/{domain}/records").is_dir():
                issues.append(f"missing: notes/{domain}/records/")
        except ValueError:
            issues.append(f"unsafe: notes/{domain}/records/")
    for host in (".agents", ".claude"):
        for skill in ("brain-record", "brain-context"):
            required.append(f"{host}/skills/{skill}/SKILL.md")
    for name in required:
        try:
            path = local(name)
            if not path.is_file():
                issues.append(f"missing: {name}")
        except ValueError:
            issues.append(f"unsafe: {name}")
    for name in [".zed/settings.json"] + [
        f"docs/hooks/{host}-{platform}.json"
        for host in ("claude", "codex") for platform in ("mac", "windows")
    ]:
        try:
            data = json.loads(local(name).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError()
            if name.startswith("docs/hooks/"):
                if set(data) != {"hooks"} or set(data["hooks"]) != {"SessionStart"}:
                    raise ValueError()
                groups = data["hooks"]["SessionStart"]
                if len(groups) != 1 or groups[0]["matcher"] != "startup|resume":
                    raise ValueError()
                handlers = groups[0]["hooks"]
                if len(handlers) != 1 or handlers[0]["type"] != "command":
                    raise ValueError()
                if handlers[0]["timeout"] != 10 or not handlers[0]["command"]:
                    raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            issues.append(f"invalid JSON/config: {name}")
    for issue in issues:
        print(issue)
    if issues:
        return 1
    print("doctor: OK (local files and JSON only; AI loading/login not tested)")
    return 0


def positive(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("limitは1以上で指定してください")
    return result


def main():
    parser = argparse.ArgumentParser(description="KnowBrain: ローカルの要約を保存・検索する")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("setup", help="不足するノート雛形だけを作成する")
    subs.add_parser("doctor", help="ローカル構成とJSONを検査する")
    finder = subs.add_parser("search", help="指定ドメイン内で文字列を検索する")
    finder.add_argument("query")
    finder.add_argument("--domain", required=True, help="notes/の中のドメイン名")
    finder.add_argument("--limit", type=positive, default=30)
    writer = subs.add_parser("record", help="確認した要約を新規ファイルに保存する")
    writer.add_argument("--domain", required=True, help="notes/の中のドメイン名")
    writer.add_argument("--name", required=True)
    source = writer.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--stdin", action="store_true", help="UTF-8の標準入力を読む")
    domain_parser = subs.add_parser("domain", help="ドメインを追加する")
    domain_subs = domain_parser.add_subparsers(dest="action", required=True)
    adder = domain_subs.add_parser("add", help="ノート・ルールの雛形を新規作成し、索引にリンクを足す")
    adder.add_argument("name", help="フォルダー名（英小文字で始まる英小文字・数字・-、1〜32文字）")
    adder.add_argument("--label", help="見出しに使う表示名（例: 就活）")
    args = parser.parse_args()
    try:
        if args.command == "setup":
            setup()
        elif args.command == "search":
            search(args)
        elif args.command == "record":
            record(args)
        elif args.command == "domain":
            domain_add(args)
        else:
            return doctor()
    except (OSError, ValueError, UnicodeError) as error:
        # Do not print OS errors containing local absolute paths or note text.
        if isinstance(error, FileExistsError):
            print("error: 同名の記録があります。別のnameを指定してください", file=sys.stderr)
        elif isinstance(error, (OSError, UnicodeError)):
            print("error: ファイルの種類・権限・UTF-8を確認してください", file=sys.stderr)
        else:
            print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    # PowerShell redirected output and Japanese terminals both use UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
