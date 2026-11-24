#!/bin/sh
set -eu
mkdir -p /out/scripts
sh /input/scripts/install-go-toolchain.sh /out/scripts/go-toolchain-selected.json
cp -a /upstream /src
cd /src
git apply /input/scripts/patches/0000-security-baseline.patch
printf '%s\n' 'fcd54b9381c98a47bceec950aa9c81b6841dfe9d4b4d4d93911c4d6f27746858  go.mod' '19c2dfb5c69fda4894738b861013043f716360bbf37d878867c315dff18732cf  go.sum' | sha256sum -c -
export GOFLAGS=-mod=readonly GOTOOLCHAIN=local GOMAXPROCS=2
export GOMODCACHE=/go/pkg/mod GOCACHE=/root/.cache/go-build
test "$(go version | cut -d ' ' -f 3)" = go1.27.4
git apply /input/scripts/patches/0000-approved-prebuilt-profiles.patch
cp -a /input/native /src/managed-firestore
sha256sum go.mod go.sum > /tmp/fs-module-lock
go test -p 1 ./managed-firestore -count=1
export SOURCE_DATE_EPOCH=1795211695
for target in linux-amd64 linux-arm64; do
 arch=${target#linux-}
 mkdir -p /out/bin/$target
 CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -p 1 -trimpath -buildvcs=false -ldflags "-s -w -buildid= -X github.com/googleapis/mcp-toolbox/cmd.buildType=flowsteward.firestore -X github.com/googleapis/mcp-toolbox/cmd.commitSha=24762d91babd43d91afc3daeeece1cb446266c54" -o /out/bin/$target/toolbox ./managed-firestore
 chmod 0755 /out/bin/$target/toolbox
 echo "[PASS] $target $(stat -c %s /out/bin/$target/toolbox) bytes"
done
sha256sum -c /tmp/fs-module-lock
