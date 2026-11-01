#!/bin/sh
set -eu
mkdir -p /src
mv /src/native /src/managed-firestore
cd /src
gofmt -w managed-firestore/*.go
go test -p 1 ./managed-firestore
mkdir -p /out/third_party/go
cp /usr/local/go/LICENSE /out/third_party/go/LICENSE
go list -deps -f "{{if .Module}}{{.Module.Path}}|{{.Module.Dir}}{{end}}" ./managed-firestore | sort -u > /tmp/modules
while IFS="|" read -r name directory; do
  test -n "$name" || continue
  safe=$(printf "%s" "$name" | tr / _)
  mkdir -p "/out/third_party/$safe"
  for notice in LICENSE LICENSE.txt LICENSE.md NOTICE; do
    if test -f "$directory/$notice"; then cp "$directory/$notice" "/out/third_party/$safe/$notice"; fi
  done
done < /tmp/modules
for arch in amd64 arm64; do
  mkdir -p /out/bin/linux-$arch
  CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -p 1 -trimpath -buildvcs=false -ldflags "-s -w -buildid=" -o /out/bin/linux-$arch/toolbox ./managed-firestore
  chmod 0755 /out/bin/linux-$arch/toolbox
done
