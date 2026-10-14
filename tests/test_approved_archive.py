from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import context_sources as sources

def test_archived_approved_global_update_reaches_another_client(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    (project / '.git').mkdir()
    vault = tmp_path / 'vault'
    archive = vault / '_approved-native-updates' / 'memory'
    archive.mkdir(parents=True)
    note = archive / 'decision.md'
    note.write_text('---\nscope: global\ntype: feedback\n---\nDo not restore the rejected mechanism.', encoding='utf-8')
    monkeypatch.setattr(sources, 'VAULT_DIR', vault)
    monkeypatch.setattr(sources, 'APPROVED_UPDATES', tmp_path / 'absent-client-cache')
    assert note in sources.approved_updates(str(project))

def test_exact_archived_copy_deduplicated_but_scopes_and_conflicts_preserved(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    (project / '.git').mkdir()
    native = tmp_path / 'native'
    native.mkdir()
    vault = tmp_path / 'vault'
    archive = vault / '_approved-native-updates' / 'memory'
    archive.mkdir(parents=True)
    body = '---\nscope: global\n---\nCurrent quality correction.'
    (native / 'a.md').write_text(body, encoding='utf-8')
    (archive / 'a.md').write_text(body, encoding='utf-8')
    (archive / 'conflict.md').write_text(body + ' Conflicting detail.', encoding='utf-8')
    (archive / 'other-project.md').write_text('---\nproject: /another/project\n---\nUnrelated state.', encoding='utf-8')
    monkeypatch.setattr(sources, 'VAULT_DIR', vault)
    monkeypatch.setattr(sources, 'APPROVED_UPDATES', native)
    results = sources.approved_updates(str(project))
    assert len(results) == 2
    assert native / 'a.md' in results
    assert archive / 'conflict.md' in results
