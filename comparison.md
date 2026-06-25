# Fabric OBO Architecture Comparison

> **Status**: Approach A is archived (`archive/approach-a/`). Approach B is the canonical baseline.

This document records the architectural comparison made during development. Approach A source code is
preserved for reference in `archive/approach-a/` but is not part of the active runtime.

## Approach A: MAF + Foundry + MCP token-arg injection (ARCHIVED)

- Backend: `archive/approach-a/backend/main.py`
- MCP: `archive/approach-a/mcp_server/server.py`
- Flow:
  1. Backend validates incoming bearer token.
  2. Backend performs OBO to get Fabric token.
  3. Backend injects fabric_token into MCP tool arguments at invocation time.
  4. MCP executes schema and DAX tools.

### Pros

- Straightforward control in one backend process.
- Explicit OBO and auth handling in backend code.

### Cons

- Requires tool-schema mutation to hide fabric_token from model.
- Tighter coupling between orchestration and auth/token plumbing.
- Harder to reuse MCP server with different orchestrators.

## Approach B: Copilot SDK + header-forwarded OBO MCP — CANONICAL BASELINE

- Backend: `backend_gh/main.py`
- MCP: `mcp_server_obo/server.py`
- Flow:
  1. Backend validates incoming bearer token.
  2. Backend forwards Authorization header only to the dedicated OBO MCP server.
  3. MCP resolves Fabric token per request:
     - Valid Authorization header: validate + OBO user token.
     - Invalid/missing Authorization header: fail closed.
  4. MCP executes schema and DAX tools.

### Pros

- Cleaner separation of concerns; MCP owns execution identity.
- No tool-argument mutation and no hidden auth argument in tool schema.
- Easier to reason about confused-deputy controls at server boundary.
- Frontend MSAL config served via backend `/client-config` — no hardcoded IDs.

### Cons

- Requires separate OBO MCP server process.
- Header-routing guardrails must be configured explicitly.

## Security Comparison

- Approach A confused-deputy risk: exists in argument injection path if tool schemas drift.
- Approach B confused-deputy mitigation: explicit allowlist routing; fail-closed on invalid auth.

## Operational Notes

- Approach B OBO MCP default: `http://localhost:8002/mcp`
- Approach B backend default: `http://localhost:8000`
- Approach A: archived — see `archive/approach-a/` for historical reference.


## Approach A: MAF + Foundry + MCP token-arg injection

- Backend: backend/main.py
- MCP: mcp_server/server.py
- Flow:
  1. Backend validates incoming bearer token.
  2. Backend performs OBO to get Fabric token.
  3. Backend injects fabric_token into MCP tool arguments at invocation time.
  4. MCP executes schema and DAX tools.

### Pros

- Straightforward control in one backend process.
- Explicit OBO and auth handling in backend code.
- Existing behavior already validated in this project.

### Cons

- Requires tool-schema mutation to hide fabric_token from model.
- Tighter coupling between orchestration and auth/token plumbing.
- Harder to reuse MCP server with different orchestrators.

## Approach B: Copilot SDK + header-forwarded OBO MCP (Kratos style)

- Backend: backend_gh/main.py
- MCP: mcp_server_obo/server.py
- Flow:
  1. Backend optionally validates incoming bearer token.
  2. Backend forwards Authorization header only to a dedicated OBO MCP server.
  3. MCP resolves Fabric token per request:
     - No Authorization header: agent identity fallback.
     - Valid Authorization header: validate + OBO user token.
     - Invalid Authorization header: fail closed (no fallback).
  4. MCP executes schema and DAX tools.

### Pros

- Cleaner separation of concerns; MCP owns execution identity.
- No tool-argument mutation and no hidden auth argument in tool schema.
- Easier to reason about confused-deputy controls at server boundary.

### Cons

- More moving parts (separate OBO MCP server/process).
- Requires careful header-routing guardrails in backend config.
- Added auth complexity inside MCP transport boundary.

## Security Comparison

- Approach A confused-deputy risk surface:
  - Lower at MCP transport boundary (no bearer headers forwarded), but risk exists in argument injection path if tool schemas drift.
- Approach B confused-deputy risk surface:
  - Mitigated by explicit allow-list routing: backend_gh forwards Authorization only to OBO_MCP_SERVER_NAME/OBO_MCP_SERVER_URL.
  - MCP fail-closed behavior for malformed/invalid Authorization prevents silent fallback abuse.

## Operational Notes

- Approach A default MCP URL: http://localhost:8001/mcp
- Approach B default OBO MCP URL: http://localhost:8002/mcp
- Run either stack independently in normal usage; both are kept for experimentation and comparison.

## Recommendation Matrix

- Choose Approach A when:
  - You need the fastest path with existing validated behavior.
  - You are already standardized on Agent Framework + Foundry integration.

- Choose Approach B when:
  - You want transport-boundary auth and cleaner server-side execution ownership.
  - You need a model closer to production gateway/service boundary patterns.
