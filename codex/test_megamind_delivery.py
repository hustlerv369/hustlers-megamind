from pathlib import Path
import hashlib
import json
import tempfile
import unittest

import megamind_delivery as delivery


class DeliveryTests(unittest.TestCase):
    def test_small_delivery_is_complete_and_byte_identical_on_windows(self):
        text='Žluťoučký kůň 🔥\nFULL_END\n'
        with tempfile.TemporaryDirectory() as directory:
            output, status=delivery.prepare_delivery(text,'SessionStart',Path(directory))
            path=next(Path(directory).glob('*.txt'))
            self.assertEqual(status,'inline')
            self.assertIn(text,output)
            self.assertEqual(path.read_bytes(),text.encode('utf-8'))
            self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(),output)

    def test_large_delivery_not_sent_as_silent_partial_memory(self):
        text='Zachovej celý význam a kameru. 🔥\n'*12000+'SOURCE_END'
        with tempfile.TemporaryDirectory() as directory:
            output,status=delivery.prepare_delivery(text,'UserPromptSubmit',Path(directory))
            self.assertEqual(status,'recovery_required')
            self.assertLessEqual(len(output.encode('utf-8')),delivery.FRAME_BYTES)
            self.assertIn('NOT yet loaded',output)
            self.assertNotIn('SOURCE_END',output)
            path=next(Path(directory).glob('*.txt'))
            self.assertEqual(path.read_bytes(),text.encode('utf-8'))

    def test_every_unicode_character_and_repeated_instruction_recovered(self):
        text=('Ponech řeč. 🔥\nPause\nPonech řeč. 🔥\n"quoted" \\ path\n'*700)+'FINÁL'
        digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
        parts=[];offset=0
        while True:
            page=delivery.content_page(text,digest,offset)
            self.assertLessEqual(len(delivery.encoded(page)),delivery.FRAME_BYTES)
            self.assertEqual(page['offset'],offset)
            self.assertEqual(page['page_sha256'],hashlib.sha256(page['content'].encode('utf-8')).hexdigest())
            parts.append(page['content'])
            self.assertFalse(page['entire_source_in_this_page'])
            if page['next_offset'] is None:
                self.assertTrue(page['reached_source_end']);break
            self.assertGreater(page['next_offset'],offset)
            offset=page['next_offset']
        self.assertEqual(''.join(parts),text)

    def test_source_pagination_keeps_all_sources(self):
        text='preamble\n'+''.join(f'## Historical memory source: C:/project/{i}.md\nFACT_{i}\n' for i in range(170))
        result=[];cursor=0
        while True:
            page=delivery.source_page(text,'fixture',cursor)
            self.assertLessEqual(len(delivery.encoded(page)),delivery.FRAME_BYTES)
            result.extend(page['sources'])
            if page['next_source'] is None:break
            self.assertGreater(page['next_source'],cursor)
            cursor=page['next_source']
        self.assertEqual(result,delivery.sections(text))
        self.assertEqual(len(result),171)

    def test_find_locates_late_correction_and_reads_it_whole(self):
        correction='aktuální oprava: transparentní logo, kamera, scroll\n'*200
        text='## Historical memory source: C:/old.md\n'+'history\n'*3000+'## Historical memory source: C:/new-correction.md\n'+correction
        found=delivery.source_page(text,'fixture',needle='new-correction')
        source_id=found['sources'][0]['source_id']
        parts=[];offset=None
        while True:
            page=delivery.content_page(text,'fixture',offset,source_id)
            parts.append(page['content'])
            offset=page['next_offset']
            if offset is None:break
        self.assertTrue(''.join(parts).endswith(correction))
        self.assertNotIn('history',''.join(parts))

    def test_last_page_does_not_claim_whole_source_read(self):
        text='history '*10000+'END'
        page=delivery.content_page(text,'fixture',len(text)-3)
        self.assertTrue(page['reached_source_end'])
        self.assertFalse(page['entire_source_in_this_page'])

    def test_artifact_revision_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'test.txt';path.write_bytes(b'first')
            digest=hashlib.sha256(b'first').hexdigest()
            self.assertEqual(delivery.load_artifact(path,digest,root),'first')
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
                delivery.load_artifact(path,digest,root)

    def test_reader_rejects_path_outside_delivery_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'secret.txt';path.write_bytes(b'private')
            with self.assertRaisesRegex(ValueError,'approved artifact directory'):
                delivery.load_artifact(path,hashlib.sha256(b'private').hexdigest(),root/'deliveries')

    def test_failed_archive_does_not_claim_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            obstacle=Path(directory)/'file';obstacle.write_text('occupied')
            output,status=delivery.prepare_delivery('private fixture','SessionStart',obstacle/'child')
            self.assertEqual(status,'failed')
            self.assertIn('NOT loaded',output)
            self.assertNotIn('private fixture',output)

    def test_invalid_offsets_and_source_ids_refused(self):
        for offset,source_id in [(-1,None),(99,None),(None,9)]:
            with self.assertRaises(ValueError):
                delivery.content_page('test','fixture',offset,source_id)


if __name__=='__main__':
    unittest.main()
