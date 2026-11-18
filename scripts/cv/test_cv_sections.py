import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import cv_sections as sections
import check_inputs
from generate_cv import tex


class ActivityTests(unittest.TestCase):
    def test_old_export_waits_and_valid_new_export_is_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'manifest.json').write_text('{"sha256": {}}')
            self.assertFalse(check_inputs.ready(folder))
            files = {'RefereeLists.json': b'{"conference": []}', 'Presentations.json': b'{}'}
            for name, content in files.items():
                (folder / name).write_bytes(content)
            (folder / 'manifest.json').write_text(json.dumps({'sha256': {
                name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}))
            self.assertTrue(check_inputs.ready(folder))
            (folder / 'Presentations.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                check_inputs.ready(folder)

    def test_places_combine_years_sort_and_deduplicate(self):
        data = {kind: [] for kind in sections.PRESENTATION_TYPES}
        data['seminars'] = [
            {'place': ' Uppsala   University ', 'years': [2025, 2023]},
            {'place': 'uppsala university', 'years': [2023, 2024]},
            {'place': 'A & B Institute', 'years': [2026]}]
        data['comments'] = [{'place': 'Comment workshop', 'years': [2027]}]
        outputs, counts = sections.presentations_tex(data, tex)
        self.assertEqual(outputs['presentations-seminars.tex'],
                         b'A \\& B Institute (2026); Uppsala University (2023, 2024, 2025)%\n')
        self.assertEqual(outputs['presentations-comments.tex'], b'Comment workshop (2027)%\n')
        self.assertEqual(counts['presentation_places_seminars'], 2)
        self.assertNotIn(b'publication_id', b''.join(outputs.values()))

    def test_press_only_and_labels_without_url_are_retained(self):
        links = [
            {'group': 'Press', 'label': 'The Economist', 'url': ''},
            {'group': 'Press', 'label': 'the economist', 'url': 'https://example.com'},
            {'group': 'Press', 'label': 'Arbetet', 'url': ''},
            {'group': 'Non-technical summary', 'label': 'Excluded blog', 'url': ''},
            {'group': 'More information', 'label': 'Excluded version', 'url': ''}]
        outputs, counts = sections.press_tex(links, tex)
        self.assertEqual(outputs['media-press.tex'], b'Arbetet, The Economist%\n')
        self.assertEqual(counts['press_outlets'], 2)

    def test_presentation_schema_rejects_raw_dates_ids_and_private_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            data = {'schema_version': 1, **{kind: [] for kind in sections.PRESENTATION_TYPES}}
            def save():
                content = json.dumps(data).encode()
                (folder / 'Presentations.json').write_bytes(content)
                (folder / 'manifest.json').write_text(json.dumps({'sha256': {
                    'Presentations.json': hashlib.sha256(content).hexdigest()}}))
            save()
            self.assertEqual(sections.presentations_snapshot(folder), data)
            data['comments'] = [{'place': 'A place', 'years': [2026], 'date': '2026-10-02'}]
            save()
            with self.assertRaisesRegex(ValueError, 'ONLY place and years'):
                sections.presentations_snapshot(folder)
            data['comments'] = [{'place': 'A place', 'years': [True]}]
            save()
            with self.assertRaisesRegex(ValueError, 'Invalid presentation year'):
                sections.presentations_snapshot(folder)


if __name__ == '__main__':
    unittest.main()
