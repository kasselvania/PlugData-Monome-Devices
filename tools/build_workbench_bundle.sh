#!/bin/sh

set -eu

usage() {
    cat <<'EOF'
Usage: ./tools/build_workbench_bundle.sh [--ref GIT_REF] [--output DIRECTORY]

Build a checksum-addressed ZIP of the complete committed development
workbench. The default ref is HEAD and the default output directory is dist/.
EOF
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
bundle_ref=HEAD
output_dir="$repo_dir/dist"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --ref)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            bundle_ref=$2
            shift 2
            ;;
        --output)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            output_dir=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

object_id=$(git -C "$repo_dir" rev-parse --verify "$bundle_ref^{object}")
short_id=$(printf '%s' "$object_id" | cut -c1-12)
bundle_name="plugdata-monome-workbench-$short_id"
archive_name="$bundle_name.zip"

mkdir -p "$output_dir"
output_dir=$(CDPATH= cd -- "$output_dir" && pwd)
archive_path="$output_dir/$archive_name"

git -C "$repo_dir" archive \
    --format=zip \
    --prefix="$bundle_name/" \
    --output="$archive_path" \
    "$bundle_ref"

unzip -tq "$archive_path" >/dev/null
(
    cd "$output_dir"
    shasum -a 256 "$archive_name" > "$archive_name.sha256"
)

printf 'WORKBENCH BUNDLE PASSED\n'
printf '%s\n' "$archive_path"
printf '%s\n' "$archive_path.sha256"
