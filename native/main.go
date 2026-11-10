// Managed Firestore adaptation for the dependency-locked Google MCP Toolbox source.
// No upstream high-level conversion, Rules client, BulkWriter or random document IDs.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"io"
	"os"
	"time"

	firestore "cloud.google.com/go/firestore/apiv1"
	pb "cloud.google.com/go/firestore/apiv1/firestorepb"
	"github.com/googleapis/gax-go/v2"
	"golang.org/x/oauth2"
	"google.golang.org/api/iterator"
	"google.golang.org/api/option"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

type command struct {
	RPC     string          `json:"rpc"`
	Request json.RawMessage `json:"request"`
}

type input struct {
	ID      int     `json:"id"`
	Command command `json:"command"`
	Timeout int     `json:"timeout_seconds"`
	Token   string  `json:"access_token"`
}

// Share the transport guards with every connection made by this adapter.
func grpcTransportOptions() []grpc.DialOption {
	return []grpc.DialOption{
		grpc.WithDisableRetry(),
		grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(480*1024), grpc.MaxRetryRPCBufferSize(0)),
	}
}

func main() {
	result, code := run()
	out := map[string]any{"jsonrpc": "2.0", "id": 2, "result": result}
	if code != "" {
		out = map[string]any{"jsonrpc": "2.0", "id": 2, "error": true, "error_code": code}
	}
	_ = json.NewEncoder(os.Stdout).Encode(out)
}
func run() ([]json.RawMessage, string) {
	var in input
	raw, err := bufio.NewReader(io.LimitReader(os.Stdin, 264*1024+1)).ReadBytes('\n')
	if err != nil || len(raw) > 264*1024 {
		return nil, "invalid_payload"
	}
	if json.Unmarshal(raw, &in) != nil || in.Timeout < 1 || in.Timeout > 30 {
		return nil, "invalid_payload"
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(in.Timeout)*time.Second)
	defer cancel()
	opts := []option.ClientOption{option.WithEndpoint("firestore.googleapis.com:443")}
	for _, transportOption := range grpcTransportOptions() {
		opts = append(opts, option.WithGRPCDialOption(transportOption))
	}
	if in.Token != "" {
		opts = append(opts, option.WithTokenSource(oauth2.StaticTokenSource(&oauth2.Token{AccessToken: in.Token})))
	} else {
		// Only the adapter sets this environment variable to its own 0600 temporary file.
		file := os.Getenv("GOOGLE_APPLICATION_CREDENTIALS")
		if file == "" {
			return nil, "authentication_failed"
		}
		key, e := os.ReadFile(file)
		if e != nil {
			return nil, "authentication_failed"
		}
		opts = append(opts, option.WithCredentialsJSON(key))
	}
	client, err := firestore.NewClient(ctx, opts...)
	if err != nil {
		return nil, "provider_unavailable"
	}
	defer client.Close()
	return execute(ctx, client, in.Command)
}

func execute(ctx context.Context, client *firestore.Client, cmd command) ([]json.RawMessage, string) {
	var err error
	// Explicit override defeats GAPIC default retries for every request, including writes.
	noRetry := gax.WithRetry(func() gax.Retryer { return nil })
	result := []json.RawMessage{}
	total := 0
	add := func(message proto.Message) bool {
		b, e := protojson.Marshal(message)
		if e != nil {
			return false
		}
		total += len(b)
		if total > 460*1024 || len(result) >= 100 {
			return false
		}
		result = append(result, b)
		return true
	}
	decode := func(message proto.Message) bool { return protojson.Unmarshal(cmd.Request, message) == nil }
	switch cmd.RPC {
	case "get":
		r := &pb.GetDocumentRequest{}
		if !decode(r) {
			return nil, "invalid_payload"
		}
		v, e := client.GetDocument(ctx, r, noRetry)
		err = e
		if err == nil && !add(v) {
			return nil, "response_too_large"
		}
	case "update":
		r := &pb.UpdateDocumentRequest{}
		if !decode(r) {
			return nil, "invalid_payload"
		}
		v, e := client.UpdateDocument(ctx, r, noRetry)
		err = e
		if err == nil && !add(v) {
			return nil, "response_too_large"
		}
	case "delete":
		r := &pb.DeleteDocumentRequest{}
		if !decode(r) {
			return nil, "invalid_payload"
		}
		err = client.DeleteDocument(ctx, r, noRetry)
	case "list":
		r := &pb.ListDocumentsRequest{}
		if !decode(r) || r.PageSize < 1 || r.PageSize > 100 {
			return nil, "invalid_payload"
		}
		// Fetch one bounded page; do not silently traverse every page via the iterator.
		it := client.ListDocuments(ctx, r, noRetry)
		page := []*pb.Document{}
		token, e := iterator.NewPager(it, int(r.PageSize), r.PageToken).NextPage(&page)
		err = e
		if err == nil {
			for _, v := range page {
				if !add(v) {
					return nil, "response_too_large"
				}
			}
			if token != "" {
				b, _ := json.Marshal(map[string]string{"next_page_token": token})
				total += len(b)
				if total > 460*1024 {
					return nil, "response_too_large"
				}
				result = append(result, b)
			}
		}
	case "collections":
		r := &pb.ListCollectionIdsRequest{}
		if !decode(r) || r.PageSize < 1 || r.PageSize > 100 {
			return nil, "invalid_payload"
		}
		it := client.ListCollectionIds(ctx, r, noRetry)
		page := []string{}
		token, e := iterator.NewPager(it, int(r.PageSize), r.PageToken).NextPage(&page)
		err = e
		if err == nil {
			for _, v := range page {
				b, _ := json.Marshal(map[string]string{"collection_id": v})
				total += len(b)
				result = append(result, b)
			}
			if token != "" {
				b, _ := json.Marshal(map[string]string{"next_page_token": token})
				result = append(result, b)
			}
			if total > 460*1024 || len(result) > 101 {
				return nil, "response_too_large"
			}
		}
	case "query":
		r := &pb.RunQueryRequest{}
		if !decode(r) || r.GetStructuredQuery() == nil || r.GetStructuredQuery().GetLimit().GetValue() < 1 || r.GetStructuredQuery().GetLimit().GetValue() > 100 {
			return nil, "invalid_payload"
		}
		stream, e := client.RunQuery(ctx, r, noRetry)
		err = e
		if err == nil {
			for {
				v, e := stream.Recv()
				if e == io.EOF {
					break
				}
				if e != nil {
					err = e
					break
				}
				if v.Document != nil && !add(v.Document) {
					return nil, "response_too_large"
				}
			}
		}
	default:
		return nil, "invalid_payload"
	}
	if err != nil {
		return nil, "provider_unavailable"
	}
	return result, ""
}
