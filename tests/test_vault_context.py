"""Memory Vault integration and no-loss regressions; isolated fixtures only."""
from pathlib import Path
NATIVE=Path(__file__).resolve().parents[1]/'codex'
from unittest.mock import patch
import json
import importlib.util
import sys

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import lib, context_sources, hook_user_prompt, hook_session_start
import vault


def setup_store(tmp_path, monkeypatch):
    project=tmp_path/'project';project.mkdir();(project/'.git').mkdir()
    slug=lib.project_slug_from_cwd(str(project))
    live=tmp_path/'live'/slug/'memory';live.mkdir(parents=True)
    vault=tmp_path/'vault';vm=vault/slug/'memory';vm.mkdir(parents=True)
    updates=tmp_path/'approved';updates.mkdir()
    monkeypatch.setattr(context_sources,'VAULT_DIR',vault)
    monkeypatch.setattr(context_sources,'APPROVED_UPDATES',updates)
    monkeypatch.setattr(context_sources,'find_memory_dir',lambda cwd:live)
    monkeypatch.setattr(hook_user_prompt,'find_memory_dir',lambda cwd:live)
    monkeypatch.setattr(hook_session_start,'find_memory_dir',lambda cwd:live)
    return project,live,vm,updates


def test_vault_only_fact_and_live_fact_are_both_retrieved(tmp_path,monkeypatch):
    project,live,vault,_=setup_store(tmp_path,monkeypatch)
    (live/'live.md').write_text('alpha LIVE_FACT')
    (vault/'vault.md').write_text('alpha VAULT_ONLY_FACT')
    result=hook_user_prompt._memory_hits({},str(project),'alpha')
    assert 'LIVE_FACT' in result and 'VAULT_ONLY_FACT' in result


def test_more_than_six_matching_notes_are_retained(tmp_path,monkeypatch):
    project,live,_,_=setup_store(tmp_path,monkeypatch)
    for i in range(12):(live/f'{i}.md').write_text(f'alpha UNIQUE_FACT_{i}')
    result=hook_user_prompt._memory_hits({},str(project),'alpha')
    assert all(f'UNIQUE_FACT_{i}' in result for i in range(12))


def test_full_content_dedup_preserves_conflicting_versions(tmp_path,monkeypatch):
    project,live,vault,_=setup_store(tmp_path,monkeypatch)
    (live/'same.md').write_text('alpha LIVE_VERSION')
    (vault/'same.md').write_text('alpha VAULT_VERSION')
    (vault/'duplicate.md').write_text('alpha LIVE_VERSION')
    result=hook_user_prompt._memory_hits({},str(project),'alpha')
    assert result.count('alpha LIVE_VERSION')==1 and 'VAULT_VERSION' in result


def test_approved_project_updates_loaded_without_cross_project_leak(tmp_path,monkeypatch):
    project,live,_,updates=setup_store(tmp_path,monkeypatch)
    (updates/'yes.md').write_text(f'---\nproject: {project}\n---\nalpha CURRENT_PUBLISHED_ID')
    (updates/'no.md').write_text('---\nproject: D:/OtherProject\n---\nalpha OTHER_PROJECT_PRIVATE')
    result=hook_user_prompt._memory_hits({},str(project),'alpha')
    assert 'CURRENT_PUBLISHED_ID' in result and 'OTHER_PROJECT_PRIVATE' not in result


def test_explicit_global_update_available_to_every_project(tmp_path,monkeypatch):
    project,live,_,updates=setup_store(tmp_path,monkeypatch)
    (updates/'global.md').write_text('---\nscope: global\n---\nalpha GLOBAL_QUALITY_POLICY')
    assert 'GLOBAL_QUALITY_POLICY' in hook_user_prompt._memory_hits({},str(project),'alpha')


def test_startup_includes_vault_index_and_current_approved_update(tmp_path,monkeypatch,capsys):
    project,live,vault,updates=setup_store(tmp_path,monkeypatch)
    (live/'MEMORY.md').write_text('LOCAL_INDEX_END')
    (vault/'MEMORY.md').write_text('VAULT_INDEX_END')
    (updates/'yes.md').write_text(f'---\nproject: {project}\n---\nCURRENT_SHORT_ID')
    with patch.object(hook_session_start,'read_hook_input',return_value={'cwd':str(project)}):
        hook_session_start.main()
    result=capsys.readouterr().out
    assert all(word in result for word in ['LOCAL_INDEX_END','VAULT_INDEX_END','CURRENT_SHORT_ID'])


def test_secret_note_excluded(tmp_path,monkeypatch):
    project,live,vault,updates=setup_store(tmp_path,monkeypatch)
    secret='sk-'+'x'*25
    (vault/'secret.md').write_text('alpha '+secret)
    assert secret not in hook_user_prompt._memory_hits({},str(project),'alpha')


def test_all_assistant_reports_survive_checkpoint():
    records=[{'role':'assistant','kind':'text','text':f'REPORT_{i}'} for i in range(40)]
    result=lib.build_resume(records)
    assert all(f'REPORT_{i}' in result for i in range(40))


def test_codex_more_than_1500_records_and_large_prose_survive(tmp_path):
    source=NATIVE/'megamind_pre_compact.py'
    spec=importlib.util.spec_from_file_location('vault_codex',source)
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    path=tmp_path/'messages.jsonl'
    texts=['FIRST_FACT']+[f'fact{i}' for i in range(1600)]+['z'*1100000+'END_LARGE_PROSE']
    rows=[{'type':'response_item','payload':{'type':'message','role':'user','content':text}} for text in texts]
    path.write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
    result=adapter.iter_transcript_blocks(str(path))
    assert len(result)==len(texts) and result[0]['text']=='FIRST_FACT'
    assert result[-1]['text'].endswith('END_LARGE_PROSE')


def test_repeated_statement_after_changed_context_is_not_deleted(tmp_path):
    source=NATIVE/'megamind_pre_compact.py'
    spec=importlib.util.spec_from_file_location('vault_repeats',source)
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    path=tmp_path/'repeat.jsonl'
    texts=['Publish','Pause','Publish']
    path.write_text('\n'.join(json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':x}}) for x in texts))
    assert [r['text'] for r in adapter.iter_transcript_blocks(str(path))]==texts


def test_vault_sync_blocks_unrelated_staged_files_without_reset(tmp_path,monkeypatch):
    monkeypatch.setattr(vault,'VAULT_DIR',tmp_path)
    calls=[]
    def fake(args,*unused,**kw):
        calls.append(args)
        return (0,'other-project/memory/private.md')
    monkeypatch.setattr(vault,'git_quiet',fake)
    monkeypatch.setattr(vault,'mirror_project_memory',lambda slug:0)
    assert vault.sync('project',force=True).startswith('ABORT: unrelated')
    assert all(args[0] not in ['add','reset','commit','push'] for args in calls)


def test_failed_commit_never_pushes_or_marks_sync_complete(tmp_path,monkeypatch):
    monkeypatch.setattr(vault,'VAULT_DIR',tmp_path)
    monkeypatch.setattr(vault,'mirror_project_memory',lambda slug:0)
    calls=[]
    def fake(args,*unused,**kw):
        calls.append(args)
        if args[:3]==['diff','--cached','--quiet']:return (1,'')
        if args[0]=='commit':return (1,'failed')
        return (0,'')
    monkeypatch.setattr(vault,'git_quiet',fake)
    assert 'commit failed' in vault.sync('project',force=True)
    assert not any(args[0]=='push' for args in calls)
    assert not (tmp_path/'.megamind-last-sync').exists()


def test_prune_does_not_delete_any_history(tmp_path,monkeypatch):
    monkeypatch.setattr(vault,'VAULT_DIR',tmp_path)
    p=tmp_path/'compact-auto.md';p.write_text('preserve history')
    assert vault.prune().startswith('disabled')
    assert p.read_text()=='preserve history'
