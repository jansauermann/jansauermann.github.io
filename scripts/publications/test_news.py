import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import generate_news as news
import refresh_publications as refresh


def item(key='news', published='2026-11-19', closed='', text='Some **bold**, *italic*, and [linked](https://example.com) text.'):
    return dict(id=key, date_pub=published, date_closer=closed, text=text)


class NewsTests(unittest.TestCase):
    def test_visibility_inclusive_dates_newest_first_and_markdown_preserved(self):
        items=[item('older','2026-01-01'),item('future','2026-11-20'),
               item('expired','2025-01-01'),item('current',closed='2026-11-19')]
        body,count=news.render(news.read_snapshot(json.dumps({'schema_version':1,'items':items})),dt.date(2026,11,19))
        self.assertEqual(count,2)
        self.assertLess(body.index('November 19, 2026'),body.index('January 1, 2026'))
        self.assertIn('**bold**, *italic*, and [linked](https://example.com)',body)
        self.assertEqual(news.render([items[-1]],dt.date(2026,11,20))[1],0)

    def test_fourteen_calendar_months_clamp_month_end_and_leap_day(self):
        self.assertEqual(news.add_months(dt.date(2025,12,31),14),dt.date(2027,2,28))
        self.assertEqual(news.add_months(dt.date(2022,12,31),14),dt.date(2024,2,29))
        self.assertEqual(news.render([item(published='2025-09-23')],dt.date(2026,11,23))[1],1)
        self.assertEqual(news.render([item(published='2025-09-23')],dt.date(2026,11,24))[1],0)

    def test_only_marked_body_changes(self):
        source='About me\n### News\n'+news.START+'\nOld news\n'+news.END+'\n### Teaching\nKeep this\n'
        result,count=news.replace_section(source,[item()],dt.date(2026,11,19))
        self.assertTrue(result.startswith('About me\n### News\n'+news.START))
        self.assertTrue(result.endswith(news.END+'\n### Teaching\nKeep this\n'))
        self.assertNotIn('Old news',result)
        self.assertEqual(count,1)
        for bad in (source.replace(news.END,''),source+news.START):
            with self.assertRaisesRegex(ValueError,'marker pair'):news.replace_section(bad,[])

    def test_invalid_dates_duplicate_ids_and_unexpected_columns_fail(self):
        for rows in ([item(),item()], [item(published='2026-02-30')], [item(closed='2026-11-18')],
                     [dict(item(),private_notes='do not export')]):
            with self.assertRaises(ValueError):news.read_snapshot(json.dumps({'schema_version':1,'items':rows}))


class NewsRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.site=self.root/'site';self.site.mkdir()
        self.scripts=self.root/'scripts';self.scripts.mkdir();self.data=self.root/'data';self.data.mkdir()
        (self.scripts/'publication-sync.json').write_text(json.dumps({'target':'research.qmd','repository':'example/site','branch':'publication-data'}))
        (self.scripts/'research-template.txt').write_text('{{PUBLICATIONS}}')
        self.original_index='Keep bio\n### News\n'+news.START+'\nManual news\n'+news.END+'\nKeep footer\n'
        (self.site/'index.qmd').write_text(self.original_index);(self.site/'research.qmd').write_text('Old research')
        import csv,io
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(refresh.PUB_FIELDS)
        pub={'id':'paper','category':'journal_article','entry_type':'article','authors':'Sauermann, Jan','title':'Paper','year':'2026'}
        writer.writerow([pub.get(field,'') for field in refresh.PUB_FIELDS]);(self.data/'Pubs.csv').write_text(stream.getvalue())
        (self.data/'Pubs_CustomLinks.csv').write_text('publication_id,group,label,url\n')
        self.save_manifest()
        self.addCleanup(patch.stopall)
        patch.object(refresh,'__file__',str(self.scripts/'refresh_publications.py')).start()
        patch.object(news,'today_stockholm',return_value=dt.date(2026,11,19)).start()

    def save_manifest(self,rows=None):
        if rows is not None:(self.data/'News.json').write_text(json.dumps({'schema_version':1,'items':rows}))
        files=[p for p in self.data.iterdir() if p.name!='manifest.json']
        (self.data/'manifest.json').write_text(json.dumps({'schema_version':1,'publications':1,'links':0,
            'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}))

    def test_transition_preserves_news_then_updates_and_backs_up(self):
        refresh.update(self.site,self.data)
        self.assertEqual((self.site/'index.qmd').read_text(),self.original_index)
        self.save_manifest([item()]);state=refresh.update(self.site,self.data)
        self.assertTrue(state['news_enabled']);self.assertEqual(state['news_shown'],1)
        self.assertIn('**November 19, 2026**:',(self.site/'index.qmd').read_text())
        backups=list((self.site/'.publication-backups').glob('index-*.qmd'))
        self.assertEqual(backups[0].read_text(),self.original_index)
        refresh.update(self.site,self.data)
        self.assertEqual(list((self.site/'.publication-backups').glob('index-*.qmd')),backups)
        (self.data/'News.json').unlink();self.save_manifest()
        with self.assertRaisesRegex(ValueError,'missing'):refresh.update(self.site,self.data)

    def test_bad_news_snapshot_changes_neither_page(self):
        self.save_manifest([item(published='2026-02-30')])
        with self.assertRaises(ValueError):refresh.update(self.site,self.data)
        self.assertEqual((self.site/'index.qmd').read_text(),self.original_index)
        self.assertEqual((self.site/'research.qmd').read_text(),'Old research')
        self.save_manifest([item()]);(self.data/'News.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'integrity'):refresh.update(self.site,self.data)
        self.assertEqual((self.site/'research.qmd').read_text(),'Old research')


if __name__=='__main__':unittest.main()
