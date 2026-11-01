"""Compile a closed operation into official Firestore v1 request JSON."""

from validation import require, path, fields, integer, field, typed, timestamp

WRITES = {"create_document", "upsert_document", "update_document", "delete_document"}
FIELDS = {
    "get_document": {"document_path"},
    "create_document": {"document_path", "fields"},
    "upsert_document": {"document_path", "fields", "update_time"},
    "update_document": {"document_path", "fields", "update_time"},
    "delete_document": {"document_path", "update_time", "exists"},
    "list_documents": {"collection_path", "limit", "page_token"},
    "query_collection": {"collection_path", "limit", "filters", "order_by"},
    "list_collections": {"parent_path", "limit", "page_token"},
}


def validate(name, args, config):
    require(
        name in FIELDS
        and isinstance(args, dict)
        and set(args) <= FIELDS[name] | {"connection_ref"},
        "Unknown action or input.",
    )
    a = dict(args)
    for k in ("document_path", "collection_path"):
        if k in FIELDS[name]:
            path(a.get(k), document=k == "document_path")
    if "fields" in FIELDS[name]:
        fields(a.get("fields"), config)
        if name == "update_document":
            require(bool(a["fields"]), "Patch fields must be nonempty.")
    if "update_time" in a:
        timestamp(a["update_time"])
    if "exists" in a:
        require(type(a["exists"]) is bool and "update_time" not in a, "Invalid precondition.")
    if name == "list_collections":
        path(a.get("parent_path", ""), empty=True)
    if "limit" in FIELDS[name]:
        a["limit"] = integer(a.get("limit", 20))
    if "page_token" in a:
        require(
            isinstance(a["page_token"], str) and len(a["page_token"]) <= 4096, "Invalid page token."
        )
    if name == "query_collection":
        require(
            isinstance(a.get("filters", []), list) and len(a.get("filters", [])) <= 10,
            "Invalid filters.",
        )
        for f in a.get("filters", []):
            require(
                isinstance(f, dict)
                and set(f) == {"field", "op", "value"}
                and f["op"]
                in {
                    "EQUAL",
                    "NOT_EQUAL",
                    "LESS_THAN",
                    "LESS_THAN_OR_EQUAL",
                    "GREATER_THAN",
                    "GREATER_THAN_OR_EQUAL",
                    "ARRAY_CONTAINS",
                    "IN",
                    "NOT_IN",
                    "ARRAY_CONTAINS_ANY",
                },
                "Invalid filter.",
            )
            field(f["field"])
            typed(f["value"], config)
        require(
            isinstance(a.get("order_by", []), list) and len(a.get("order_by", [])) <= 5,
            "Invalid ordering.",
        )
        for o in a.get("order_by", []):
            require(
                isinstance(o, dict)
                and set(o) == {"field", "direction"}
                and o["direction"] in {"ASCENDING", "DESCENDING"},
                "Invalid ordering.",
            )
            field(o["field"])
    return a


def compile_command(name, a, c):
    root = f"projects/{c['project']}/databases/{c['database']}/documents"
    rpc = ""
    r = {}
    if name == "get_document":
        rpc = "get"
        r = {"name": root + "/" + a["document_path"]}
    elif name in WRITES:
        pre = {"updateTime": a["update_time"]} if "update_time" in a else None
        if name == "delete_document":
            rpc = "delete"
            r = {"name": root + "/" + a["document_path"]}
            if "exists" in a:
                pre = {"exists": a["exists"]}
        else:
            rpc = "update"
            r = {"document": {"name": root + "/" + a["document_path"], "fields": a["fields"]}}
            if name == "create_document":
                pre = {"exists": False}
            if name == "update_document":
                pre = pre or {"exists": True}
                r["updateMask"] = {"fieldPaths": list(a["fields"])}
        if pre is not None:
            r["currentDocument"] = pre
    elif name == "list_documents":
        rpc = "list"
        parts = a["collection_path"].split("/")
        r = {
            "parent": root + ("/" + "/".join(parts[:-1]) if len(parts) > 1 else ""),
            "collectionId": parts[-1],
            "pageSize": a["limit"],
            "pageToken": a.get("page_token", ""),
        }
    elif name == "list_collections":
        rpc = "collections"
        r = {
            "parent": root + ("/" + a["parent_path"] if a.get("parent_path") else ""),
            "pageSize": a["limit"],
            "pageToken": a.get("page_token", ""),
        }
    elif name == "query_collection":
        rpc = "query"
        parts = a["collection_path"].split("/")
        q = {"from": [{"collectionId": parts[-1]}], "limit": a["limit"]}
        filters = [
            {
                "fieldFilter": {
                    "field": {"fieldPath": f["field"]},
                    "op": f["op"],
                    "value": f["value"],
                }
            }
            for f in a.get("filters", [])
        ]
        if filters:
            q["where"] = (
                filters[0]
                if len(filters) == 1
                else {"compositeFilter": {"op": "AND", "filters": filters}}
            )
        if a.get("order_by"):
            q["orderBy"] = [
                {"field": {"fieldPath": o["field"]}, "direction": o["direction"]}
                for o in a["order_by"]
            ]
        r = {
            "parent": root + ("/" + "/".join(parts[:-1]) if len(parts) > 1 else ""),
            "structuredQuery": q,
        }
    return {"rpc": rpc, "request": r}


def execute(name, args, config, context, call):
    command = compile_command(name, validate(name, args, config), config)
    value = call(command, {})
    page_cursor = ""
    if isinstance(value, list) and value and set(value[-1]) == {"next_page_token"}:
        page_cursor = value.pop()["next_page_token"]
    require(
        isinstance(value, list) and len(value) <= 100,
        "Invalid bounded provider response.",
        code="invalid_provider_response",
    )
    return {
        "records": value,
        "count": len(value),
        "applied": name in WRITES,
        "next_page_token": page_cursor,
    }
