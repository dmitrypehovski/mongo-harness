#!/usr/bin/env bash
# Run MongoDB's official MCP server against the harness cluster, read-only.
#
# This is the *audit* path, not the harness's own path. The agent inside the harness
# reaches MongoDB through the driver, with a tool surface the envelope holds down to
# find/aggregate/count. This server is for a human or a judge to inspect the ledger
# with MongoDB's own tooling, and it is deliberately read-only: in this mode the
# server does not even register the write tools, so an audit cannot turn into an edit.
#
# Usage (as a stdio server for an MCP client):
#   bash mcp/run_mongodb_mcp.sh
#
# Usage with mcporter:
#   mcporter list --stdio "bash mcp/run_mongodb_mcp.sh" --name mongodb-atlas --schema
#   mcporter call --stdio "bash mcp/run_mongodb_mcp.sh" --name mongodb-atlas \
#     mongodb-atlas.count database=harness collection=edits
#
# The connection string is read from a file and never printed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URI_FILE="${MH_URI_FILE:-/root/.secrets/atlas_uri}"

if [[ ! -s "$URI_FILE" ]]; then
  echo "no connection string in $URI_FILE (set MH_URI_FILE to point elsewhere)" >&2
  exit 1
fi

export MDB_MCP_CONNECTION_STRING="$(cat "$URI_FILE")"
# No writes, no server-side JavaScript, no telemetry leaving the machine.
export MDB_MCP_READ_ONLY=true
export MDB_MCP_DISABLE_SERVER_SIDE_JS=true
export MDB_MCP_TELEMETRY=disabled

cd "$REPO_ROOT"
exec npx --yes mongodb-mcp-server "$@"
