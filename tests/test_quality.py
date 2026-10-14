"""Regression contract for the user-authorized context-quality repair."""
from pathlib import Path
from unittest.mock import patch
import importlib.util, io, json, os, subprocess, sys

S=Path(__file__).parents[1]/'scripts'
sys.path.insert(0,str(S))
import lib, hook_session_start, hook_user_prompt

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def test_new_question_can_retrieve_other_section(tmp_path):
    note=tmp_path/'complete.md'
    note.write_text('# Memory\nalpha first\n'+'filler\n'*30+'beta UNIQUE_RULE\n',encoding='utf-8')
    with patch.object(hook_user_prompt,'find_memory_dir',return_value=tmp_path):
        first=hook_user_prompt._memory_hits({'session_id':'fixture'},str(tmp_path),'alpha')
        second=hook_user_prompt._memory_hits({'session_id':'fixture'},str(tmp_path),'beta')
    assert 'UNIQUE_RULE' in first and 'UNIQUE_RULE' in second

def test_updated_source_is_not_suppressed(tmp_path):
    note=tmp_path/'changed.md';note.write_text('alpha OLD',encoding='utf-8')
    with patch.object(hook_user_prompt,'find_memory_dir',return_value=tmp_path):
        assert 'OLD' in hook_user_prompt._memory_hits({},str(tmp_path),'alpha')
        note.write_text('alpha NEW',encoding='utf-8')
        assert 'NEW' in hook_user_prompt._memory_hits({},str(tmp_path),'alpha')

def test_fourth_fact_remains_retrievable(tmp_path):
    for i in range(4):(tmp_path/f'n{i}.md').write_text(f'# alpha note {i}\nunique fact {i}',encoding='utf-8')
    with patch.object(hook_user_prompt,'find_memory_dir',return_value=tmp_path):
        output=hook_user_prompt._memory_hits({},str(tmp_path),'alpha')
    assert all(f'unique fact {i}' in output for i in range(4))

def test_entire_index_and_checkpoint_loaded(tmp_path):
    (tmp_path/'MEMORY.md').write_text('index line\n'*400+'FINAL_INDEX_RULE',encoding='utf-8')
    sessions=tmp_path/'sessions';sessions.mkdir()
    (sessions/'checkpoint.md').write_text('checkpoint body\n'*300+'FINAL_CHECKPOINT_RULE',encoding='utf-8')
    buf=io.StringIO()
    with patch.object(hook_session_start,'read_hook_input',return_value={'cwd':str(tmp_path)}),patch.object(hook_session_start,'find_memory_dir',return_value=tmp_path),patch.object(sys,'stdout',buf):
        hook_session_start.main()
    assert 'FINAL_INDEX_RULE' in buf.getvalue() and 'FINAL_CHECKPOINT_RULE' in buf.getvalue()

def test_template_header_does_not_merge_different_facts(tmp_path):
    for i in range(2):
        (tmp_path/f'{i}.md').write_text('---\nname: shared\ndescription: shared\n---\n# Same header\nalpha fact '+str(i),encoding='utf-8')
    assert len(lib.grep_memory(tmp_path,{'alpha'},max_files=6,inject=True))==2

def test_old_fact_survives_more_than_400_new_files(tmp_path):
    old=tmp_path/'old.md';old.write_text('alpha OLD_POLICY',encoding='utf-8');os.utime(old,(1,1))
    for i in range(401):(tmp_path/f'recent{i}.md').write_text(f'unrelated task {i}',encoding='utf-8')
    assert old in lib.grep_memory(tmp_path,{'alpha'},inject=True)

def test_czech_constraints_and_result_remain_complete():
    constraint='Zachovej všechna slova. '+'podmínka '*40+'UNIQUE_FINAL_CONSTRAINT'
    result='Ověřeno 12 testů. Export je v D:/test/result.md.'
    output=lib.build_resume([{'role':'user','kind':'text','text':constraint},{'role':'assistant','kind':'text','text':result}])
    assert constraint in output and result in output

def test_resolved_questions_are_not_labeled_open():
    output=lib.build_resume([{'role':'user','kind':'text','text':'Je hotovo?'},{'role':'assistant','kind':'text','text':'Ano, kontrola je hotová.'}])
    assert 'Open questions' not in output and 'kontrola je hotová' in output

def test_session_checkpoint_has_priority_over_another_chat(tmp_path):
    sessions=tmp_path/'sessions';sessions.mkdir()
    own=sessions/'own.md';own.write_text('Session: own-session\nmy current task',encoding='utf-8');os.utime(own,(1,1))
    other=sessions/'other.md';other.write_text('Session: other-session\nunrelated task',encoding='utf-8')
    assert lib.latest_session_note(tmp_path,'own-session')==own

def test_missing_project_never_inherits_home_memory(tmp_path,monkeypatch):
    projects=tmp_path/'memory-store';projects.mkdir()
    workspace=tmp_path/'workspace';workspace.mkdir();(workspace/'AGENTS.md').write_text('project',encoding='utf-8')
    parent_memory=projects/lib.project_slug_from_cwd(str(tmp_path))/'memory';parent_memory.mkdir(parents=True)
    monkeypatch.setattr(lib,'PROJECTS_ROOT',projects)
    assert lib.find_memory_dir(str(workspace)) is None

def test_git_worktree_resolves_real_repository_memory(tmp_path,monkeypatch):
    projects=tmp_path/'memory-store';projects.mkdir()
    repo=tmp_path/'repo';(repo/'.git/worktrees/wt').mkdir(parents=True)
    worktree=tmp_path/'managed/wt';worktree.mkdir(parents=True)
    (worktree/'.git').write_text('gitdir: '+str(repo/'.git/worktrees/wt'),encoding='utf-8')
    memory=projects/lib.project_slug_from_cwd(str(repo))/'memory';memory.mkdir(parents=True)
    monkeypatch.setattr(lib,'PROJECTS_ROOT',projects)
    assert lib.find_memory_dir(str(worktree))==memory

def test_partial_excerpt_is_explicit_and_inflection_matches(tmp_path):
    p=tmp_path/'long.md';p.write_text('unrelated '*100+'\n\nvideo UNIQUE_VIDEO_RULE\n\n'+'other '*100,encoding='utf-8')
    output=lib.extract_snippet(p,{'videem'},max_chars=100)
    assert 'UNIQUE_VIDEO_RULE' in output and 'PARTIAL' in output

def test_removed_style_functions_cannot_reactivate():
    assert not hasattr(lib,'caveman_session_block')
    assert not hasattr(lib,'write_caveman_flag')
    assert not hasattr(lib,'lean_on')

def test_codex_adapter_preserves_tools_summaries_and_czech_result(tmp_path):
    adapter=load('quality_cp_adapter',Path.home()/'.codex/hooks/megamind_pre_compact.py')
    records=[{'type':'response_item','payload':{'type':'message','role':'assistant','channel':'summary','content':[{'type':'output_text','text':'Earlier accepted constraint UNIQUE_SUMMARY'}]}},
             {'type':'response_item','payload':{'type':'function_call','name':'apply_patch','arguments':'*** Add File: D:/test/result.md\n+hello'}},
             {'type':'response_item','payload':{'type':'message','role':'assistant','channel':'final','content':[{'type':'output_text','text':'Ověřeno 12 testů, soubor uložen.'}]}}]
    p=tmp_path/'transcript.jsonl';p.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in records),encoding='utf-8')
    resume=lib.build_resume(adapter.iter_transcript_blocks(str(p)))
    assert 'UNIQUE_SUMMARY' in resume and 'D:/test/result.md' in resume and '12 testů' in resume

def test_broken_hook_failure_is_visible_without_secret_leak(tmp_path):
    broken=tmp_path/'broken.py';broken.write_text('raise RuntimeError("do not print this private value")',encoding='utf-8')
    result=subprocess.run([sys.executable,str(Path.home()/'.codex/hooks/megamind_hook_adapter.py'),'SessionStart',str(broken)],input='{}',text=True,capture_output=True)
    data=json.loads(result.stdout)
    assert 'failed' in data['hookSpecificOutput']['additionalContext']
    assert result.stderr and 'private value' not in result.stderr+result.stdout

def test_source_filters_still_exclude_image_and_credentials(tmp_path):
    adapter=load('quality_filter',Path.home()/'.codex/hooks/megamind_pre_compact.py')
    text='normal context\npassword=super-private-fixture\ndata:image/png;base64,AAABBB'
    cleaned=adapter._clean_text(text)
    assert 'normal context' in cleaned and 'super-private' not in cleaned and 'data:image' not in cleaned


def test_codex_custom_tools_preserve_source_paths(tmp_path):
    adapter=load('quality_custom',Path.home()/'.codex/hooks/megamind_pre_compact.py')
    p=tmp_path/'custom.jsonl'
    code='text(await tools.exec_command({cmd:"python helper.py",workdir:"D:/Project with spaces"}));'
    p.write_text(json.dumps({'type':'response_item','payload':{'type':'custom_tool_call','name':'functions.exec','input':code}}),encoding='utf-8')
    result=lib.build_resume(adapter.iter_transcript_blocks(str(p)))
    assert 'D:/Project with spaces' in result


def test_superseded_checkpoint_does_not_become_startup_state(tmp_path):
    sessions=tmp_path/'sessions';sessions.mkdir()
    current=sessions/'current.md';current.write_text('# Current\nvalid context',encoding='utf-8');os.utime(current,(1,1))
    closed=sessions/'closed.md';closed.write_text('---\nsuperseded_by: current\n---\n# Closed\nstale instruction',encoding='utf-8')
    assert lib.latest_session_note(tmp_path)==current
