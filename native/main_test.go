package main

import (
	pb "cloud.google.com/go/firestore/apiv1/firestorepb"
	"google.golang.org/protobuf/encoding/protojson"
	"strings"
	"testing"
)

func TestTypedDocumentRoundTrip(t *testing.T) {
	input := `{"document":{"name":"projects/sample-project/databases/(default)/documents/a/b","fields":{"i":{"integerValue":"9223372036854775807"},"b":{"bytesValue":"AAE="},"r":{"referenceValue":"projects/sample-project/databases/(default)/documents/a/c"},"t":{"timestampValue":"2026-01-01T00:00:00.123456789Z"}}},"currentDocument":{"exists":false}}`
	r := &pb.UpdateDocumentRequest{}
	if err := protojson.Unmarshal([]byte(input), r); err != nil {
		t.Fatal(err)
	}
	if r.Document.Fields["i"].GetIntegerValue() != 9223372036854775807 {
		t.Fatal("int64 precision lost")
	}
	if r.CurrentDocument.GetExists() {
		t.Fatal("create-only precondition lost")
	}
	out, err := protojson.Marshal(r)
	if err != nil {
		t.Fatal(err)
	}
	for _, s := range []string{`"9223372036854775807"`, `"AAE="`, `"2026-01-01T00:00:00.123456789Z"`, `"referenceValue"`} {
		if !strings.Contains(string(out), s) {
			t.Fatal("typed field lost:", s)
		}
	}
}
func TestClosedProtoRequest(t *testing.T) {
	if protojson.Unmarshal([]byte(`{"document":{"name":"a/b"},"endpoint":"evil"}`), &pb.UpdateDocumentRequest{}) == nil {
		t.Fatal("unknown fields accepted")
	}
}
