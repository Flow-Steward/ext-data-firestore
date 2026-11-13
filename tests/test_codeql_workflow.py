"""CodeQL must analyze and preserve the same reviewed module lock as native CI."""
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]


def module_hashes(script):
    return dict((name, digest) for digest, name in re.findall(
        r"([0-9a-f]{64})  (?:native/)?(go\.(?:mod|sum))", script
    ))


def test_codeql_verifies_native_builder_module_lock():
    expected = module_hashes((ROOT / "scripts/build_inside.sh").read_text())
    assert expected.keys() == {"go.mod", "go.sum"}
    workflow = yaml.safe_load((ROOT / ".github/workflows/codeql.yml").read_text())
    steps = workflow["jobs"]["analyze"]["steps"]
    prepare = next(step for step in steps if step["name"] == "Prepare the locked Firestore Go module")
    build = next(step for step in steps if step["name"] == "Build the Firestore adapter for CodeQL")
    assert module_hashes(prepare["run"]) == expected
    assert module_hashes(build["run"]) == expected
    assert build["env"]["GOFLAGS"] == "-mod=readonly"
    assert build["env"]["GOTOOLCHAIN"] == "local"
