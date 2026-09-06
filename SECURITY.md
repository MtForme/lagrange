# Security Policy

Lagrange is a security project, and it is **alpha software**. Please read
the "Status & limitations" section of the [README](README.md) and the
"Known open problems" section of [`docs/DESIGN.md`](docs/DESIGN.md) before
relying on it — several limitations are known and documented, not bugs.

## Reporting a vulnerability

Report suspected vulnerabilities through GitHub's **private vulnerability
reporting**:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue, the affected version or commit, and a minimal
   reproduction.

This keeps the report private until a fix is available. Please do **not**
open a public issue for a security report.

For a project of this size, expect an initial acknowledgement within a
few days. There is no bug-bounty program.

### What is in scope

- A way to get a memory **accepted** into the store that should have been
  quarantined under the [threat model](docs/DESIGN.md#2-threat-model)
  (grey-box attacker: query access and context injection, no weight
  access, no direct store or signing-key access).
- Forging or replaying an `internal_system` signature.
- Bypassing the MCP server's restriction that an agent cannot write
  `source="internal_system"`.
- Crashing or hanging the coordinator with a crafted write.

### What is already known (not a vulnerability)

- Policy/preference injection through a trusted `direct_chat` write with
  no spoofed source and no indirect vector is **not** caught. This is
  documented as `test_KNOWN_LIMITATION_...` in `tests/test_attacks.py`.
- The contradiction and instruction detectors are keyword lists and can
  be evaded by paraphrase.
- The coordinator is a single point of failure; compromising 2 of 3
  nodes defeats consensus.

If you have an idea for closing one of these, an issue or PR is welcome —
that is normal development, not a security report.

## Supported versions

Pre-1.0: only the latest release on the `main` branch receives fixes.
