package main

import (
	"context"
	"encoding/json"
	"net"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	firestore "cloud.google.com/go/firestore/apiv1"
	pb "cloud.google.com/go/firestore/apiv1/firestorepb"
	"google.golang.org/api/option"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/emptypb"
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

// These tests use a real GAPIC client and gRPC transport. Service-config retries
// make removal of either the gRPC or per-request GAPIC retry guard observable.
type wireFirestore struct {
	pb.UnimplementedFirestoreServer
	calls       atomic.Int32
	unavailable bool
	document    *pb.Document
}

func (s *wireFirestore) called() error {
	s.calls.Add(1)
	if s.unavailable {
		return status.Error(codes.Unavailable, "temporary provider failure")
	}
	return nil
}
func (s *wireFirestore) GetDocument(context.Context, *pb.GetDocumentRequest) (*pb.Document, error) {
	if err := s.called(); err != nil {
		return nil, err
	}
	return s.document, nil
}
func (s *wireFirestore) UpdateDocument(context.Context, *pb.UpdateDocumentRequest) (*pb.Document, error) {
	if err := s.called(); err != nil {
		return nil, err
	}
	return s.document, nil
}
func (s *wireFirestore) DeleteDocument(context.Context, *pb.DeleteDocumentRequest) (*emptypb.Empty, error) {
	if err := s.called(); err != nil {
		return nil, err
	}
	return &emptypb.Empty{}, nil
}
func (s *wireFirestore) ListDocuments(context.Context, *pb.ListDocumentsRequest) (*pb.ListDocumentsResponse, error) {
	if err := s.called(); err != nil {
		return nil, err
	}
	return &pb.ListDocumentsResponse{Documents: []*pb.Document{s.document}}, nil
}
func (s *wireFirestore) ListCollectionIds(context.Context, *pb.ListCollectionIdsRequest) (*pb.ListCollectionIdsResponse, error) {
	if err := s.called(); err != nil {
		return nil, err
	}
	return &pb.ListCollectionIdsResponse{CollectionIds: []string{s.document.Fields["value"].GetStringValue()}}, nil
}
func (s *wireFirestore) RunQuery(_ *pb.RunQueryRequest, stream pb.Firestore_RunQueryServer) error {
	if err := s.called(); err != nil {
		return err
	}
	return stream.Send(&pb.RunQueryResponse{Document: s.document})
}

func wireClient(t *testing.T, service *wireFirestore) *firestore.Client {
	t.Helper()
	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	pb.RegisterFirestoreServer(server, service)
	serveDone := make(chan error, 1)
	go func() { serveDone <- server.Serve(listener) }()
	t.Cleanup(func() {
		server.Stop()
		_ = listener.Close()
		if err := <-serveDone; err != nil && err != grpc.ErrServerStopped {
			t.Errorf("local server: %v", err)
		}
	})
	opts := append(grpcTransportOptions(), grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return listener.DialContext(ctx) }), grpc.WithDefaultServiceConfig(`{"methodConfig":[{"name":[{"service":"google.firestore.v1.Firestore"}],"retryPolicy":{"maxAttempts":4,"initialBackoff":"0.001s","maxBackoff":"0.001s","backoffMultiplier":1,"retryableStatusCodes":["UNAVAILABLE"]}}]}`))
	conn, err := grpc.NewClient("passthrough:///firestore.googleapis.com:443", opts...)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	client, err := firestore.NewClient(context.Background(), option.WithGRPCConn(conn))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func wireCommands() []command {
	const document = "projects/sample-project/databases/(default)/documents/c/d"
	const parent = "projects/sample-project/databases/(default)/documents"
	return []command{
		{RPC: "get", Request: json.RawMessage(`{"name":"` + document + `"}`)},
		{RPC: "update", Request: json.RawMessage(`{"document":{"name":"` + document + `","fields":{"value":{"integerValue":"1"}}}}`)},
		{RPC: "delete", Request: json.RawMessage(`{"name":"` + document + `"}`)},
		{RPC: "list", Request: json.RawMessage(`{"parent":"` + parent + `","collectionId":"c","pageSize":1}`)},
		{RPC: "collections", Request: json.RawMessage(`{"parent":"` + parent + `","pageSize":1}`)},
		{RPC: "query", Request: json.RawMessage(`{"parent":"` + parent + `","structuredQuery":{"from":[{"collectionId":"c"}],"limit":1}}`)},
	}
}
func TestWireRequestsNeverRetry(t *testing.T) {
	for _, cmd := range wireCommands() {
		t.Run(cmd.RPC, func(t *testing.T) {
			service := &wireFirestore{unavailable: true}
			client := wireClient(t, service)
			ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
			defer cancel()
			result, code := execute(ctx, client, cmd)
			if code != "provider_unavailable" || result != nil {
				t.Fatalf("unexpected failure mapping: %s %s", code, result)
			}
			if got := service.calls.Load(); got != 1 {
				t.Fatalf("request retried: %d wire attempts", got)
			}
		})
	}
}
func TestWireResponseBounds(t *testing.T) {
	for _, cmd := range wireCommands() {
		if cmd.RPC == "delete" {
			continue
		}
		t.Run(cmd.RPC, func(t *testing.T) {
			for _, tc := range []struct {
				name string
				size int
				code string
			}{{"small", 1024, ""}, {"application limit", 470 * 1024, "response_too_large"}, {"wire limit", 481 * 1024, "provider_unavailable"}} {
				t.Run(tc.name, func(t *testing.T) {
					service := &wireFirestore{document: &pb.Document{Name: "projects/sample-project/databases/(default)/documents/c/d", Fields: map[string]*pb.Value{"value": {ValueType: &pb.Value_StringValue{StringValue: strings.Repeat("x", tc.size)}}}}}
					client := wireClient(t, service)
					ctx, cancel := context.WithTimeout(context.Background(), time.Second)
					defer cancel()
					result, code := execute(ctx, client, cmd)
					if code != tc.code {
						t.Fatalf("response bound bypassed: code=%q want=%q", code, tc.code)
					}
					if got := service.calls.Load(); got != 1 {
						t.Fatalf("response caused retry: %d attempts", got)
					}
					if tc.code == "" && (len(result) != 1 || !strings.Contains(string(result[0]), strings.Repeat("x", tc.size))) {
						t.Fatal("small wire response lost")
					}
				})
			}
		})
	}
}
