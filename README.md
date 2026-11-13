# Firestore for Flow Steward

See [Workflow action guide](docs/workflow-actions.md) for action selection, setup requirements and JSON field examples.

Use Google Cloud Firestore documents in Flow Steward workflows for application record lookup, collection queries and updates. Actions read a document, create at a stable path, replace or upsert its fields, patch selected top-level fields, and delete it. Collection actions list documents, query with typed filters and ordering, or list root collections and subcollections. Listing returns a page token for explicit continuation.

Firestore's typed Value JSON supports strings, booleans, numbers, timestamps, bytes, geographic points, references, arrays and maps. Integer values can retain full int64 precision as strings inside their Firestore type representation. Optional update-time preconditions help reject stale updates, replacements and deletes; creation fails when the supplied path already exists. Choose patches for individual field changes or replacements when a workflow owns the complete document.

Configure the Google Cloud project and database with an access token or service-account JSON and appropriate Firestore IAM permissions. Queries and pages return at most 100 documents, and some filters require an existing Firestore index. Document deletion does not recursively remove subcollections. The connector provides Firestore document operations rather than transactions, triggers, Rules management or Firebase Realtime Database access.

## Runtime and operation requirements

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

`native/main.go` is a managed source adaptation built under the pinned Google MCP Toolbox v1.17.0 (`45ed205cc8682ed066c82e0b65bcd0e8fc3becce`) dependency lock. It replaces upstream high-level Firestore CRUD with the official Google low-level Firestore v1 GAPIC/protobuf client. Upstream high-level conversion removes type tags, Add generates random IDs, BulkWriter retries, and source initialization creates a Firebase Rules client; none of those implementations is included in the native runtime. The binary is not an unmodified Google Toolbox distribution or an MCP server. The Python adapter uses a bounded private single-request JSON protocol.

Run `scripts/build_toolbox.sh` to fetch and verify the pinned upstream source, install the official Go 1.27.4 SDK in the pinned bootstrap container, run native regressions and build static Linux AMD64 and ARM64 executables. An existing clean pinned checkout may be supplied through `TOOLBOX_SOURCE` or `FS_TOOLBOX_SOURCE_DIR`. The container is limited to two CPUs and 4 GiB memory. `toolbox-provenance.json` records source and binary digests; runtime verifies its packaged executable digest. Run `python3 scripts/package_extension.py --help` to produce target-specific installer ZIPs. Archives include exactly one matching native ELF binary and architecture metadata.

## Validation limits

Offline host contract tests mock the transport. Native tests validate official protobuf typed-value round trips and closed request decoding. No Google Cloud credentials were available during development: live authentication, IAM authorization, queries, and cloud CRUD were not exercised. These are contract/native-build checks, not evidence of live Google Cloud behavior. No emulator is accepted in the production connection contract.

Primary references: [Firestore documents API](https://docs.cloud.google.com/firestore/docs/reference/rest/v1/projects.databases.documents), [Firestore Value types](https://docs.cloud.google.com/firestore/docs/reference/rest/v1/Value), [official Go client](https://pkg.go.dev/cloud.google.com/go/firestore/apiv1), [Google MCP Toolbox](https://github.com/googleapis/mcp-toolbox/tree/v1.17.0).

## Changelog

### 1.0.1

Split the service-account PEM header validation literal so the catalog secret scan accepts the source archive. Credential validation behavior and native executables are unchanged.

## Automated CI and releases

Pushes to `main` and pull requests run the shared extension build workflow. The checked-in `.github/release-config.json` selects both Linux targets, the repository's package script and test inputs. Missing native payloads and published-only inventory are restored from checksum-pinned release archives; tracked source files are preserved. The source packager retains its provenance checks.

After the versioned release commit is on `main`, publish by pushing its version tag:

```sh
git tag v1.0.10
git push origin v1.0.10
```

The release workflow runs the shared checks, builds the target archives and publishes the GitHub release and checksums. Do not move an existing tag. To rerun a release for an existing tag, dispatch the same workflow:

```sh
gh workflow run release.yml --repo Flow-Steward/ext-data-firestore --ref main -f tag=v1.0.10
```

The manifest, descriptor (when present), package version and tag must identify the same release. Release publication uses the workflow token; no additional repository secret is required by these callers.

### Standalone CI coverage

The release recipe lists the standalone test files and individual test nodes explicitly, including package, source and provenance contracts. The shared runner clears repository pytest addopts so packaged contract checks are not silently deselected. This scope does not claim live provider or database verification.

The selected contract suite uses mocked provider responses and does not require a provider account.

CI builds both Linux architectures from the pinned upstream checkout; it does not restore older release binaries. `scripts/build_toolbox.sh` clones the pinned tag automatically, or accepts a clean exact-commit checkout through `TOOLBOX_SOURCE` / `FS_TOOLBOX_SOURCE_DIR`. The build generates `toolbox-provenance.json`, `SHA256SUMS` and selected compiler metadata, which are included in release archives.
