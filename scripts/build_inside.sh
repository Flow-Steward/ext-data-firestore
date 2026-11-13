#!/bin/sh
set -eu
sh /out/scripts/install-go-toolchain.sh /out/scripts/go-toolchain-selected.json
cp -a /upstream /src
cd /src
git apply /out/scripts/patches/0000-security-baseline.patch
printf '%s\n' 'ce3c45e7f5d6cb877b357f035a70e3015d00818a5a1d354e714ea28340ae3bf9  go.mod' 'a90a6478c08aa41ef8201589a0ec5ab4e12b9271e8cfee538bb199f3386e2553  go.sum' | sha256sum -c -
export GOFLAGS=-mod=readonly GOTOOLCHAIN=local GOMAXPROCS=2
test "$(go version | cut -d ' ' -f 3)" = go1.27.4
git apply /out/scripts/patches/0000-approved-prebuilt-profiles.patch
cp -a /out/native /src/managed-firestore
sha256sum go.mod go.sum > /tmp/fs-module-lock
go test -p 1 ./managed-firestore -count=1
export SOURCE_DATE_EPOCH=1794536030
for target in linux-amd64 linux-arm64; do
 arch=${target#linux-}
 mkdir -p /out/bin/$target
 CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -p 1 -trimpath -buildvcs=false -ldflags "-s -w -buildid= -X github.com/googleapis/mcp-toolbox/cmd.buildType=flowsteward.firestore -X github.com/googleapis/mcp-toolbox/cmd.commitSha=45ed205cc8682ed066c82e0b65bcd0e8fc3becce" -o /out/bin/$target/toolbox ./managed-firestore
 chmod 0755 /out/bin/$target/toolbox
 echo "[PASS] $target $(stat -c %s /out/bin/$target/toolbox) bytes"
done
sha256sum -c /tmp/fs-module-lock
mkdir -p /out/third_party/go
cp /usr/local/go/LICENSE /out/third_party/go/LICENSE
go list -deps -f '{{if .Module}}{{.Module.Path}}|{{.Module.Dir}}{{end}}' ./managed-firestore | sort -u > /tmp/modules
while IFS='|' read -r name directory; do
 test -n "$name" || continue
 safe=$(printf '%s' "$name" | tr / _)
 mkdir -p "/out/third_party/$safe"
 for notice in LICENSE LICENSE.txt LICENSE.md NOTICE; do
  if test -f "$directory/$notice"; then cp "$directory/$notice" "/out/third_party/$safe/$notice"; fi
 done
done < /tmp/modules
