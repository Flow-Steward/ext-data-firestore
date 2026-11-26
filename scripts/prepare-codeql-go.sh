#!/usr/bin/env bash
set -euo pipefail
upstream_commit=$(python3 - <<'PYTHON'
import json
import re
from pathlib import Path
commit = json.loads(Path("scripts/build-config.json").read_text())["upstream_commit"]
if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
    raise SystemExit("The upstream commit must be a full 40-character SHA.")
print(commit)
PYTHON
)
for module_file in go.mod go.sum; do
  curl --fail --show-error --silent --location \
    --proto '=https' --proto-redir '=https' \
    --connect-timeout 10 --max-time 60 \
    --retry 3 --retry-max-time 180 --max-filesize 2097152 \
    "https://raw.githubusercontent.com/googleapis/mcp-toolbox/$upstream_commit/$module_file" \
    --output "native/$module_file"
done
git apply --directory=native scripts/patches/0000-security-baseline.patch
printf '%s\n' \
  '0d7abba8b133f8c400ef711949b77019efa4af643762364d132f51c7d357a5b0  native/go.mod' \
  '0576793ba5b46b5057a41886968ae5f458d0e15781b7a52f66717a9b93c8d057  native/go.sum' \
  | sha256sum -c -
