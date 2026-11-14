# Changelog

## 1.0.11 - 2026-11-14

- Declare extension host contract 1.5.0 for the artifact-free service descriptor, so current hosts can install the release. Workflow action IDs, inputs, outputs and provider behavior are unchanged.

## 1.0.10

- Rebuild Linux AMD64 and ARM64 native payloads with google.golang.org/api v0.315.0 on the pinned Toolbox v1.17.0 and verified Go 1.27.4 baseline.
- Preserve the other selected dependency versions, connector controls and approved profiles; reject the superseded Google API module during package verification.

## 1.0.9

- Rebuild both Linux architectures in CI from pinned MCP Toolbox v1.17.0 and the reviewed Go 1.27.4 dependency floor.
- Preserve connector restrictions, safety patches and native build information validation; record generated provenance per build.
- Fetch the exact upstream source automatically and reject dirty source overrides.

