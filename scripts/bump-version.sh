#!/usr/bin/env bash
# bump-version.sh - Semantic version bump helper for signal-engine
# Usage: bump-version.sh <bump_type> [base_version]
#   bump_type: patch | minor | major | none | set
#   base_version: optional X.Y.Z (defaults: latest git tag v*, then pyproject.toml)
# Flags:
#   --dry-run: resolve and print new version WITHOUT rewriting files
#
# Rewrites (idempotent, macOS BSD sed safe):
#   - pyproject.toml: version = "X.Y.Z" in [project] table
#   - charts/signal-engine/Chart.yaml: version: X.Y.Z and appVersion: "X.Y.Z"
#
# Prints NEW version on stdout (last line). Exits non-zero on invalid input.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DRY_RUN=false
BUMP_TYPE=""
BASE_VERSION=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            if [[ -z "$BUMP_TYPE" ]]; then
                BUMP_TYPE="$1"
            elif [[ -z "$BASE_VERSION" ]]; then
                BASE_VERSION="$1"
            else
                echo "Error: Unexpected argument: $1" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate bump type
if [[ -z "$BUMP_TYPE" ]]; then
    echo "Error: bump_type required (patch|minor|major|none|set)" >&2
    echo "Usage: bump-version.sh [--dry-run] <bump_type> [base_version]" >&2
    exit 1
fi

if [[ ! "$BUMP_TYPE" =~ ^(patch|minor|major|none|set)$ ]]; then
    echo "Error: Invalid bump_type '$BUMP_TYPE'. Must be one of: patch, minor, major, none, set" >&2
    exit 1
fi

# Validate base_version if provided
SEMVER_REGEX='^[0-9]+\.[0-9]+\.[0-9]+$'
if [[ -n "$BASE_VERSION" ]] && [[ ! "$BASE_VERSION" =~ $SEMVER_REGEX ]]; then
    echo "Error: Invalid version '$BASE_VERSION'. Must match ^[0-9]+\\.[0-9]+\\.[0-9]+$" >&2
    exit 1
fi

# Resolve base version
resolve_base_version() {
    local base=""
    
    # 1. Try latest git tag matching v*
    if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
        base=$(git -C "$REPO_ROOT" tag --list 'v*' --sort=-v:refname 2>/dev/null | \
               grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1 | sed 's/^v//' || true)
    fi
    
    # 2. Fall back to pyproject.toml
    if [[ -z "$base" ]] && [[ -f "$REPO_ROOT/pyproject.toml" ]]; then
        base=$(grep -E '^version[[:space:]]*=' "$REPO_ROOT/pyproject.toml" | head -1 | \
               sed -E 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/' || true)
    fi
    
    if [[ -z "$base" ]]; then
        echo "Error: Could not resolve base version (no git tags v* and no version in pyproject.toml)" >&2
        exit 1
    fi
    
    if [[ ! "$base" =~ $SEMVER_REGEX ]]; then
        echo "Error: Resolved base version '$base' is not valid semver" >&2
        exit 1
    fi
    
    echo "$base"
}

# Compute new version from base and bump type
compute_new_version() {
    local base="$1"
    local bump="$2"
    local target="$3"  # for 'set' mode
    
    if [[ "$bump" == "set" ]]; then
        if [[ -z "$target" ]]; then
            echo "Error: 'set' mode requires a target version" >&2
            exit 1
        fi
        if [[ ! "$target" =~ $SEMVER_REGEX ]]; then
            echo "Error: Target version '$target' is not valid semver" >&2
            exit 1
        fi
        echo "$target"
        return
    fi
    
    local major minor patch
    IFS='.' read -r major minor patch <<< "$base"
    
    case "$bump" in
        patch)
            echo "${major}.${minor}.$((patch + 1))"
            ;;
        minor)
            echo "${major}.$((minor + 1)).0"
            ;;
        major)
            echo "$((major + 1)).0.0"
            ;;
        none)
            echo "$base"
            ;;
        *)
            echo "Error: Unknown bump type '$bump'" >&2
            exit 1
            ;;
    esac
}

# Update file using temp file + mv (macOS safe)
update_file() {
    local file="$1"
    local pattern="$2"
    local replacement="$3"
    
    local tmpfile
    tmpfile=$(mktemp)
    
    if ! sed -E "$pattern" "$file" > "$tmpfile"; then
        rm -f "$tmpfile"
        echo "Error: Failed to process $file" >&2
        exit 1
    fi
    
    if ! mv "$tmpfile" "$file"; then
        rm -f "$tmpfile"
        echo "Error: Failed to write $file" >&2
        exit 1
    fi
}

# Rewrite pyproject.toml version
update_pyproject() {
    local new_version="$1"
    local file="$REPO_ROOT/pyproject.toml"
    
    if [[ ! -f "$file" ]]; then
        echo "Error: $file not found" >&2
        exit 1
    fi
    
    # Match first ^version = "..." line in [project] table
    # Pattern: version = "X.Y.Z" -> version = "NEW"
    local pattern='s/^(version[[:space:]]*=[[:space:]]*)"[0-9]+\.[0-9]+\.[0-9]+"/\1"'"$new_version"'"/'
    update_file "$file" "$pattern" "$new_version"
}

# Rewrite Chart.yaml version and appVersion
update_chart() {
    local new_version="$1"
    local file="$REPO_ROOT/charts/signal-engine/Chart.yaml"
    
    if [[ ! -f "$file" ]]; then
        echo "Error: $file not found" >&2
        exit 1
    fi
    
    local tmpfile
    tmpfile=$(mktemp)
    
    # Update both version: and appVersion: in one pass
    if ! sed -E \
        -e 's/^(version:[[:space:]]*)[0-9]+\.[0-9]+\.[0-9]+/\1'"$new_version"'/' \
        -e 's/^(appVersion:[[:space:]]*)"[^"]*"/\1"'"$new_version"'"/' \
        "$file" > "$tmpfile"; then
        rm -f "$tmpfile"
        echo "Error: Failed to process $file" >&2
        exit 1
    fi
    
    if ! mv "$tmpfile" "$file"; then
        rm -f "$tmpfile"
        echo "Error: Failed to write $file" >&2
        exit 1
    fi
}

# Main logic
main() {
    # Resolve base if not provided
    if [[ -z "$BASE_VERSION" ]]; then
        BASE_VERSION=$(resolve_base_version)
    fi
    
    # For 'set' mode without a second arg, error
    if [[ "$BUMP_TYPE" == "set" ]] && [[ -z "$BASE_VERSION" ]]; then
        echo "Error: 'set' mode requires a target version as the second argument" >&2
        exit 1
    fi
    
    # Compute new version
    local NEW_VERSION
    if [[ "$BUMP_TYPE" == "set" ]]; then
        # In set mode, the second argument is the exact target version
        NEW_VERSION=$(compute_new_version "" "set" "$BASE_VERSION")
    else
        NEW_VERSION=$(compute_new_version "$BASE_VERSION" "$BUMP_TYPE" "")
    fi
    
    # Dry run: just print and exit
    if [[ "$DRY_RUN" == true ]]; then
        echo "$NEW_VERSION"
        exit 0
    fi
    
    # Apply rewrites
    update_pyproject "$NEW_VERSION"
    update_chart "$NEW_VERSION"
    
    # Print new version (last line for capture)
    echo "$NEW_VERSION"
}

main