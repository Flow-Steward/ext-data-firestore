# Firestore for Flow Steward

Standalone `flowsteward.firestore` host-v2 connector. This is Google Cloud Firestore document storage, not Firebase Realtime Database. No triggers, Rules management, arbitrary RPC execution, transactions, or automatic write retries.

Supports `get_document`, `create_document`, `upsert_document`, `update_document`, `delete_document`, `list_documents`, `query_collection`, and `list_collections`. Select a matching project connection, configure Google Cloud `project`, optional `database` (default `(default)`), and `request_timeout_seconds` (1–30, default 15).

Configure exactly one connection secret: `access_token` (short-lived OAuth token) or `service_account_json` (Google service-account key JSON). Grant only the Firestore IAM permissions needed for the chosen operations, for example the appropriate read-only or read/write datastore role. Service-account JSON is written to an adapter-owned 0600 file inside an adapter-owned temporary directory, passed using a controlled environment, and removed on success or failure. No caller credential paths, custom endpoints, environment overrides, or emulator endpoints are accepted. Both Google TLS certificates and hostnames are verified. Keys must use `https://oauth2.googleapis.com/token`.

All documents use explicit stable `document_path` values such as `customers/customer-42`. Subcollections use alternating document and collection segments. `create_document` uses `exists=false`; `update_document` patches supplied top-level fields and requires an existing document; `upsert_document` replaces the whole document and may create it. An optional `update_time` precondition guards update/upsert/delete against stale versions. Delete additionally accepts `exists`. Delete does not recursively remove subcollections. Missing documents and precondition failures return a redacted provider error.

`fields` use official Firestore Value JSON, preserving types and int64 precision:

```json
{"name":{"stringValue":"Alice"},"visits":{"integerValue":"9223372036854775807"},"created":{"timestampValue":"2026-01-01T00:00:00Z"},"bytes":{"bytesValue":"AAE="}}
```

Other accepted types include null, booleans, doubles, geographic points, typed arrays/maps, and references within the selected database. Field names are simple identifiers; update patches operate on top-level fields. Inputs are capped at 256 KiB, outputs at 480 KiB, and collection queries/pages at 100 records. Reads fail closed on oversized documents. List operations return `next_page_token` for explicit continuation; they never silently fetch all pages. Query `filters` are objects with `field`, official Firestore operator `op`, and typed `value`; optional `order_by` contains `field` and `direction` (`ASCENDING`/`DESCENDING`). Firestore may require a provisioned index.

Writes require a host durable `external_effect_id`; test mode validates inputs then suppresses every write before provider I/O. Each write invocation performs one RPC. GAPIC retries and gRPC policy retries are disabled; the gRPC retry buffer is zero. Transport-level transparent retries before server processing follow gRPC semantics. Read pagination is explicitly bounded. A failed write after dispatch is conservatively `timeout_unknown`, never retryable: reconcile by stable path and read updateTime before deciding on a new host effect. The adapter does not claim exactly-once provider writes or deduplicate effects itself.

## Native build and packages

`native/main.go` is a managed source adaptation built under the pinned Google MCP Toolbox v1.3.0 (`b0010060a939455d91e4f8ba62dc3e72b1892469`) dependency lock. It replaces upstream high-level Firestore CRUD with the official Google low-level Firestore v1 GAPIC/protobuf client. Upstream high-level conversion removes type tags, Add generates random IDs, BulkWriter retries, and source initialization creates a Firebase Rules client; none of those implementations is included in the native runtime. The binary is not an unmodified Google Toolbox distribution or an MCP server. The Python adapter uses a bounded private single-request JSON protocol.

Run `scripts/build_toolbox.sh` with a local pinned Toolbox checkout in `TOOLBOX_SOURCE` (default `/private/tmp/fs-toolbox-upstream-20261101`). It snapshots source over stdin into the pinned Go container and builds static Linux AMD64 and ARM64 executables. Builds use `--cpus 1 --memory 2g`. `toolbox-provenance.json` records source and binary digests; runtime verifies its packaged executable digest. Run `python3 scripts/package_extension.py --help` to produce target-specific installer ZIPs. Archives include exactly one matching native ELF binary and architecture metadata.

## Validation limits

Offline host contract tests mock the transport. Native tests validate official protobuf typed-value round trips and closed request decoding. No Google Cloud credentials were available during development: live authentication, IAM authorization, queries, and cloud CRUD were not exercised. These are contract/native-build checks, not evidence of live Google Cloud behavior. No emulator is accepted in the production connection contract.

Primary references: [Firestore documents API](https://docs.cloud.google.com/firestore/docs/reference/rest/v1/projects.databases.documents), [Firestore Value types](https://docs.cloud.google.com/firestore/docs/reference/rest/v1/Value), [official Go client](https://pkg.go.dev/cloud.google.com/go/firestore/apiv1), [Google MCP Toolbox](https://github.com/googleapis/mcp-toolbox/tree/v1.3.0).
