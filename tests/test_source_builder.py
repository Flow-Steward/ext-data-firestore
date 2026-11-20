"""The CI builder accepts only a clean checkout of its pinned upstream source."""

import os
from pathlib import Path
import re
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _builder_fixture(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    script = (ROOT / "scripts/build_toolbox.sh").read_text()
    script = re.sub(r"TOOLBOX_COMMIT=[0-9a-f]{40}", "TOOLBOX_COMMIT=" + commit, script)
    builder = tmp_path / "publisher" / "scripts" / "build_toolbox.sh"
    builder.parent.mkdir(parents=True)
    builder.write_text(script)
    return source, builder


@pytest.mark.parametrize("extra", ["untracked", "ignored"])
@pytest.mark.parametrize("override", ["TOOLBOX_SOURCE", "FS_TOOLBOX_SOURCE_DIR"])
def test_builder_rejects_unreviewed_upstream_source(tmp_path, extra, override):
    source, builder = _builder_fixture(tmp_path)
    if extra == "ignored":
        (source / ".git/info/exclude").write_text("unreviewed.go\n")
    (source / "unreviewed.go").write_text("package main")
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\necho 'docker must not run' >&2\nexit 86\n")
    docker.chmod(0o755)
    result = subprocess.run(
        ["sh", str(builder)],
        env={
            **os.environ,
            override: str(source),
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        },
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "docker must not run" not in result.stderr
    assert "clean" in result.stderr.lower(), result.stderr


def test_native_builder_mounts_only_read_only_inputs_and_private_outputs(tmp_path):
    source, builder = _builder_fixture(tmp_path)
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\nexit 86\n")
    docker.chmod(0o755)
    result = subprocess.run(
        ["sh", str(builder)],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "TOOLBOX_SOURCE": str(source),
            "TMPDIR": str(tmp_path),
        },
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 86, result.stderr
    arguments = result.stdout.splitlines()
    volumes = [arguments[index + 1] for index, part in enumerate(arguments) if part == "-v"]
    root = builder.parents[1]
    assert f"{source}:/upstream:ro" in volumes
    assert f"{root / 'scripts'}:/input/scripts:ro" in volumes
    assert f"{root / 'native'}:/input/native:ro" in volumes
    writable = [
        Path(volume.removesuffix(":/out")) for volume in volumes if volume.endswith(":/out")
    ]
    assert len(writable) == 1 and writable[0].parent == tmp_path
    assert writable[0] != root and not writable[0].exists()
    assert len(volumes) == 4


def test_native_builder_promotes_generated_files_before_running_host_helpers(tmp_path):
    source, builder = _builder_fixture(tmp_path)
    root = builder.parents[1]
    docker = tmp_path / "docker"
    docker.write_text(
        """#!/bin/sh
set -eu
for argument do
  case "$argument" in
    *:/out) output=${argument%:/out} ;;
  esac
done
printf '%s\n' "amd64 fixture" > "$output/bin/linux-amd64/toolbox"
printf '%s\n' "arm64 fixture" > "$output/bin/linux-arm64/toolbox"
printf '%s\n' '{}' > "$output/scripts/go-toolchain-selected.json"
"""
    )
    docker.chmod(0o755)
    (root / "scripts/provenance.py").write_text(
        """from pathlib import Path
root = Path(__file__).resolve().parents[1]
assert (root / "bin/linux-amd64/toolbox").read_text().strip() == "amd64 fixture"
assert (root / "bin/linux-arm64/toolbox").read_text().strip() == "arm64 fixture"
assert (root / "scripts/go-toolchain-selected.json").read_text().strip() == "{}"
(root / "toolbox-provenance.json").write_text("{}")
"""
    )
    (root / "scripts/native_build_info.py").write_text(
        """from pathlib import Path
root = Path(__file__).resolve().parents[1]
assert (root / "toolbox-provenance.json").read_text() == "{}"
(root / "SHA256SUMS").write_text("verified fixture")
"""
    )
    result = subprocess.run(
        ["sh", str(builder)],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "TOOLBOX_SOURCE": str(source),
            "TMPDIR": str(tmp_path),
        },
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert (root / "SHA256SUMS").read_text() == "verified fixture"
    assert (root / "bin/linux-amd64/toolbox").stat().st_mode & 0o777 == 0o755
    assert not list(tmp_path.glob("fs-toolbox-firestore.*"))


def test_generated_native_payload_is_untracked_and_ignored():
    generated = [
        "bin/linux-amd64/toolbox",
        "bin/linux-arm64/toolbox",
        "toolbox-provenance.json",
        "SHA256SUMS",
        "scripts/go-toolchain-selected.json",
    ]
    tracked = subprocess.check_output(["git", "ls-files", "--", *generated], cwd=ROOT, text=True)
    assert tracked == "", (
        f"Generated native build outputs must not modify tracked source: {tracked}"
    )
    ignored = subprocess.check_output(
        ["git", "check-ignore", "--no-index", "--", *generated], cwd=ROOT, text=True
    )
    assert set(ignored.splitlines()) == set(generated)
