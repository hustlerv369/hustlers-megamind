#!/usr/bin/env python3
"""Query-aware retrieval on every turn; no file-level seen suppression."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from lib import extract_keywords, extract_snippet, find_memory_dir, grep_memory, read_hook_input
from context_sources import search, render

def _memory_hits(payload,cwd,prompt):
    mem=find_memory_dir(cwd)
    keywords=extract_keywords(prompt)
    if not keywords:return ""
    matches=search(cwd,keywords,mem)
    return render(matches,keywords)

def main():
    payload=read_hook_input()
    output=_memory_hits(payload,payload.get("cwd"),payload.get("prompt") or payload.get("user_prompt_text") or "")
    if output:print(output)

if __name__=="__main__":main()
