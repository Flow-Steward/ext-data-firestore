"""CodeQL must analyze and preserve the same reviewed module lock as native CI."""

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]


def module_hashes(script):
    return dict(
        (name, digest)
        for digest, name in re.findall(
            r"([0-9a-f]{64})  (?:native/)?(go\.(?:mod|sum))", script
        )
    )


def test_codeql_verifies_native_builder_module_lock():
    expected = module_hashes((ROOT / "scripts/build_inside.sh").read_text())
    assert expected.keys() == {"go.mod", "go.sum"}
    workflow = yaml.safe_load((ROOT / ".github/workflows/codeql.yml").read_text())
    job = workflow["jobs"]["analyze"]
    assert job["uses"] == (
        "Flow-Steward/extensions/.github/workflows/codeql-scan.yml@codeql-stable"
    )
    assert {"language": "go", "build-mode": "manual"} in job["strategy"]["matrix"][
        "include"
    ]

    for filename in ("prepare-codeql-go.sh", "build-codeql-go.sh"):
        script = (ROOT / "scripts" / filename).read_text()
        assert module_hashes(script) == expected
        assert "sha256sum -c -" in script
