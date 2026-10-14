"""Read-only scoped retrieval across Memory Vault, live cache and approved updates.

No ingestion, credentials, automatic Git operation or cross-project fallback.
"""
from pathlib import Path
import os
import re
from lib import (VAULT_DIR, find_memory_dir, project_slug_from_cwd, is_noise_file,
                 is_superseded, extract_snippet, score_file_detail, _safe_mtime,
                 _prose_fingerprint, scan_secrets)

APPROVED_UPDATES = Path.home() / '.codex/memories/extensions/ad_hoc/notes'


def project_root(cwd, memory=None):
    requested = Path(os.path.abspath(cwd))
    slug = memory.parent.name.lower() if memory else None
    for parent in [requested, *requested.parents]:
        if slug and project_slug_from_cwd(str(parent)).lower() == slug:
            return parent
        if (parent / '.git').exists():
            git = parent / '.git'
            if git.is_file():
                value = git.read_text(encoding='utf-8').strip()
                if value.startswith('gitdir:'):
                    gitdir = (parent / value.split(':',1)[1].strip()).resolve()
                    common = gitdir.parent.parent
                    if gitdir.parent.name == 'worktrees' and common.name == '.git':
                        return common.parent
            return parent
    return requested


def roots(cwd, memory=None):
    if not cwd:
        return None, []
    memory = memory if memory is not None else find_memory_dir(cwd)
    root = project_root(cwd, memory)
    slug = memory.parent.name if memory else project_slug_from_cwd(str(root))
    vault = VAULT_DIR / slug / 'memory'
    # Both copies remain evidence. Conflicting content is never silently merged.
    result = [vault] if vault.is_dir() else []
    if memory and memory.is_dir() and memory not in result:
        result.append(memory)
    return root, result


def approved_updates(cwd, memory=None):
    root, _ = roots(cwd, memory)
    if root is None:
        return []
    normal = lambda value: str(value).replace('\\', '/').rstrip('/').casefold()
    result = []
    seen = set()
    # Approved native notes can be explicitly archived into the private Vault.
    # Reading this archive never performs ingestion, commits or remote sync.
    for directory in (APPROVED_UPDATES, VAULT_DIR / '_approved-native-updates' / 'memory'):
        if not directory.is_dir():
            continue
        for path in directory.glob('*.md'):
            text = path.read_text(encoding='utf-8')
            if not text.startswith('---\n'):
                continue  # unscoped legacy updates require explicit retrieval
            head = text.split('\n---', 1)[0]
            project = re.search(r'^project:\s*(.+)$', head, re.M)
            global_scope = re.search(r'^scope:\s*global\s*$', head, re.M)
            if global_scope or (project and normal(project.group(1).strip('"\'')) == normal(root)):
                if not is_superseded(path) and not scan_secrets(text):
                    if text in seen:
                        continue
                    seen.add(text)
                    result.append(path)
    return sorted(result, key=_safe_mtime, reverse=True)


def notes(cwd, memory=None):
    _, stores = roots(cwd, memory)
    result = []
    seen = set()
    for store in stores:
        for path in store.rglob('*.md'):
            if is_noise_file(path) or is_superseded(path):
                continue
            if scan_secrets(path.read_text(encoding='utf-8', errors='replace')):
                continue
            fingerprint = _prose_fingerprint(path)
            if fingerprint and fingerprint in seen:
                continue
            if fingerprint:
                seen.add(fingerprint)
            result.append(path)
    result.extend(approved_updates(cwd, memory))
    return result


def search(cwd, keywords, memory=None, limit=None):
    ranked = []
    for path in notes(cwd, memory):
        score, _ = score_file_detail(path, keywords)
        if score > 0:
            ranked.append((score, _safe_mtime(path), str(path), path))
    ranked.sort(reverse=True)
    paths = [row[3] for row in ranked]
    return paths if limit is None else paths[:limit]


def render(paths, keywords):
    return '\n\n'.join('## Historical memory source: ' + str(path) + '\n' +
                        extract_snippet(path, keywords) for path in paths)
