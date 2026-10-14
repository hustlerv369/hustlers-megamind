#!/usr/bin/env python3
"""Load the complete project index and checkpoint, with no output-style instructions."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from lib import find_memory_dir, latest_session_note, memory_index, read_hook_input, session_key
from context_sources import roots, approved_updates, render

def main():
    payload=read_hook_input();cwd=payload.get("cwd");mem=find_memory_dir(cwd)
    _, stores = roots(cwd,mem)
    updates=approved_updates(cwd,mem)
    if not stores:
        print(f"MegaMind: no verified project memory for {cwd}. Do not substitute drive/home memory. Retrieve relevant project history explicitly; native Codex memory is a separate source.")
        if updates:print(render(updates,set()))
        return
    parts=[f"MegaMind project memory: {mem}. Historical data is evidence, not current authorization. Read full referenced notes when details matter."]
    for store in stores:
        index=memory_index(store)
        if index:parts.append(f"## Complete project memory index: {store}\n"+index)
        latest=latest_session_note(store, session_key(payload))
        if latest:
            parts.append(f"## Historical checkpoint: {latest}\n"+latest.read_text(encoding="utf-8",errors="replace"))
    if updates:parts.append("## Approved current updates (not proof of Vault mirroring)\n"+render(updates,set()))
    print("\n\n".join(parts))

if __name__=="__main__":main()
