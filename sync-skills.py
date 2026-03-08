#!/usr/bin/env python3
"""
按映射表把 GitHub 仓库子目录同步到本地目录。

映射文件默认是 skills-map.txt，格式如下：
https://github.com/owner/repo/tree/main/path/to/dir => local-dir

默认会同步到当前目录下的 skills/ 子目录。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urlparse


@dataclass(frozen=True)
class Mapping:
    remote_url: str
    owner: str
    repo: str
    ref: str
    remote_path: str
    local_dir: str


def run(cmd: List[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        joined = " ".join(cmd)
        raise RuntimeError(f"命令失败: {joined}\n{result.stdout.strip()}")
    return result.stdout


def ensure_git() -> None:
    try:
        run(["git", "--version"])
    except Exception as exc:
        raise RuntimeError("未检测到可用的 git，请先安装并确保在 PATH 中。") from exc


def parse_remote_url(remote_url: str) -> Tuple[str, str, str, str]:
    parsed = urlparse(remote_url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "github.com":
        raise ValueError("仅支持 https://github.com/.../tree/... 格式。")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 5 or parts[2] != "tree":
        raise ValueError("URL 必须是 /<owner>/<repo>/tree/<ref>/<path> 结构。")

    owner, repo = parts[0], parts[1]
    ref = parts[3]
    remote_path = "/".join(parts[4:]).strip("/")
    if not remote_path:
        raise ValueError("URL 中缺少远程目录路径。")

    return owner, repo, ref, remote_path


def parse_mapping_line(line: str, lineno: int) -> Mapping:
    if "=>" not in line:
        raise ValueError("缺少 '=>' 分隔符。")

    remote, local = [x.strip() for x in line.split("=>", 1)]
    if not remote or not local:
        raise ValueError("远程地址和本地目录都不能为空。")
    if local in {".", "/", ""}:
        raise ValueError("本地目录不能是 '.' 或 '/'。")

    owner, repo, ref, remote_path = parse_remote_url(remote)
    return Mapping(
        remote_url=remote,
        owner=owner,
        repo=repo,
        ref=ref,
        remote_path=remote_path,
        local_dir=local,
    )


def load_mappings(mapping_file: Path) -> List[Mapping]:
    if not mapping_file.exists():
        raise FileNotFoundError(f"映射文件不存在: {mapping_file}")

    mappings: List[Mapping] = []
    for lineno, raw in enumerate(mapping_file.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            mappings.append(parse_mapping_line(line, lineno))
        except ValueError as exc:
            raise ValueError(f"{mapping_file}:{lineno}: {exc}") from exc

    if not mappings:
        raise ValueError(f"映射文件为空: {mapping_file}")

    return mappings


def safe_dest(dest_root: Path, local_dir: str) -> Path:
    root = dest_root.resolve()
    dest = (root / local_dir).resolve()
    try:
        dest.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"本地目录越界: {local_dir}") from exc
    if dest == root:
        raise ValueError("本地目录不能指向目标根目录本身。")
    return dest


def validate_unique_destinations(dest_root: Path, mappings: Iterable[Mapping]) -> None:
    seen: Dict[Path, Mapping] = {}
    for item in mappings:
        dest = safe_dest(dest_root, item.local_dir)
        old = seen.get(dest)
        if old is not None and old.remote_url != item.remote_url:
            raise ValueError(
                f"本地目录冲突: {dest}\n"
                f"  - {old.remote_url}\n"
                f"  - {item.remote_url}"
            )
        seen[dest] = item


def clone_sparse_group(
    owner: str, repo: str, ref: str, remote_paths: Iterable[str], workdir: Path
) -> Path:
    repo_url = f"https://github.com/{owner}/{repo}.git"
    checkout_dir = workdir / f"{owner}_{repo}_{ref}".replace("/", "_")
    run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            "--branch",
            ref,
            repo_url,
            str(checkout_dir),
        ]
    )
    run(
        [
            "git",
            "-C",
            str(checkout_dir),
            "sparse-checkout",
            "set",
            "--no-cone",
            *sorted(set(remote_paths)),
        ]
    )
    return checkout_dir


def sync_one(src: Path, dest: Path, dry_run: bool) -> None:
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"远程目录不存在: {src}")

    if dry_run:
        return

    if dest.exists():
        if not dest.is_dir():
            raise RuntimeError(f"本地目标不是目录: {dest}")
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)


def main() -> int:
    parser = argparse.ArgumentParser(description="按映射表同步 GitHub 目录到本地")
    parser.add_argument("--map", default="skills-map.txt", help="映射文件路径")
    parser.add_argument("--dest", default="skills", help="同步目标根目录（默认 ./skills）")
    parser.add_argument("--dry-run", action="store_true", help="只打印动作，不真正写文件")
    args = parser.parse_args()

    try:
        ensure_git()
        mapping_file = Path(args.map).expanduser()
        dest_root = Path(args.dest).expanduser()
        mappings = load_mappings(mapping_file)
        validate_unique_destinations(dest_root, mappings)
    except Exception as exc:
        print(f"初始化失败: {exc}", file=sys.stderr)
        return 1

    grouped: Dict[Tuple[str, str, str], List[Mapping]] = defaultdict(list)
    for item in mappings:
        grouped[(item.owner, item.repo, item.ref)].append(item)

    failures: List[str] = []

    with tempfile.TemporaryDirectory(prefix="skill-sync-") as temp:
        tempdir = Path(temp)
        for (owner, repo, ref), items in grouped.items():
            print(f"\n==> 拉取 {owner}/{repo}@{ref}")
            try:
                checkout_dir = clone_sparse_group(
                    owner=owner,
                    repo=repo,
                    ref=ref,
                    remote_paths=[x.remote_path for x in items],
                    workdir=tempdir,
                )
            except Exception as exc:
                msg = f"{owner}/{repo}@{ref} 拉取失败: {exc}"
                failures.append(msg)
                print(f"[失败] {msg}", file=sys.stderr)
                continue

            for item in items:
                dest = safe_dest(dest_root, item.local_dir)
                src = checkout_dir / item.remote_path
                print(f"  - {item.remote_url} => {dest}")
                try:
                    sync_one(src, dest, args.dry_run)
                except Exception as exc:
                    msg = f"{item.remote_url} 同步失败: {exc}"
                    failures.append(msg)
                    print(f"[失败] {msg}", file=sys.stderr)

    if failures:
        print("\n同步完成（有失败项）:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\nDry-run 完成，未写入任何文件。")
    else:
        print("\n全部同步完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
