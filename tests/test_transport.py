"""Exercise the real bounded subprocess boundary using a local fake native peer."""

import json
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
import toolbox
from validation import Failure


def native_peer(tmp_path, body):
    p = tmp_path / "peer"
    p.write_text("#!" + sys.executable + "\n" + body)
    p.chmod(0o755)
    return str(p)


def test_credentials_private_and_removed(tmp_path, monkeypatch):
    peer = native_peer(
        tmp_path,
        """import json,os,stat,sys
request=json.loads(sys.stdin.readline())
p=os.environ['GOOGLE_APPLICATION_CREDENTIALS']
assert stat.S_IMODE(os.stat(p).st_mode)==0o600
assert json.load(open(p))=={'type':'service_account'}
assert 'UNTRUSTED_CREDENTIAL' not in os.environ
print(json.dumps({'jsonrpc':'2.0','id':2,'result':[{'path':p}]}),flush=True)
""",
    )
    monkeypatch.setenv("UNTRUSTED_CREDENTIAL", "do-not-forward")
    with patch.object(toolbox, "_binary", return_value=peer):
        result = toolbox.invoke(
            {},
            {"service_account_json": json.dumps({"type": "service_account"})},
            {"rpc": "get", "request": {}},
            {},
            timeout_seconds=3,
        )
    assert not Path(result[0]["path"]).exists()


def test_token_only_passed_on_private_stdin(tmp_path):
    peer = native_peer(
        tmp_path,
        """import json,os,sys
request=json.loads(sys.stdin.readline())
assert request['access_token']=='sensitive'
assert 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ
print(json.dumps({'jsonrpc':'2.0','id':2,'result':[]}),flush=True)
""",
    )
    with patch.object(toolbox, "_binary", return_value=peer):
        assert (
            toolbox.invoke(
                {},
                {"access_token": "sensitive"},
                {"rpc": "get", "request": {}},
                {},
                timeout_seconds=3,
            )
            == []
        )


def test_timeout_stops_peer_and_reports_uncertainty(tmp_path):
    peer = native_peer(
        tmp_path,
        """import sys,time
sys.stdin.readline()
time.sleep(30)
""",
    )
    with patch.object(toolbox, "_binary", return_value=peer), pytest.raises(Failure) as error:
        toolbox.invoke(
            {},
            {"access_token": "sensitive"},
            {"rpc": "delete", "request": {}},
            {},
            timeout_seconds=0.1,
        )
    assert error.value.code == "timeout" and error.value.dispatched
    assert "sensitive" not in str(error.value)


def test_native_error_is_redacted(tmp_path):
    peer = native_peer(
        tmp_path,
        """import json,sys
sys.stdin.readline()
print(json.dumps({'jsonrpc':'2.0','id':2,'error':'sensitive','error_code':'provider_unavailable'}),flush=True)
""",
    )
    with patch.object(toolbox, "_binary", return_value=peer), pytest.raises(Failure) as error:
        toolbox.invoke(
            {},
            {"access_token": "sensitive"},
            {"rpc": "delete", "request": {}},
            {},
            timeout_seconds=3,
        )
    assert error.value.dispatched and "sensitive" not in str(error.value)
