#!/usr/bin/env python3
"""Use shared Megamind compaction with a text-only Codex JSONL adapter."""
from __future__ import annotations

from collections import deque
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

SHARED_SCRIPTS = Path.home() / '.claude' / 'skills' / 'megamind' / 'scripts'
if not (SHARED_SCRIPTS / 'hook_pre_compact.py').is_file():
    bundled = Path(__file__).resolve().parent.parent / 'scripts'
    if (bundled / 'hook_pre_compact.py').is_file():
        SHARED_SCRIPTS = bundled
MAX_LINE = 1024 * 1024
MAX_TEXT = 16000
_SECRET = re.compile(
    r'(?<![\w-])(?:sk-(?:ant-)?[\w-]{16,}|gh[pousr]_[\w]{20,}|'
    r'github_pat_[\w]{20,}|AIza[\w-]{25,}|AKIA[A-Z0-9]{16}|'
    r'eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,})'
    r'|(?i:-----BEGIN .*PRIVATE KEY-----|authorization\s*[:=]|'
    r'\b(?:[\w-]*(?:api[_-]?key|secret|token|password|passwd|credential)[\w-]*)'
    r'[\"\x27]?\s*[:=]\s*[^\s])'
)


def _clean_text(text):
    if not isinstance(text, str):
        return ''
    # Keep prose only; a credential-bearing line is discarded in full.
    result = []
    in_private_key = False
    for line in text.splitlines():
        if '-----BEGIN ' in line and 'PRIVATE KEY-----' in line:
            in_private_key = True
        if in_private_key:
            if '-----END ' in line and 'PRIVATE KEY-----' in line:
                in_private_key = False
            continue
        if not _SECRET.search(line) and 'data:image/' not in line:
            result.append(line)
    return '\n'.join(result).strip()


def iter_transcript_blocks(transcript_path: str, limit: int | None = None) -> list[dict]:
    """Read complete safe message text; explicit callers may request a limit.

    Claude's message/content envelope remains supported, using the same safe
    text filter. Duplicate event_msg mirrors of response_item messages collapse.
    Large prose records survive; raw reasoning and image payloads stay excluded.
    """
    records = deque(maxlen=limit)
    recent = None
    try:
        with open(transcript_path, encoding='utf-8', errors='replace') as stream:
            while True:
                line = stream.readline()
                if not line:
                    break
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(obj, dict):
                    continue
                envelope = obj.get('type')
                msg = obj.get('message')
                if envelope in ('response_item', 'event_msg'):
                    payload = obj.get('payload')
                    if not isinstance(payload, dict):
                        continue
                    if envelope == 'response_item' and payload.get('type') in ('function_call', 'custom_tool_call'):
                        raw = payload.get('arguments') or payload.get('input') or '{}'
                        try:
                            args = json.loads(raw) if isinstance(raw, str) else raw
                        except (ValueError, TypeError):
                            args = {}
                        if not isinstance(args, dict): args = {}
                        safe_input = {}
                        for key in ('file_path', 'notebook_path', 'cmd', 'command'):
                            value = args.get(key)
                            if isinstance(value, str) and not _SECRET.search(value): safe_input[key] = value
                        if payload.get('name') == 'apply_patch' and isinstance(raw, str):
                            safe_input['paths'] = re.findall(r'^\*\*\* (?:Add|Update|Delete) File: (.+)$', raw, re.M)
                        if isinstance(raw, str):
                            sources = re.findall(r'''["']([A-Za-z]:[/\\][^"'\r\n]+)["']''', raw)
                            sources += re.findall(r'^\*\*\* (?:Add|Update|Delete) File: (.+)$', raw.replace('\\n', '\n'), re.M)
                            safe_input['paths'] = list(dict.fromkeys(
                                safe_input.get('paths', []) + [path.replace('\\\\', '\\') for path in sources if not _SECRET.search(path)]
                            ))
                        records.append({'role': 'assistant', 'kind': 'tool_use', 'name': payload.get('name'), 'input': safe_input})
                        continue
                    if envelope == 'response_item' and payload.get('type') == 'message':
                        msg = payload
                    elif envelope == 'event_msg' and payload.get('type') in ('user_message', 'agent_message'):
                        msg = {'role': 'user' if payload['type'] == 'user_message' else 'assistant',
                               'content': payload.get('message'), 'channel': payload.get('channel')}
                    else:
                        continue
                if not isinstance(msg, dict) or msg.get('role') not in ('user', 'assistant'):
                    continue
                if msg.get('channel') in ('analysis',) or msg.get('recipient') not in (None, 'all'):
                    continue
                content = msg.get('content')
                if isinstance(content, list):
                    content = '\n'.join(block['text'] for block in content
                                        if isinstance(block, dict)
                                        and block.get('type') in ('text', 'input_text', 'output_text')
                                        and isinstance(block.get('text'), str))
                text = _clean_text(content)
                if not text:
                    continue
                role = msg['role']
                digest = hashlib.sha256((role + '\0' + text).encode()).digest()
                if recent and digest == recent[0] and envelope != recent[1]:
                    continue
                recent = (digest, envelope)
                records.append({'role': role, 'kind': 'summary' if msg.get('channel') == 'summary' else 'text', 'text': text})
    except OSError:
        return []
    return list(records)


def main():
    sys.path.insert(0, str(SHARED_SCRIPTS))
    spec = importlib.util.spec_from_file_location('megamind_shared_precompact', SHARED_SCRIPTS / 'hook_pre_compact.py')
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    from lib import RESUME_TAIL_MESSAGES
    shared.iter_transcript_blocks = lambda path: iter_transcript_blocks(path, RESUME_TAIL_MESSAGES)
    shared.main()  # Retains shared note writing and ledger invalidation.


if __name__ == '__main__':
    main()
