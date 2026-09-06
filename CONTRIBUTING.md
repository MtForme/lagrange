# Contributing to Lagrange

Thanks for your interest. Lagrange is early and the design is still
moving, so an issue to discuss an idea before a large PR is usually the
fastest path.

## Development setup

```bash
git clone https://github.com/MtForme/lagrange
cd lagrange
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.11+.

## Before you open a PR

```bash
pytest            # all tests must pass
ruff check .      # lint must be clean
ruff format .     # apply formatting
```

CI runs the same on Python 3.11, 3.12 and 3.13.

## Design rules

These are enforced in review because they are the point of the project:

1. **Nodes never communicate.** A node sees only the proposed `Memory`
   and the read-only `context` dict from the coordinator. No shared
   mutable state, no node-to-node calls. All coordination lives in
   `lagrange/coordinator.py`.
2. **Consensus logic lives in `lagrange/consensus/pbft.py`.** Keep nodes
   and the coordinator thin; put new consensus behavior there.
3. **Keep each node small** (roughly < 150 lines). A node is one
   verification strategy, not a framework.
4. **Fail safe.** Any ambiguity — no votes, a tie, an exception in a
   node, an unreachable threshold — resolves to *quarantine*, never
   *accept*. There must be no code path that accepts by default.
5. **Write the test first**, especially for a new node or a new attack.
   `tests/test_attacks.py` is the red-team suite; new defenses should be
   motivated by a new attack test there.
6. **Don't overclaim.** If a defense is partial, say so in the docstring
   and, if it is a user-visible limitation, in the README. A documented
   gap (see `test_KNOWN_LIMITATION_*`) is acceptable; a hidden one is
   not.

## Adding a node

A node subclasses `lagrange.nodes.base_node.BaseNode`, sets a `node_id`,
and implements `evaluate(memory, context) -> NodeVote`. Note that the
consensus rule assumes an odd node count with a 2/3 threshold; changing
the number of nodes is a consensus-design change, not a drop-in.

## Commit messages

Explain *why*, not just *what*. Present tense, imperative mood
("Add temporal burst detection", not "Added…").

## License

By contributing you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
