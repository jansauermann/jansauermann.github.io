"""Behavioral checks for CV generation and atomic GitHub publication."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generate_cv as cv
import publish_cv


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / 'TotalCitations_raw.txt').write_text('100')
        (self.directory / 'GoogleScholarHIndex_raw.txt').write_text('12')
        self.pub = {'id': 'paper', 'category': 'journal_article', 'entry_type': 'article',
                    'authors': 'Alpha, Ada; Sauermann, Jan', 'title': 'Skills & training_2: 50%',
                    'year': '2025', 'journal': 'Journal & Review', 'volume': '12',
                    'issue': '3', 'pages': '1–20', 'scopus_file': 'citations/paper.txt'}

    def render(self, pubs=None, links=None):
        return cv.generate(pubs or [self.pub], links or [], self.directory)[0]

    def test_citations_are_inside_blocks_zero_hidden_and_switch_retained(self):
        (self.directory / 'paper.txt').write_text('% no citations\n')
        output = self.render()['publications.tex'].decode()
        self.assertNotIn(r'\ifshowcitations', output)
        self.assertIn(r'pp.\ 1--20.}', output)
        (self.directory / 'paper.txt').write_text(' (1 citation)\n')
        output = self.render()['publications.tex'].decode()
        self.assertIn(r'pp.\ 1--20\ifshowcitations\hspace{\fontdimen2\font}(1 citation)\else.\fi}', output)
        self.assertNotIn(r'. \ifshowcitations', output)
        self.assertIn(r'\setcounter{journalcounterD}{2}', output)
        self.assertIn(r'\&', output)
        self.assertIn(r'\_', output)
        self.assertIn(r'\%', output)

    def test_order_ties_and_exclusion(self):
        pubs = [dict(self.pub, id='old', year='2020', scopus_file=''),
                dict(self.pub, id='newA', year='2025', scopus_file=''),
                dict(self.pub, id='newB', year='2025', scopus_file=''),
                dict(self.pub, id='hidden', category='work_in_progress', scopus_file='')]
        output = self.render(pubs)['publications.tex'].decode()
        self.assertLess(output.index('newA'), output.index('newB'))
        self.assertLess(output.index('newB'), output.index('old'))
        self.assertNotIn('hidden', ''.join(value.decode() for value in self.render(pubs).values()))
        self.assertNotIn(r'\sectionheader', output)
        self.assertIn(r'\setcounter{journalcounterD}{4}', output)

    def test_relative_links_become_public_and_press_is_not_used_for_wp_title(self):
        pub = dict(self.pub, category='working_paper', scopus_file='')
        links = [{'publication_id': 'paper', 'group': 'More information', 'label': 'download',
                  'url': 'files/My_paper.pdf'}]
        output = self.render([pub], links)['working-papers.tex'].decode()
        self.assertIn(r'https://jansauermann.github.io/files/My\_paper.pdf', output)
        self.assertNotIn('(2025)', output)
        links[0]['url'] = 'mailto:jan@example.com'
        links.append(dict(links[0], label='Press', url='https://example.com/press'))
        self.assertNotIn(r'\href', self.render([pub], links)['working-papers.tex'].decode())

    def test_bad_or_missing_counts_fail_instead_of_publishing_false_zero(self):
        for content in ('Error fetching count: 404', '<html>500</html>', '-1'):
            (self.directory / 'paper.txt').write_text(content)
            with self.assertRaises(ValueError):
                self.render()
        (self.directory / 'paper.txt').unlink()
        with self.assertRaises(FileNotFoundError):
            self.render()

    def test_snapshot_tampering_detected(self):
        for name in ('Pubs.csv', 'Pubs_CustomLinks.csv'):
            (self.directory / name).write_text('wrong')
        (self.directory / 'manifest.json').write_text(json.dumps({
            'schema_version': 1, 'sha256': {'Pubs.csv': '0' * 64, 'Pubs_CustomLinks.csv': '0' * 64}}))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            cv.snapshot(self.directory)


class PublishTests(unittest.TestCase):
    def test_complete_snapshot_one_commit_no_force_and_repeat_is_noop(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            files = {name: b'% a complete generated file\n' for name in cv.FILES}
            manifest = {'publication_revision': 'a' * 40,
                        'sha256': {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}}
            files['manifest.json'] = (json.dumps(manifest) + '\n').encode()
            for name, content in files.items():
                (directory / name).write_bytes(content)
            calls = []
            exists = False

            def api(method, path, body=None, **kwargs):
                calls.append((method, path, body))
                if path.endswith('/publication-data'):
                    return {'object': {'sha': 'a' * 40}}
                if path == '/git/ref/heads/cv-data':
                    return {'object': {'sha': 'b' * 40}} if exists else None
                if method == 'GET' and path.startswith('/git/trees/'):
                    return {'tree': [{'path': 'cv/' + name, 'type': 'blob', 'sha': publish_cv.blob_sha(content)}
                                     for name, content in files.items()]}
                if path == '/git/trees':
                    self.assertEqual({item['path'] for item in body['tree']}, {'cv/' + name for name in files})
                    return {'sha': 'c' * 40}
                if path == '/git/commits':
                    return {'sha': 'b' * 40}
                if path == '/git/refs':
                    self.assertEqual(body['ref'], 'refs/heads/cv-data')
                    return {}
                self.fail('Unexpected API operation')

            with patch.object(publish_cv, 'api', side_effect=api):
                publish_cv.publish(directory)
                self.assertEqual(sum(method == 'POST' and path == '/git/commits' for method, path, _ in calls), 1)
                exists = True
                calls.clear()
                publish_cv.publish(directory)
                self.assertTrue(all(method == 'GET' for method, _, _ in calls))


if __name__ == '__main__':
    unittest.main()
