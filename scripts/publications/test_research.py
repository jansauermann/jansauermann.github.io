import unittest
import generate_research as research


class PublicationDisplayTests(unittest.TestCase):
    def setUp(self):
        self.pub = {'id': 'paper', 'category': 'journal_article', 'entry_type': 'article',
                    'title': 'Test paper', 'authors': 'Sauermann, Jan', 'year': '2026'}

    def link(self, label, group='More information', url=None):
        return {'publication_id': 'paper', 'group': group, 'label': label,
                'url': url if url is not None else 'https://example.com/' + str(len(label))}

    def test_link_order_and_text_notes_survive(self):
        links = [self.link('Outlet', 'Press'), self.link('preprint'), self.link('Summary', 'Non-technical summary'),
                 self.link('online appendix'), self.link('publisher version (open access)'),
                 self.link('previously released as IZA DP 123', url='')]
        html = research.additional_info(self.pub, links)
        labels = ['publisher version (open access)', 'online appendix', 'preprint',
                  'previously released as IZA DP 123', 'non-technical summary', 'Press:']
        self.assertEqual(sorted(labels, key=html.index), labels)
        self.assertEqual(html.count('<p>'), 2)
        self.assertIn('>[non-technical summary]</a>', html)
        self.assertNotIn('Non-technical summary:', html)
        self.assertIn('<span class="pub-note">[previously released as IZA DP 123]</span>', html)

    def test_one_link_techreport_has_direct_link_and_separate_abstract_and_bibtex(self):
        pub = dict(self.pub, category='other', entry_type='techreport', abstract='An abstract')
        qmd, _, _ = research.generate([pub], [self.link('download')], '{{PUBLICATIONS}}')
        self.assertIn('class="pub-direct-link"', qmd)
        self.assertIn('Download</a>', qmd)
        self.assertNotIn('id="moreinfo-paper"', qmd)
        self.assertIn('id="abstract-paper"', qmd)
        self.assertIn('id="bibtex-paper"', qmd)
        self.assertLess(qmd.index('class="pub-direct-link"'), qmd.index('aria-controls="abstract-paper"'))
        self.assertLess(qmd.index('aria-controls="abstract-paper"'), qmd.index('aria-controls="bibtex-paper"'))
        self.assertIn('<p>Sauermann, Jan (2026), <em>Test paper</em>', qmd)

    def test_multiple_links_keep_more_information_and_empty_abstract_is_omitted(self):
        pub = dict(self.pub, category='other', entry_type='techreport', abstract='  ')
        qmd, _, _ = research.generate([pub], [self.link('download'), self.link('online appendix')], '{{PUBLICATIONS}}')
        self.assertIn('id="moreinfo-paper"', qmd)
        self.assertNotIn('id="abstract-paper"', qmd)
        self.assertIn('id="bibtex-paper"', qmd)

    def test_main_url_supplements_all_other_entry_types_without_duplicates(self):
        for kind in ['misc', 'article', 'techreport']:
            pub = dict(self.pub, category='other', entry_type=kind, main_url='https://example.com/main')
            custom = [self.link('online appendix', url='https://example.com/appendix')]
            combined = research.website_links(pub, custom)
            self.assertEqual([link['url'] for link in combined], [pub['main_url'], custom[0]['url']])
            qmd, _, _ = research.generate([pub], custom, '{{PUBLICATIONS}}')
            self.assertIn('id="moreinfo-paper"', qmd)
            self.assertIn('href="https://example.com/main"', qmd)
            self.assertIn('href="https://example.com/appendix"', qmd)
            self.assertEqual(len(research.website_links(pub, combined)), 2)

    def test_main_url_only_report_has_download_and_journal_uses_customlinks(self):
        pub = dict(self.pub, category='other', entry_type='misc', main_url='https://example.com/main')
        qmd, _, _ = research.generate([pub], [], '{{PUBLICATIONS}}')
        self.assertIn('href="https://example.com/main"', qmd)
        self.assertIn('Download</a>', qmd)
        self.assertNotIn('id="moreinfo-paper"', qmd)
        self.assertEqual(research.website_links(dict(pub, category='journal_article'), []), [])

    def test_no_wp_or_wip_bibtex_and_nonresearch_report_has_none(self):
        for category, entry_type in [('working_paper', 'unpublished'), ('work_in_progress', 'unpublished'),
                                     ('other', 'misc')]:
            pub = dict(self.pub, category=category, entry_type=entry_type)
            qmd, _, _ = research.generate([pub], [self.link('download')], '{{PUBLICATIONS}}')
            self.assertNotIn('id="bibtex-paper"', qmd)


if __name__ == '__main__':
    unittest.main()
