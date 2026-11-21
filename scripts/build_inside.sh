#!/bin/sh
set -eu
mkdir -p /out/scripts
sh /input/scripts/install-go-toolchain.sh /out/scripts/go-toolchain-selected.json
cp -a /upstream /src
cd /src
git apply /input/scripts/patches/0000-security-baseline.patch
printf '%s\n' '567a748775f167d78c6f9ec90f49d2deb40109a9a8bbad1c17f7987dcf69f9e9  go.mod' '19d3fba8c5f5a3cea31533dfdd040059d0b5f515c5a85f4f27a67f7ee882d5d2  go.sum' | sha256sum -c -
export GOFLAGS=-mod=readonly GOTOOLCHAIN=local GOMAXPROCS=2
export GOMODCACHE=/go/pkg/mod GOCACHE=/root/.cache/go-build
test "$(go version | cut -d ' ' -f 3)" = go1.27.4
git apply /input/scripts/patches/0000-approved-prebuilt-profiles.patch
cp -a /input/native /src/managed-firestore
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
