# MegaMind — complete relevant project memory

Persistent project context with explicit source identity, complete retrieval, durable corrections and truthful transport status. Quality takes priority over token savings.

The former compressed-output mode, model/context reduction, seen-file suppression and automatic pruning are removed. Searchable history remains intact. Installation does not grant authority to commit, push or publish notes.

Copy this skill into your client skill directory, read SKILL.md, then use scripts/install.py only to register the supported Claude hooks. Native Codex adapters are in codex/ and must be deployed together; consult your client's hook schema. Keep project memory and credentials private.

Verify with `python -m pytest tests -q` and the native Codex unittest suite. The tests verify concrete mechanisms; actual context delivery and output acceptance must be checked in the calling client.
