#!/usr/bin/env bash
set -euo pipefail
go build -p 1 -buildvcs=false -o "$RUNNER_TEMP/firestore-codeql" .
printf '%s\n' \
  '0d7abba8b133f8c400ef711949b77019efa4af643762364d132f51c7d357a5b0  go.mod' \
  '0576793ba5b46b5057a41886968ae5f458d0e15781b7a52f66717a9b93c8d057  go.sum' \
  | sha256sum -c -
