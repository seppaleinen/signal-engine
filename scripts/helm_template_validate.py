#!/usr/bin/env python3
"""Validate rendered Helm template output for Helm whitespace / template errors.

Checks three classes of defect that `helm lint` misses:

1. EMPTY KEYS — a YAML key with no value and no children (e.g. `env:` rendered
   with nothing under it because the surrounding `{{- range }}` block produced
   zero items). Helm lint does not flag these; they surface as confusing
   downstream errors or silently-dropped fields.

2. --- ON SAME LINE AS VALUE — a YAML document separator `---` that leaked
   onto the same line as a value (e.g. `apiVersion: v1---`). This happens when
   a Helm whitespace-trim comment (`{{- ... -}}`) eats the newline that should
   have separated the value from the next document.

3. UNPARSEABLE DOCUMENTS — the rendered YAML fails to parse at all.

Usage:
    python3 scripts/helm_template_validate.py <rendered_yaml_file> [chart_path]

Exit codes: 0 = clean, 1 = errors found, 2 = usage error.
"""

import re
import sys
import yaml


def check_dashdash_on_value(text):
    """Flag `---` that appears after a non-whitespace character on a value line."""
    failures = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("-"):
            # Real document separators (and YAML tag anchors like `!foo`).
            continue
        if "---" in line:
            # `---` inside a quoted string is fine; flag unquoted occurrences.
            if re.search(r'(?<!")---(?!")', line):
                failures.append(
                    f"  line {lineno}: '---' on same line as a value: {line!r}"
                )
    return failures


def check_unparseable(text):
    """Return a failure string if the YAML fails to parse, else []."""
    try:
        list(yaml.safe_load_all(text))
    except yaml.YAMLError as exc:
        return [f"  YAML parse error: {str(exc).splitlines()[0]}"]
    return []


def check_empty_keys(text):
    """Flag YAML keys with no value and no children (leaf-with-no-value)."""
    failures = []
    key_re = re.compile(r'^(\s*)([\w][\w.-]*):\s*$')
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = key_re.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        key = m.group(2)
        # Look ahead for the next non-blank line.
        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if j >= len(lines):
            failures.append(
                f"  line {i+1}: empty key at end of document: {key!r}"
            )
            continue
        next_indent = len(lines[j]) - len(lines[j].lstrip())
        if next_indent <= indent:
            failures.append(
                f"  line {i+1}: empty key with no children: {key!r}"
            )
    return failures


def main():
    if len(sys.argv) < 2:
        print("usage: helm_template_validate.py <rendered_yaml_file> [chart_path]",
              file=sys.stderr)
        return 2

    path = sys.argv[1]
    chart_path = sys.argv[2] if len(sys.argv) > 2 else "charts/signal-engine"

    try:
        with open(path, "r") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"helm-template-validate: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    failures = []
    failures.extend(check_dashdash_on_value(text))
    failures.extend(check_unparseable(text))
    failures.extend(check_empty_keys(text))

    if failures:
        print(f"helm-template-validate: {len(failures)} error(s) in "
              f"rendered output for {chart_path}")
        for f in failures:
            print(f)
        return 1

    docs = list(yaml.safe_load_all(text))
    print(f"helm-template-validate: OK — {len(docs)} document(s) rendered cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())