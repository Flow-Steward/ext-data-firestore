from unittest.mock import patch
import pytest
import main
from commands import compile_command, validate
from validation import Failure, connection_values

CONFIG = {"project": "sample-project", "database": "(default)", "request_timeout_seconds": 15}


def envelope(name="get_document", **args):
    return {
        "contract_version": "extension_host_v2",
        "mode": "action",
        "runtime_context": {
            "group_id": None,
            "for_each_id": None,
            "step_id": "step",
            "step_execution_id": "exec",
            "account_id": "a",
            "project_id": "p",
            "test_mode": False,
            "external_effect_id": "claim",
        },
        "action": {
            "action_id": name,
            "input": {"connection_ref": "c", "document_path": "things/id", **args},
            "target": {
                "connection": {
                    "connection_id": "c",
                    "connection_type": "firestore",
                    "config": CONFIG,
                    "secrets": {"access_token": "secret"},
                }
            },
        },
    }


@pytest.mark.parametrize(
    "path", ["../a", "a", "a//b", "projects/p/databases/d/documents/a/b", "a/b?x", "a/%2F"]
)
def test_paths_closed(path):
    with pytest.raises(Failure):
        validate("get_document", {"document_path": path}, CONFIG)


@pytest.mark.parametrize(
    "name", ["create_document", "upsert_document", "update_document", "delete_document"]
)
def test_write_suppression_before_io(name):
    p = envelope(name, fields={"n": {"integerValue": "9223372036854775807"}})
    if name == "delete_document":
        p["action"]["input"].pop("fields")
    p["runtime_context"]["test_mode"] = True
    with patch("toolbox.invoke") as call:
        result = main.handle(p)
    assert result["error_code"] == "test_mode_suppressed"
    call.assert_not_called()


@pytest.mark.parametrize("key", ["account_id", "project_id"])
def test_scope_required(key):
    p = envelope()
    p["runtime_context"].pop(key)
    assert not main.handle(p)["ok"]


def test_typed_values_and_preconditions():
    fields = {
        "big": {"integerValue": "9223372036854775807"},
        "data": {"bytesValue": "AA=="},
        "ts": {"timestampValue": "2026-01-01T00:00:00Z"},
    }
    a = validate(
        "update_document",
        {"document_path": "a/b", "fields": fields, "update_time": "2026-01-01T00:00:00Z"},
        CONFIG,
    )
    cmd = compile_command("update_document", a, CONFIG)
    assert cmd["request"]["document"]["fields"] == fields
    assert cmd["request"]["currentDocument"] == {"updateTime": "2026-01-01T00:00:00Z"}
    assert compile_command("create_document", {"document_path": "a/b", "fields": fields}, CONFIG)[
        "request"
    ]["currentDocument"] == {"exists": False}


def test_no_retry_uncertain_write():
    p = envelope("delete_document")
    with patch(
        "toolbox.invoke", side_effect=Failure("timeout", "redacted", dispatched=True)
    ) as call:
        r = main.handle(p)
    assert call.call_count == 1 and r["retryable"] is False
    assert r["external_effect_status"] == "timeout_unknown"
    assert not r["definitely_no_external_effect"]


def test_connection_match_and_claim():
    p = envelope("delete_document")
    p["runtime_context"].pop("external_effect_id")
    assert main.handle(p)["error_code"] == "effect_claim_required"
    p = envelope()
    p["action"]["target"]["connection"]["connection_id"] = "other"
    assert main.handle(p)["error_code"] == "invalid_connection"


@pytest.mark.parametrize(
    "config,secrets",
    [
        ({"project": "p", "endpoint": "evil"}, {"access_token": "x"}),
        (
            {"project": "p"},
            {"service_account_json": '{"type":"service_account","token_uri":"https://evil"}'},
        ),
        ({"project": "p"}, {"access_token": "x", "service_account_json": "{}"}),
    ],
)
def test_closed_credentials(config, secrets):
    with pytest.raises(Failure):
        connection_values({"config": config, "secrets": secrets})


def test_query_bounded_and_collection_scoped():
    with pytest.raises(Failure):
        validate("query_collection", {"collection_path": "a", "limit": 101}, CONFIG)
    cmd = compile_command(
        "query_collection",
        validate("query_collection", {"collection_path": "a/b/c", "limit": 3}, CONFIG),
        CONFIG,
    )
    assert cmd["request"]["parent"].endswith("/a/b")
    assert cmd["request"]["structuredQuery"]["from"] == [{"collectionId": "c"}]
    assert cmd["request"]["structuredQuery"]["limit"] == 3


def test_read_result_and_secret_redaction():
    p = envelope()
    with patch(
        "toolbox.invoke", return_value=[{"fields": {"n": {"integerValue": "9223372036854775807"}}}]
    ):
        r = main.handle(p)
    assert (
        r["ok"]
        and r["result"]["records"][0]["fields"]["n"]["integerValue"] == "9223372036854775807"
    )
    with patch("toolbox.invoke", side_effect=RuntimeError("secret")):
        r = main.handle(p)
    assert "secret" not in str(r)


def test_empty_patch_rejected_before_dispatch():
    p = envelope("update_document", fields={})
    with patch("toolbox.invoke") as call:
        assert main.handle(p)["error_code"] == "invalid_payload"
    call.assert_not_called()


def test_oversized_payload_and_result():
    p = envelope()
    p["action"]["input"]["document_path"] = "x" * 300000
    assert main.handle(p)["error_code"] == "invalid_payload"
    p = envelope()
    with patch("toolbox.invoke", return_value=[{"fields": {"x": "x" * 500000}}]):
        assert main.handle(p)["error_code"] == "response_too_large"


def test_missing_host_execution_scope():
    p = envelope()
    p["runtime_context"].pop("step_execution_id")
    with patch("toolbox.invoke") as call:
        assert main.handle(p)["error_code"] == "invalid_payload"
    call.assert_not_called()


def test_page_token_removed_from_records():
    p = envelope("list_documents", collection_path="things", limit=100)
    p["action"]["input"].pop("document_path")
    with patch(
        "toolbox.invoke", return_value=[{"name": "x"}] * 100 + [{"next_page_token": "next"}]
    ):
        r = main.handle(p)
    assert r["ok"] and r["result"]["count"] == 100 and r["result"]["next_page_token"] == "next"
