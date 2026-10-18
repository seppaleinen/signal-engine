#!/usr/bin/env bash
# helm-template-validate.sh — render a Helm chart template and check the
# rendered YAML for Helm whitespace / template errors BEFORE running
# `helm lint`. Catches three classes of defect that `helm lint` misses:
#
#   1. EMPTY KEYS — a YAML key with no value and no children (e.g. `env:`
#      rendered with nothing under it because the surrounding `{{- range }}`
#      block produced zero items). Helm lint does not flag these; they
#      surface as confusing downstream errors or silently-dropped fields.
#
#   2. --- ON SAME LINE AS VALUE — a YAML document separator `---` that
#      leaked onto the same line as a value (e.g. `apiVersion: v1---`).
#      This happens when a Helm whitespace-trim comment (`{{- ... -}}`)
#      eats the newline that should have separated the value from the
#      next document. Helm lint does not flag these; they corrupt the
#      following document.
#
#   3. UNPARSEABLE DOCUMENTS — the rendered YAML fails to parse at all
#      (truncated flow sequences, bad indentation, stray tokens).
#
# Usage:
#   ./scripts/helm-template-validate.sh [CHART_PATH] [RELEASE_NAME]
#
# Defaults: CHART_PATH=charts/signal-engine  RELEASE_NAME=test
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed (details on stderr)
#   2 — usage error (missing helm, missing chart, etc.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="${SCRIPT_DIR}/helm_template_validate.py"

CHART_PATH="${1:-charts/signal-engine}"
RELEASE_NAME="${2:-test}"

if ! command -v helm >/dev/null 2>&1; then
  echo "helm-template-validate: 'helm' not found in PATH" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "helm-template-validate: 'python3' not found in PATH" >&2
  exit 2
fi

if [[ ! -d "$CHART_PATH" ]]; then
  echo "helm-template-validate: chart directory not found: $CHART_PATH" >&2
  exit 2
fi

if [[ ! -f "$VALIDATOR" ]]; then
  echo "helm-template-validate: validator not found: $VALIDATOR" >&2
  exit 2
fi

# Render the template. If helm itself fails, stop here (that is a template
# syntax error, not a whitespace error — surface the helm output verbatim).
rendered="$(helm template "$RELEASE_NAME" "$CHART_PATH" 2>&1)" || {
  echo "helm-template-validate: helm template failed:" >&2
  echo "$rendered" >&2
  exit 1
}

# Write the rendered YAML to a temp file so the Python validator can read
# it cleanly.
tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT
printf '%s\n' "$rendered" > "$tmpfile"

python3 "$VALIDATOR" "$tmpfile" "$CHART_PATH"