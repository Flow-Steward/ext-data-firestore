import json
from pathlib import Path
from commands import FIELDS, WRITES

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text())


def test_contract_parity_and_no_triggers():
    manifest = load("extension.yaml")
    assert (
        manifest["extension_id"]
        == load("extension-descriptor.yaml")["extension_id"]
        == "flowsteward.firestore"
    )
    assert manifest["features"] == ["tool", "action"]
    assert {e["operation_id"] for e in manifest["external_effects"]} == WRITES
    operations = load("contracts/operation_manifest.yaml")["operations"]
    actions = load("ui/actions/actions.yaml")["actions"]
    forms = load("contracts/step_ui_manifest.yaml")["forms"]
    assert {o["operation_id"] for o in operations} == set(FIELDS)
    assert {a["action_id"] for a in actions} == set(FIELDS)
    assert {f["operation_id"] for f in forms} == set(FIELDS)
    for operation in operations:
        name = operation["operation_id"]
        assert {i["name"] for i in operation["inputs"]} == FIELDS[name] | {"connection_ref"}
        assert operation["connection_type_ids"] == ["firestore"]
    connection = load("contracts/connection_types.yaml")["connection_types"][0]
    assert connection["connection_type_id"] == "firestore"
    assert connection["capabilities"]["workflow_trigger"] is False
    assert connection["config_schema"]["additionalProperties"] is False
    assert set(connection["secret_schema"]["properties"]) == {
        "access_token",
        "service_account_json",
    }


def test_action_parameter_types_match_operation_schemas():
    actions = {a["action_id"]: a for a in load("ui/actions/actions.yaml")["actions"]}
    for operation in load("contracts/operation_manifest.yaml")["operations"]:
        parameters = {p["name"]: p for p in actions[operation["operation_id"]]["parameters"]}
        for item in operation["inputs"]:
            if "schema" in item:
                assert parameters[item["name"]]["type"] == item["schema"]["type"]
