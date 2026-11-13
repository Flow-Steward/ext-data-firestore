# Firestore workflow actions

Configure a Firestore project connection with the Google Cloud project, database and either an access token or service-account JSON in connection secrets. Grant Firestore IAM permissions for the chosen reads or writes. Select this connection in every action. All paths are relative to its database: orders/order_1042 identifies a document; orders identifies a collection. Queries are collection-scoped and may need Firestore indexes.

Action names below match the workflow builder. IDs in parentheses remain compatible with saved workflows. Examples show field values; bind values from earlier steps as needed.

## Choose and configure an action

### Read a document by path (`get_document`)

Read one Firestore document with typed field values and create/update timestamps. Use a path relative to the configured database.

```json
{
  "document_path": "orders/order_1042"
}
```

### Create a document at a new path (`create_document`)

Create a document at a stable caller-supplied path using Firestore typed fields. Fails if that document already exists.

```json
{
  "document_path": "orders/order_1042",
  "fields": {
    "status": {
      "stringValue": "approved"
    },
    "total": {
      "integerValue": "42"
    }
  }
}
```

### Create or replace all document fields (`upsert_document`)

Create a missing document or replace every field at the selected path. Omitted fields are removed; an optional update timestamp guards against concurrent changes.

```json
{
  "document_path": "orders/order_1042",
  "fields": {
    "status": {
      "stringValue": "approved"
    },
    "total": {
      "integerValue": "42"
    }
  }
}
```

### Patch fields on an existing document (`update_document`)

Update the supplied top-level typed fields while preserving omitted fields. The document must exist; an optional update timestamp guards against concurrent changes.

```json
{
  "document_path": "orders/order_1042",
  "fields": {
    "status": {
      "stringValue": "approved"
    },
    "total": {
      "integerValue": "42"
    }
  }
}
```

### Delete a document by path (`delete_document`)

Delete one document at the selected path, optionally checking existence or an update timestamp. Does not delete its subcollections.

```json
{
  "document_path": "orders/order_1042"
}
```

### List a page of collection documents (`list_documents`)

Read one page of up to 100 documents from one collection. Pass next_page_token to another call for continuation.

```json
{
  "collection_path": "orders"
}
```

### Find collection documents by typed filters (`query_collection`)

Read up to 100 documents from one collection using AND-combined typed filters and optional ordering. Firestore may require an index for the query.

```json
{
  "collection_path": "orders",
  "filters": [
    {
      "field": "status",
      "op": "EQUAL",
      "value": {
        "stringValue": "approved"
      }
    }
  ],
  "order_by": [
    {
      "field": "total",
      "direction": "DESCENDING"
    }
  ]
}
```

### List root collections or subcollections (`list_collections`)

Read a page of collection IDs at the database root or below a document. Pass next_page_token to continue the listing.

```json
{}
```

## Requirements and result handling

Field values use official Firestore Value objects: `{"status":{"stringValue":"approved"},"total":{"integerValue":"42"}}`. A plain `{"status":"approved"}` is rejected. Replacement removes omitted fields; patch preserves omitted fields and changes supplied top-level fields. Copy the exact UTC `updateTime` from a read to prevent overwriting concurrent changes. Delete accepts either `exists` or `update_time`, never both, and does not delete subcollections. List actions return `result.next_page_token`; query is bounded without automatic pagination. Results are in `result.records`.

Workflow write actions are suppressed in test mode. Read/search actions still read the configured service. If a write fails after dispatch, inspect the service before repeating it; the write may already have applied.
