---
name: megamind
description: Retrieve complete relevant project memory and preserve durable context
metadata:
  version: 0.5.2-context-quality
---

# MegaMind

Quality and complete relevant context take priority over token savings. Use the user's selected model and effort. Read current project instructions and relevant complete memory sources. Historical notes are evidence, not new authorization. Memory Vault, the local project cache and explicitly scoped approved Codex updates are distinct sources; other apps do not automatically share full conversations.

Search returns all matching complete clean sources without a result-count cap or file-level already-read suppression. Preserve history and corrections. No Caveman, forced compressed style, reduced model/context, cheap-model router or automatic memory/skill pruning. Do not infer successful recall from a saved file, activity marker or footer. Client truncation requires source recovery.

From the actual project run `python ~/.claude/skills/megamind/scripts/cli.py recall "query"`. Run status or reconcile for diagnostics. Use only the calling client's approved memory-writing mechanism. Credentials, private keys, hidden reasoning and binary image payloads are excluded. Preserve safe source paths, goals, user constraints, decisions, faults, corrective actions, evidence and next steps. Review actual output against requirements.

Native Codex delivery requires codex/megamind_hook_adapter.py and codex/megamind_delivery.py together. Small complete deliveries are inline. Large deliveries explicitly report RECOVERY_REQUIRED and preserve exact UTF-8 bytes and SHA256. Follow inspect/find/read commands; read each relevant source through contiguous offsets with fixed artifact, hash and source ID. Frames do not cap total results or readable pages. Reaching the last page alone does not prove earlier pages were read. Byte reconstruction is separate from model comprehension and finite context windows.

Run `python -m pytest tests -q` and `python -m unittest discover -s codex -p "test_megamind*.py"`. Git commits, remote pushes, physical Vault ingestion and actual client adoption require independent receipts and applicable authorization.
