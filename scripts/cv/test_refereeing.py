import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import generate_cv as cv


class RefereeingTests(unittest.TestCase):
    def test_two_alphabetical_unique_lists_escape_tex_and_have_no_headers(self):
        outputs, counts = cv.refereeing_tex({'journals': [
            'Zeitschrift', ' Alpha   Economics ', 'alpha economics', 'Économie & Policy'],
            'funding': ['Z Fund', 'A & B Foundation', 'A & B Foundation']})
        self.assertEqual(outputs['refereeing-journals.tex'].decode(),
                         'Alpha Economics; Économie \\& Policy; Zeitschrift%\n')
        self.assertEqual(outputs['refereeing-funding.tex'].decode(),
                         'A \\& B Foundation; Z Fund%\n')
        self.assertEqual(counts, {'refereeing_journals': 3, 'refereeing_funding': 2})
        self.assertNotIn(b'\\other', outputs['refereeing-journals.tex'])

    def test_only_aggregate_schema_accepted_with_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            def save(data):
                content = json.dumps(data).encode()
                (folder / 'RefereeLists.json').write_bytes(content)
                (folder / 'manifest.json').write_text(json.dumps({'sha256': {
                    'RefereeLists.json': hashlib.sha256(content).hexdigest()}}))
            valid = {'schema_version': 1, 'journals': ['Journal A'], 'funding': []}
            save(valid)
            self.assertEqual(cv.refereeing_snapshot(folder), valid)
            save(dict(valid, Notes=['PRIVATE']))
            with self.assertRaisesRegex(ValueError, 'ONLY'):
                cv.refereeing_snapshot(folder)
            save(valid)
            (folder / 'RefereeLists.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                cv.refereeing_snapshot(folder)
            (folder / 'manifest.json').write_text('{"sha256": {}}')
            with self.assertRaisesRegex(ValueError, 'Update Code.gs'):
                cv.refereeing_snapshot(folder)

    def test_empty_lists_produce_no_names_or_placeholders(self):
        outputs, counts = cv.refereeing_tex({'journals': [], 'funding': []})
        self.assertEqual(set(outputs.values()), {b'%\n'})
        self.assertEqual(sum(counts.values()), 0)


if __name__ == '__main__':
    unittest.main()
