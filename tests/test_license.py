"""Keep the upstream Apache license byte-for-byte canonical."""

import hashlib
from pathlib import Path


def test_canonical_apache_license_is_unmodified():
    data = (Path(__file__).resolve().parents[1] / "LICENSE").read_bytes()
    assert (
        hashlib.sha256(data).hexdigest()
        == "58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd"
    )
