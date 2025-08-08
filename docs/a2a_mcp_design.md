### A2A/MCP Design Overview

This document describes the enhanced Model Context Protocol with AI-to-AI (A2A) extensions for KubeStellar's Management Control Plane.

Key components:
- Protocol primitives (`src/a2a/protocol.py`): message envelope and types
- Broker (`src/a2a/broker.py`): async pub/sub and direct messaging
- Shared Context (`src/a2a/context.py`): compact, hashed snapshots and deltas
- Consensus (`src/a2a/consensus.py`): majority vote for small clusters
- Routing (`src/a2a/router.py`): topic helpers based on cluster/resource/role
- Serialization (`src/a2a/serialization.py`): compact JSON and gzip helpers
- Security (`src/a2a/security.py`): HMAC tokens and role checks
- MCP wiring (`src/mcp/server.py`): registers handlers and holds shared context

Performance goals:
- Keep hot path allocations minimal
- Avoid blocking I/O in request path
- Use compact JSON and topic fanout with drop-on-full queues

Security:
- HMAC tokens per agent, role registry in-process
- Pluggable for mTLS/OIDC later

Testing:
- Unit tests for protocol, broker, context deltas, and export function
- Target 90%+ coverage for new modules


