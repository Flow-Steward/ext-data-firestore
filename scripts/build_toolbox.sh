#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
GO_IMAGE=golang:1.26.2-bookworm@sha256:47ce5636e9936b2c5cbf708925578ef386b4f8872aec74a67bd13a627d242b19
SOURCE=${TOOLBOX_SOURCE:-/private/tmp/fs-toolbox-upstream-20261101}
test "$(git -C "$SOURCE" rev-parse HEAD)" = b0010060a939455d91e4f8ba62dc3e72b1892469
tar -cf - -C "$SOURCE" go.mod go.sum -C "$ROOT" native scripts/build_inside.sh | docker run -i --rm --cpus 1 --memory 2g --label flow-steward.audit=firestore-20261101 \
  -v "$ROOT:/out" \
  -v flow-steward-db-batch-go-cache:/go/pkg/mod \
  -v flow-steward-db-batch-build-cache:/root/.cache/go-build \
  "$GO_IMAGE" sh -c '
    mkdir -p /src
    tar -xf - -C /src
    sh /src/scripts/build_inside.sh
  '
python3 "$ROOT/scripts/provenance.py"
