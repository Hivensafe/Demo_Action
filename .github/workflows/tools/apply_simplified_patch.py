#!/usr/bin/env python3

import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_sections(lines):
    sections = []
    current = None

    for line in lines:
        if line.startswith("diff --git "):
            if current is not None:
                sections.append(current)
            current = {"header": [line], "body": []}
            continue

        if current is None:
            continue

        if line.startswith("@@"):
            current["body"].append(line)
        elif current["body"]:
            current["body"].append(line)
        else:
            current["header"].append(line)

    if current is not None:
        sections.append(current)

    return sections


def target_path_from_header(header_lines):
    for line in header_lines:
        if line.startswith("+++ b/"):
            return line[6:]
    for line in header_lines:
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4 and parts[3].startswith("b/"):
                return parts[3][2:]
    fail("unable to determine target path from patch header")


def split_hunks(body_lines):
    hunks = []
    current = None

    for line in body_lines:
        if line.startswith("@@"):
            if current is not None:
                hunks.append(current)
            current = []
            continue

        if current is None:
            continue

        current.append(line)

    if current is not None:
        hunks.append(current)

    return hunks


def build_chunks(hunk_lines):
    old_lines = []
    new_lines = []

    for line in hunk_lines:
        if line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        else:
            old_lines.append(line)
            new_lines.append(line)

    return "\n".join(old_lines), "\n".join(new_lines)


def apply_hunks(file_path: Path, hunks):
    original = file_path.read_text(encoding="utf-8")
    normalized = original.replace("\r\n", "\n")

    for index, hunk in enumerate(hunks, start=1):
        old_chunk, new_chunk = build_chunks(hunk)
        occurrences = normalized.count(old_chunk)
        if occurrences != 1:
            fail(
                f"{file_path}: hunk {index} matched {occurrences} locations, expected 1"
            )
        normalized = normalized.replace(old_chunk, new_chunk, 1)

    file_path.write_text(normalized, encoding="utf-8", newline="\n")


def main():
    if len(sys.argv) != 3:
        fail("usage: apply_simplified_patch.py <patch-file> <source-root>")

    patch_file = Path(sys.argv[1])
    source_root = Path(sys.argv[2])

    if not patch_file.is_file():
        fail(f"patch file not found: {patch_file}")
    if not source_root.is_dir():
        fail(f"source root not found: {source_root}")

    lines = patch_file.read_text(encoding="utf-8").splitlines()
    sections = parse_sections(lines)
    if not sections:
        fail("no file sections found in patch")

    for section in sections:
        relative_path = target_path_from_header(section["header"])
        target_file = source_root / relative_path
        if not target_file.is_file():
            fail(f"target file not found: {target_file}")

        hunks = split_hunks(section["body"])
        if not hunks:
            fail(f"no hunks found for {relative_path}")

        apply_hunks(target_file, hunks)
        print(f"patched {relative_path}")


if __name__ == "__main__":
    main()