#!/usr/bin/env python3

import re
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def replace_once(text: str, old: str, new: str, path: Path, description: str) -> str:
    occurrences = text.count(old)
    if occurrences != 1:
        fail(f"{path}: {description} matched {occurrences} locations, expected 1")
    return text.replace(old, new, 1)


def insert_once_after(text: str, anchor: str, insertion: str, path: Path, description: str) -> str:
    if insertion in text:
        return text

    occurrences = text.count(anchor)
    if occurrences != 1:
        fail(f"{path}: {description} anchor matched {occurrences} locations, expected 1")
    return text.replace(anchor, anchor + insertion, 1)


def apply_unicode_hard_fix(target_file: Path) -> bool:
    relative = target_file.as_posix().replace("\\", "/")
    text = target_file.read_text(encoding="utf-8").replace("\r\n", "\n")

    if relative.endswith("include/linux/unicode.h"):
        text = insert_once_after(
            text,
            "int utf8_validate(const struct unicode_map *um, const struct qstr *str);\n",
            "int utf8_has_unsafe_ignorables(const struct qstr *str);\n",
            target_file,
            "utf8_has_unsafe_ignorables declaration",
        )
    elif relative.endswith("fs/unicode/utf8-core.c"):
        text = insert_once_after(
            text,
            "#include <linux/errno.h>\n",
            "#include <linux/nls.h>\n",
            target_file,
            "nls include insertion",
        )

        helper_block = """

struct utf32_range {
	unicode_t first;
	unicode_t last;
};

static const struct utf32_range utf8_default_ignorable_ranges[] = {
	{ 0x00ad, 0x00ad },
	{ 0x034f, 0x034f },
	{ 0x061c, 0x061c },
	{ 0x115f, 0x1160 },
	{ 0x17b4, 0x17b5 },
	{ 0x180b, 0x180e },
	{ 0x200b, 0x200f },
	{ 0x202a, 0x202e },
	{ 0x2060, 0x206f },
	{ 0x3164, 0x3164 },
	{ 0xfe00, 0xfe0f },
	{ 0xfeff, 0xfeff },
	{ 0xffa0, 0xffa0 },
	{ 0xfff0, 0xfff8 },
	{ 0x1bca0, 0x1bca3 },
	{ 0x1d173, 0x1d17a },
	{ 0xe0000, 0xe007f },
	{ 0xe0100, 0xe01ef },
};

static bool utf8_is_default_ignorable(unicode_t codepoint)
{
	int i;

	for (i = 0; i < ARRAY_SIZE(utf8_default_ignorable_ranges); i++) {
		if (codepoint < utf8_default_ignorable_ranges[i].first)
			return false;
		if (codepoint <= utf8_default_ignorable_ranges[i].last)
			return true;
	}

	return false;
}

int utf8_has_unsafe_ignorables(const struct qstr *str)
{
	const u8 *s = (const u8 *)str->name;
	size_t len = str->len;

	while (len) {
		unicode_t codepoint;
		int clen;

		clen = utf8_to_utf32(s, len, &codepoint);
		if (clen < 0)
			return -EINVAL;
		if (utf8_is_default_ignorable(codepoint))
			return 1;

		s += clen;
		len -= clen;
	}

	return 0;
}
EXPORT_SYMBOL(utf8_has_unsafe_ignorables);

static int utf8_reject_unsafe_ignorables(const struct qstr *str)
{
	return utf8_has_unsafe_ignorables(str) ? -EINVAL : 0;
}
"""
        text = insert_once_after(
            text,
            '#include "utf8n.h"\n',
            helper_block,
            target_file,
            "unicode helper block insertion",
        )

        text = replace_once(
            text,
            "int utf8_validate(const struct unicode_map *um, const struct qstr *str)\n{\n\tif (utf8nlen(um, UTF8_NFDI, str->name, str->len) < 0)\n\t\treturn -1;\n\treturn 0;\n}\n",
            "int utf8_validate(const struct unicode_map *um, const struct qstr *str)\n{\n\tif (utf8_has_unsafe_ignorables(str))\n\t\treturn -1;\n\tif (utf8nlen(um, UTF8_NFDI, str->name, str->len) < 0)\n\t\treturn -1;\n\treturn 0;\n}\n",
            target_file,
            "utf8_validate body",
        )

        text = replace_once(
            text,
            "int utf8_strncmp(const struct unicode_map *um,\n\t\t const struct qstr *s1, const struct qstr *s2)\n{\n\tstruct utf8cursor cur1, cur2;\n\tint c1, c2;\n\n\tif (utf8ncursor(&cur1, um, UTF8_NFDI, s1->name, s1->len) < 0)\n",
            "int utf8_strncmp(const struct unicode_map *um,\n\t\t const struct qstr *s1, const struct qstr *s2)\n{\n\tstruct utf8cursor cur1, cur2;\n\tint c1, c2;\n\tint ret;\n\n\tret = utf8_reject_unsafe_ignorables(s1);\n\tif (ret)\n\t\treturn ret;\n\tret = utf8_reject_unsafe_ignorables(s2);\n\tif (ret)\n\t\treturn ret;\n\n\tif (utf8ncursor(&cur1, um, UTF8_NFDI, s1->name, s1->len) < 0)\n",
            target_file,
            "utf8_strncmp guard insertion",
        )

        text = replace_once(
            text,
            "int utf8_strncasecmp(const struct unicode_map *um,\n\t\t     const struct qstr *s1, const struct qstr *s2)\n{\n\tstruct utf8cursor cur1, cur2;\n\tint c1, c2;\n\n\tif (utf8ncursor(&cur1, um, UTF8_NFDICF, s1->name, s1->len) < 0)\n",
            "int utf8_strncasecmp(const struct unicode_map *um,\n\t\t     const struct qstr *s1, const struct qstr *s2)\n{\n\tstruct utf8cursor cur1, cur2;\n\tint c1, c2;\n\tint ret;\n\n\tret = utf8_reject_unsafe_ignorables(s1);\n\tif (ret)\n\t\treturn ret;\n\tret = utf8_reject_unsafe_ignorables(s2);\n\tif (ret)\n\t\treturn ret;\n\n\tif (utf8ncursor(&cur1, um, UTF8_NFDICF, s1->name, s1->len) < 0)\n",
            target_file,
            "utf8_strncasecmp guard insertion",
        )

        text = replace_once(
            text,
            "int utf8_strncasecmp_folded(const struct unicode_map *um,\n\t\t\t    const struct qstr *cf,\n\t\t\t    const struct qstr *s1)\n{\n\tstruct utf8cursor cur1;\n\tint c1, c2;\n\tint i = 0;\n\n\tif (utf8ncursor(&cur1, um, UTF8_NFDICF, s1->name, s1->len) < 0)\n",
            "int utf8_strncasecmp_folded(const struct unicode_map *um,\n\t\t\t    const struct qstr *cf,\n\t\t\t    const struct qstr *s1)\n{\n\tstruct utf8cursor cur1;\n\tint c1, c2;\n\tint i = 0;\n\tint ret;\n\n\tret = utf8_reject_unsafe_ignorables(cf);\n\tif (ret)\n\t\treturn ret;\n\tret = utf8_reject_unsafe_ignorables(s1);\n\tif (ret)\n\t\treturn ret;\n\n\tif (utf8ncursor(&cur1, um, UTF8_NFDICF, s1->name, s1->len) < 0)\n",
            target_file,
            "utf8_strncasecmp_folded guard insertion",
        )

        text = replace_once(
            text,
            "int utf8_casefold(const struct unicode_map *um, const struct qstr *str,\n\t\t  unsigned char *dest, size_t dlen)\n{\n\tstruct utf8cursor cur;\n\tsize_t nlen = 0;\n\n\tif (utf8ncursor(&cur, um, UTF8_NFDICF, str->name, str->len) < 0)\n",
            "int utf8_casefold(const struct unicode_map *um, const struct qstr *str,\n\t\t  unsigned char *dest, size_t dlen)\n{\n\tstruct utf8cursor cur;\n\tsize_t nlen = 0;\n\tint ret;\n\n\tret = utf8_reject_unsafe_ignorables(str);\n\tif (ret)\n\t\treturn ret;\n\n\tif (utf8ncursor(&cur, um, UTF8_NFDICF, str->name, str->len) < 0)\n",
            target_file,
            "utf8_casefold guard insertion",
        )

        text = replace_once(
            text,
            "int utf8_casefold_hash(const struct unicode_map *um, const void *salt,\n\t\t       struct qstr *str)\n{\n\tstruct utf8cursor cur;\n\tint c;\n\tunsigned long hash = init_name_hash(salt);\n\n\tif (utf8ncursor(&cur, um, UTF8_NFDICF, str->name, str->len) < 0)\n",
            "int utf8_casefold_hash(const struct unicode_map *um, const void *salt,\n\t\t       struct qstr *str)\n{\n\tstruct utf8cursor cur;\n\tint c;\n\tint ret;\n\tunsigned long hash = init_name_hash(salt);\n\n\tret = utf8_reject_unsafe_ignorables(str);\n\tif (ret)\n\t\treturn ret;\n\n\tif (utf8ncursor(&cur, um, UTF8_NFDICF, str->name, str->len) < 0)\n",
            target_file,
            "utf8_casefold_hash guard insertion",
        )

        text = replace_once(
            text,
            "int utf8_normalize(const struct unicode_map *um, const struct qstr *str,\n\t\t   unsigned char *dest, size_t dlen)\n{\n\tstruct utf8cursor cur;\n\tssize_t nlen = 0;\n\n\tif (utf8ncursor(&cur, um, UTF8_NFDI, str->name, str->len) < 0)\n",
            "int utf8_normalize(const struct unicode_map *um, const struct qstr *str,\n\t\t   unsigned char *dest, size_t dlen)\n{\n\tstruct utf8cursor cur;\n\tssize_t nlen = 0;\n\tint ret;\n\n\tret = utf8_reject_unsafe_ignorables(str);\n\tif (ret)\n\t\treturn ret;\n\n\tif (utf8ncursor(&cur, um, UTF8_NFDI, str->name, str->len) < 0)\n",
            target_file,
            "utf8_normalize guard insertion",
        )
    elif relative.endswith("fs/ext4/namei.c"):
        text = replace_once(
            text,
            "\tstruct fscrypt_str *cf_name = &name->cf_name;\n\tstruct dx_hash_info *hinfo = &name->hinfo;\n\tint len;\n",
            "\tstruct fscrypt_str *cf_name = &name->cf_name;\n\tstruct dx_hash_info *hinfo = &name->hinfo;\n\tint len;\n\tint ret;\n",
            target_file,
            "ext4 local ret declaration",
        )
        text = replace_once(
            text,
            "\tif (!IS_CASEFOLDED(dir) ||\n\t    (IS_ENCRYPTED(dir) && !fscrypt_has_encryption_key(dir))) {\n\t\tcf_name->name = NULL;\n\t\treturn 0;\n\t}\n\n\tcf_name->name = kmalloc(EXT4_NAME_LEN, GFP_NOFS);\n",
            "\tif (!IS_CASEFOLDED(dir) ||\n\t    (IS_ENCRYPTED(dir) && !fscrypt_has_encryption_key(dir))) {\n\t\tcf_name->name = NULL;\n\t\treturn 0;\n\t}\n\n\tret = utf8_has_unsafe_ignorables(iname);\n\tif (ret > 0)\n\t\treturn -EINVAL;\n\n\tcf_name->name = kmalloc(EXT4_NAME_LEN, GFP_NOFS);\n",
            target_file,
            "ext4 ignorable check insertion",
        )
    elif relative.endswith("fs/f2fs/dir.c"):
        text = replace_once(
            text,
            "#if IS_ENABLED(CONFIG_UNICODE)\n\tstruct super_block *sb = dir->i_sb;\n\n\tif (IS_CASEFOLDED(dir) &&\n",
            "#if IS_ENABLED(CONFIG_UNICODE)\n\tstruct super_block *sb = dir->i_sb;\n\tint ret;\n\n\tif (IS_CASEFOLDED(dir) &&\n",
            target_file,
            "f2fs local ret declaration",
        )
        text = replace_once(
            text,
            "\tif (IS_CASEFOLDED(dir) &&\n\t    !is_dot_dotdot(fname->usr_fname->name, fname->usr_fname->len)) {\n\t\tfname->cf_name.name = f2fs_kmem_cache_alloc(f2fs_cf_name_slab,\n",
            "\tif (IS_CASEFOLDED(dir) &&\n\t    !is_dot_dotdot(fname->usr_fname->name, fname->usr_fname->len)) {\n\t\tret = utf8_has_unsafe_ignorables(fname->usr_fname);\n\t\tif (ret > 0)\n\t\t\treturn -EINVAL;\n\n\t\tfname->cf_name.name = f2fs_kmem_cache_alloc(f2fs_cf_name_slab,\n",
            target_file,
            "f2fs ignorable check insertion",
        )
    else:
        return False

    target_file.write_text(text, encoding="utf-8", newline="\n")
    return True


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

        try:
            apply_hunks(target_file, hunks)
        except SystemExit:
            if not apply_unicode_hard_fix(target_file):
                raise
        print(f"patched {relative_path}")


if __name__ == "__main__":
    main()