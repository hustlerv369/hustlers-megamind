import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

import megamind_pre_compact as adapter


class TranscriptAdapterTests(unittest.TestCase):
    def parse(self, records, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'transcript.jsonl'
            path.write_text('\n'.join(json.dumps(r) if not isinstance(r, str) else r for r in records), encoding='utf-8')
            return adapter.iter_transcript_blocks(str(path), **kwargs)

    def message(self, role, text, **kwargs):
        return {'type': 'response_item', 'payload': {'type': 'message', 'role': role,
                'content': [{'type': 'input_text' if role == 'user' else 'output_text', 'text': text}], **kwargs}}

    def test_codex_text_and_event_mirror(self):
        rows = self.parse([self.message('user', 'Oprav paměť.'),
                          {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'Oprav paměť.'}},
                          {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': 'Zvolil jsem adaptér.'}}])
        self.assertEqual([r['text'] for r in rows], ['Oprav paměť.', 'Zvolil jsem adaptér.'])

    def test_claude_fallback_text_only(self):
        rows = self.parse([{'message': {'role': 'user', 'content': 'Keep this intent'}},
                           {'message': {'role': 'assistant', 'content': [
                               {'type': 'text', 'text': 'Decision: keep shared hooks'},
                               {'type': 'thinking', 'thinking': 'hidden'},
                               {'type': 'tool_use', 'input': {'command': 'hidden'}},
                               {'type': 'tool_result', 'content': 'hidden'}]}}])
        self.assertEqual(len(rows), 2)
        self.assertNotIn('hidden', str(rows))

    def test_ignores_reasoning_images_tools_and_analysis(self):
        rows = self.parse([
            {'type': 'response_item', 'payload': {'type': 'reasoning', 'summary': 'hidden'}},
            {'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': 'hidden'}},
            self.message('assistant', 'hidden', channel='analysis'),
            self.message('developer', 'hidden'),
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [
                {'type': 'input_image', 'image_url': 'hidden'}, {'type': 'input_text', 'text': 'Describe my image'}]}}])
        self.assertEqual(rows, [{'role': 'user', 'kind': 'text', 'text': 'Describe my image'}])

    def test_malformed_missing_and_bounded(self):
        rows = self.parse(['{bad', 'null', '[]', {'message': []},
                           *[self.message('user', str(i)) for i in range(6)]], limit=3)
        self.assertEqual([r['text'] for r in rows], ['3', '4', '5'])
        self.assertEqual(adapter.iter_transcript_blocks('Z:/missing-transcript.jsonl'), [])

    def test_credentials_are_not_copied(self):
        text = 'Keep intent\nAPI_KEY=synthetic_value\n' + 'sk-' + 'x' * 24
        text += '\n-----BEGIN PRIVATE KEY-----\nsynthetic material\n-----END PRIVATE KEY-----\nKeep decision'
        rows = self.parse([self.message('user', text)])
        self.assertEqual(rows[0]['text'], 'Keep intent\nKeep decision')

    def test_large_prose_record_and_following_message_are_preserved(self):
        with patch.object(adapter, 'MAX_LINE', 250):
            rows = self.parse([self.message('user', 'x' * 300), self.message('user', 'Keep')])
        self.assertEqual([r['text'] for r in rows], ['x' * 300, 'Keep'])

    def test_shared_main_writes_resume_and_always_clears_ledger(self):
        sys.path.insert(0, str(adapter.SHARED_SCRIPTS))
        import lib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = root / 'memory'
            memory.mkdir()
            transcript = root / 'synthetic.jsonl'
            payload = {'cwd': str(root), 'transcript_path': str(transcript),
                       'trigger': 'manual', 'session_id': 'synthetic-integration'}
            with patch.object(lib, 'find_memory_dir', return_value=memory), \
                 patch.object(lib, 'read_hook_input', return_value=payload), \
                 patch.object(lib, 'clear_seen') as clear_seen:
                transcript.write_text(json.dumps(self.message('user', 'Preserve the synthetic integration intent.')), encoding='utf-8')
                adapter.main()
                clear_seen.assert_called_once_with('synthetic-integration')
                notes = list((memory / 'sessions').glob('*.md'))
                self.assertEqual(len(notes), 1)
                self.assertIn('Preserve the synthetic integration intent.', notes[0].read_text(encoding='utf-8'))
                for malformed in ('', '{broken JSON\nnull\n'):
                    clear_seen.reset_mock()
                    transcript.write_text(malformed, encoding='utf-8')
                    adapter.main()
                    clear_seen.assert_called_once_with('synthetic-integration')
                    self.assertEqual(list((memory / 'sessions').glob('*.md')), notes)


if __name__ == '__main__':
    unittest.main()
