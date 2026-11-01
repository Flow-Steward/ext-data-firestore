"""Record native build provenance and digests."""

import hashlib
import json
from pathlib import Path

r = Path(__file__).resolve().parents[1]
records = {}
for target in ("linux-amd64", "linux-arm64"):
    p = r / "bin" / target / "toolbox"
    records[target] = {
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "size": p.stat().st_size,
    }
(r / "toolbox-provenance.json").write_text(
    json.dumps(
        {
            "tag": "v1.3.0",
            "commit": "b0010060a939455d91e4f8ba62dc3e72b1892469",
            "adaptation": "native/main.go replaces upstream high-level Firestore tools; official apiv1 protobuf requests; Toolbox dependency lock",
            "go_image": "golang:1.26.2-bookworm@sha256:47ce5636e9936b2c5cbf708925578ef386b4f8872aec74a67bd13a627d242b19",
            "source_sha256": hashlib.sha256((r / "native/main.go").read_bytes()).hexdigest(),
            "binaries": records,
        },
        indent=2,
    )
    + "\n"
)
