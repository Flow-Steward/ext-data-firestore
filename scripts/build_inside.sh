#!/bin/sh
set -eu
mkdir -p /src
mv /src/native /src/managed-firestore
cd /src
git apply scripts/patches/0000-security-baseline.patch
printf "%s\n" "7f367f79f68cc28cfcb8c7d36c5533ef79f5016aaeba4443a795a46132105fb5  go.mod" "ca2ace78373b79e7c2b048e69ef22abfb93f1b3a537b7f035ad7c1a0c28542e9  go.sum" | sha256sum -c -
export GOFLAGS=-mod=readonly GOTOOLCHAIN=local
sha256sum go.mod go.sum > /tmp/fs-security-module-lock
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

sha256sum -c /tmp/fs-security-module-lock
