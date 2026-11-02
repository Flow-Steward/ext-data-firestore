"""Closed Firestore connection and bounded typed document validation."""

import base64
import datetime
import json
import re


class Failure(Exception):
    def __init__(self, code, message, *, dispatched=False):
        super().__init__(message)
        self.code, self.dispatched = code, dispatched


def require(condition, message, *, code="invalid_payload"):
    if not condition:
        raise Failure(code, message)


def bounded_json(value, limit=256 * 1024):
    try:
        require(
            len(json.dumps(value, allow_nan=False).encode()) <= limit, "JSON exceeds byte limit."
        )
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise Failure("invalid_payload", "Bounded JSON required.") from exc


def text(value, maximum=1500):
    require(
        isinstance(value, str) and 0 < len(value.encode()) <= maximum and "\x00" not in value,
        "Invalid text.",
    )
    return value


def integer(value, low=1, high=100):
    require(type(value) is int and low <= value <= high, "Invalid bounded integer.")
    return value


def path(value, *, document=True, empty=False):
    if empty and value == "":
        return value
    text(value, 6000)
    parts = value.split("/")
    require(
        len(parts) <= 40 and len(parts) % 2 == (0 if document else 1),
        "Invalid document or collection path.",
    )
    require(
        parts[0] != "projects"
        and all(
            re.fullmatch(r"[A-Za-z0-9_\- .@$+(),:]{1,256}", p)
            and p not in {".", ".."}
            and not re.fullmatch(r"__.*__", p)
            for p in parts
        ),
        "Invalid resource path.",
    )
    return value


def timestamp(value):
    text(value, 40)
    require(
        bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", value)),
        "Use UTC RFC3339 timestamp.",
    )
    datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def field(value):
    text(value)
    require(
        bool(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,255}(?:\.[A-Za-z_][A-Za-z0-9_]{0,255})*", value)
        )
        and all(not re.fullmatch(r"__.*__", p) for p in value.split(".")),
        "Invalid field path.",
    )
    return value


def typed(value, config, depth=0):
    require(
        depth <= 12 and isinstance(value, dict) and len(value) == 1,
        "Use official Firestore Value objects.",
    )
    kind, v = next(iter(value.items()))
    if kind == "nullValue":
        require(v is None or v == "NULL_VALUE", "Invalid null.")
    elif kind == "booleanValue":
        require(type(v) is bool, "Invalid boolean.")
    elif kind == "integerValue":
        require(
            isinstance(v, str)
            and bool(re.fullmatch(r"-?(?:0|[1-9][0-9]*)", v))
            and -(2**63) <= int(v) < 2**63,
            "int64 requires decimal text.",
        )
    elif kind == "doubleValue":
        require(type(v) in (int, float) or v in ("NaN", "Infinity", "-Infinity"), "Invalid double.")
    elif kind == "stringValue":
        require(isinstance(v, str), "Invalid string.")
    elif kind == "timestampValue":
        timestamp(v)
    elif kind == "bytesValue":
        require(isinstance(v, str), "Invalid bytes.")
        base64.b64decode(v, validate=True)
    elif kind == "referenceValue":
        prefix = f"projects/{config['project']}/databases/{config['database']}/documents/"
        require(
            isinstance(v, str) and v.startswith(prefix),
            "References must use the selected database.",
        )
        path(v[len(prefix) :])
    elif kind == "geoPointValue":
        require(
            isinstance(v, dict)
            and set(v) == {"latitude", "longitude"}
            and all(type(n) in (int, float) for n in v.values())
            and -90 <= v["latitude"] <= 90
            and -180 <= v["longitude"] <= 180,
            "Invalid geographic point.",
        )
    elif kind == "arrayValue":
        require(
            isinstance(v, dict)
            and set(v) <= {"values"}
            and isinstance(v.get("values", []), list)
            and len(v.get("values", [])) <= 1000,
            "Invalid array.",
        )
        for child in v.get("values", []):
            require(
                not isinstance(child, dict) or "arrayValue" not in child, "Nested arrays forbidden."
            )
            typed(child, config, depth + 1)
    elif kind == "mapValue":
        require(isinstance(v, dict) and set(v) <= {"fields"}, "Invalid map.")
        fields(v.get("fields", {}), config, depth + 1)
    else:
        require(False, "Unsupported Firestore Value type.")


def fields(value, config, depth=0):
    require(isinstance(value, dict) and len(value) <= 500, "Invalid typed fields.")
    for key, child in value.items():
        field(key)
        require("." not in key, "Field names must be simple identifiers.")
        typed(child, config, depth)
    return value


def connection_values(connection):
    try:
        c, s = connection.get("config") or {}, connection.get("secrets") or {}
        require(
            isinstance(c, dict)
            and isinstance(s, dict)
            and set(c) <= {"project", "database", "request_timeout_seconds"}
            and set(s) in ({"access_token"}, {"service_account_json"}),
            "Invalid connection fields.",
        )
        project = text(c.get("project"), 63)
        require(bool(re.fullmatch(r"[a-z][a-z0-9-]{0,61}[a-z0-9]", project)), "Invalid project.")
        database = c.get("database", "(default)")
        require(
            database == "(default)"
            or bool(re.fullmatch(r"[a-z][a-z0-9-]{2,61}[a-z0-9]", database)),
            "Invalid database.",
        )
        if "access_token" in s:
            token = text(s["access_token"], 8192)
            require(not any(ch.isspace() for ch in token), "Invalid token.")
        else:
            raw = text(s["service_account_json"], 16384)
            key = json.loads(raw)
            require(
                isinstance(key, dict)
                and key.get("type") == "service_account"
                and key.get("token_uri") == "https://oauth2.googleapis.com/token"
                and isinstance(key.get("client_email"), str)
                and key["client_email"].endswith(".iam.gserviceaccount.com")
                and isinstance(key.get("private_key"), str)
                and key["private_key"].startswith("-----BEGIN " + "PRIVATE KEY-----"),
                "Invalid service account.",
            )
        return {
            "project": project,
            "database": database,
            "request_timeout_seconds": integer(c.get("request_timeout_seconds", 15), 1, 30),
        }, s
    except (Failure, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise Failure(
            "invalid_connection", "Invalid Firestore configuration or credentials."
        ) from exc
