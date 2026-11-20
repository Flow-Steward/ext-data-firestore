#!/bin/sh
# Reviewed v1.17.0 source, reviewed module graph; official Go1.27.4 installed over bootstrap, and connector-only registrations.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BOOTSTRAP_IMAGE=golang:1.27.3-bookworm@sha256:dc0963f32053e4bc451d24d87e3892d42d01021b61f093e98eb95c0352bb84b0
TOOLBOX_COMMIT=45ed205cc8682ed066c82e0b65bcd0e8fc3becce
SOURCE=${TOOLBOX_SOURCE:-${FS_TOOLBOX_SOURCE_DIR:-}}
TEMP_SOURCE=
BUILD_OUTPUT=
cleanup() {
 if test -n "$BUILD_OUTPUT"; then rm -rf -- "$BUILD_OUTPUT"; fi
 if test -n "$TEMP_SOURCE"; then rm -rf -- "$TEMP_SOURCE"; fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
if test -z "$SOURCE"; then
 TEMP_SOURCE=$(mktemp -d "${TMPDIR:-/tmp}/fs-toolbox-source.XXXXXX")
 git clone --quiet --depth 1 --branch v1.17.0 https://github.com/googleapis/mcp-toolbox.git "$TEMP_SOURCE/upstream"
 SOURCE=$TEMP_SOURCE/upstream
fi
SOURCE=$(CDPATH= cd -- "$SOURCE" && pwd)
test "$(git -C "$SOURCE" rev-parse HEAD)" = "$TOOLBOX_COMMIT" || { echo "Unreviewed Toolbox source commit" >&2; exit 1; }
if test -n "$(git -C "$SOURCE" status --porcelain --untracked-files=all --ignored)"; then
 echo "Toolbox source must be clean, including untracked and ignored files" >&2
 exit 1
fi
BUILD_OUTPUT=$(mktemp -d "${TMPDIR:-/tmp}/fs-toolbox-firestore.XXXXXX")
mkdir -p "$BUILD_OUTPUT/bin/linux-amd64" "$BUILD_OUTPUT/bin/linux-arm64" "$BUILD_OUTPUT/scripts"
docker run --rm --name "fs-toolbox-firestore-$$" --label flow-steward.audit=dependency-refresh-20261113 --cpus 2 --memory 4g \
 -v "$SOURCE:/upstream:ro" \
 -v "$ROOT/scripts:/input/scripts:ro" \
 -v "$ROOT/native:/input/native:ro" \
 -v "$BUILD_OUTPUT:/out" \
 "$BOOTSTRAP_IMAGE" sh /input/scripts/build_inside.sh

# The builder can return only these generated artifacts. Host scripts and the
# reviewed license notices remain in the checkout and are never build outputs.
for directory in bin bin/linux-amd64 bin/linux-arm64 scripts; do
 if test -L "$BUILD_OUTPUT/$directory" || test -L "$ROOT/$directory"; then
  echo "Native build artifact directories must not be symlinks: $directory" >&2
  exit 1
 fi
done
for artifact in bin/linux-amd64/toolbox bin/linux-arm64/toolbox scripts/go-toolchain-selected.json; do
 if test ! -f "$BUILD_OUTPUT/$artifact" || test -L "$BUILD_OUTPUT/$artifact"; then
  echo "Missing or invalid native build artifact: $artifact" >&2
  exit 1
 fi
done
for artifact in bin/linux-amd64/toolbox bin/linux-arm64/toolbox scripts/go-toolchain-selected.json toolbox-provenance.json SHA256SUMS; do
 if test -L "$ROOT/$artifact" || { test -e "$ROOT/$artifact" && test ! -f "$ROOT/$artifact"; }; then
  echo "Native build artifact destination must be a regular file: $artifact" >&2
  exit 1
 fi
done
for target in linux-amd64 linux-arm64; do
 mkdir -p "$ROOT/bin/$target"
 install -m 0755 "$BUILD_OUTPUT/bin/$target/toolbox" "$ROOT/bin/$target/toolbox"
done
install -m 0644 "$BUILD_OUTPUT/scripts/go-toolchain-selected.json" "$ROOT/scripts/go-toolchain-selected.json"
python3 "$ROOT/scripts/provenance.py"
python3 "$ROOT/scripts/native_build_info.py"

# Native suite: go test -p 1 ./managed-firestore
# CGO_ENABLED=0; -trimpath -buildvcs=false; linux-amd64 linux-arm64
