#!/usr/bin/env python3
"""Generate CV LaTeX lists from a validated public publication snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urljoin

# Reuse the website's CSV validation, author formatting and metadata rules.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'publications'))
import generate_research as publications

LISTS = {
    'journal_article': ('publications.tex', 'journalblock', 'journalcounter'),
    'working_paper': ('working-papers.tex', 'wpblock', 'wpcounter'),
    'other': ('other-publications.tex', 'repblock', 'repcounter'),
}
PUBLIC_CATEGORIES = set(LISTS) | {'work_in_progress'}
FILES = tuple(item[0] for item in LISTS.values()) + ('citation-statistics.tex',)
WEBSITE = 'https://jansauermann.github.io/'


def tex(value):
    # Keep ordinary UTF-8 accents; translate punctuation unsupported by pdfLaTeX.
    value = value.translate(str.maketrans({'–': '--', '—': '---', '’': "'", '‘': '`',
                                         '“': '``', '”': "''", '\u00a0': ' ',
                                         '−': '-', '\u202f': ' ', '\u200b': ''}))
    return publications.latex(value).replace('\n', ' ').replace('\r', ' ')


def title_link(pub, links):
    # Ignore press links and metadata URLs. A request-by-email is not a paper URL.
    candidates = [link for link in links if link.get('url') and
                  link.get('group', '').casefold() in {'more information', ''}]
    primary = candidates[0] if candidates else None
    if pub['category'] == 'journal_article':
        primary = next((link for link in candidates if
                        link['label'].casefold().startswith('publisher version')), primary)
    title = r'\textbf{' + tex(pub['title']) + '}'
    if not primary or primary['url'].startswith('mailto:'):
        return title
    url = primary['url']
    if url.endswith('?via%3Dihub'):
        url = url.split('?', 1)[0]
    publications.safe_url(url)
    url = urljoin(WEBSITE, url)
    if not url.startswith(('https://', 'http://')):
        raise ValueError('Unsupported CV link: ' + url)
    url = quote(url, safe=':/?&=#%+-._~@!$,;()*[]')
    return r'\href{' + publications.latex(url) + '}{' + title + '}'


def details(pub):
    get = lambda key: pub.get(key, '')
    parts = []
    if get('journal'):
        journal = r'\emph{' + tex(get('journal')) + '}'
        if pub['category'] == 'journal_article':
            journal = r'\textbf{' + journal + '}'
        parts.append(journal)
        volume = tex(get('volume'))
        if get('issue'):
            if volume:
                volume += '(' + tex(get('issue')) + ')'
            elif get('journal') == 'Wirtschaft im Wandel':
                volume = tex(get('issue') + '/' + get('year'))
            else:
                volume = tex(get('issue'))
        elif get('month'):
            volume += ' (' + tex(get('month')) + ')'
        if volume.strip():
            parts.append(volume.strip())
        if get('pages'):
            parts.append(r'pp.\ ' + tex(get('pages')))
        elif get('article_number'):
            parts.append(tex(get('article_number')))
        if pub['category'] == 'other':
            parts.extend(tex(get(key)) for key in ('institution', 'publisher', 'address') if get(key))
    else:
        if get('entry_type') == 'phdthesis':
            parts.append('PhD thesis')
        if get('booktitle'):
            parts.append(r'in: \emph{' + tex(get('booktitle')) + '}')
        series = ' '.join(value for value in (get('series'), get('number')) if value)
        if series:
            parts.append(tex(series))
        institution = get('institution')
        if institution and institution.casefold() not in series.casefold():
            parts.append(tex(institution))
        if get('publisher') and get('publisher') != institution:
            parts.append(tex(get('publisher')))
        if get('address'):
            parts.append(tex(get('address')))
        if get('pages'):
            parts.append(r'pp.\ ' + tex(get('pages')))
        elif get('article_number'):
            parts.append(tex(get('article_number')))
        if get('month'):
            parts.append(tex(get('month')))
    if get('publication_details'):
        parts.append(tex(get('publication_details')))
    return ', '.join(parts)


def count_value(content, name):
    text = content.strip()
    if re.fullmatch(r'%\s*no citations', text, re.I):
        return 0
    match = re.fullmatch(r'(?:\d+|\(\s*\d+\s+citations?\s*\))', text)
    if not match:
        raise ValueError('Invalid citation statistic: ' + name)
    return int(re.search(r'\d+', text)[0])


def read_count(directory, filename):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.txt', filename):
        raise ValueError('Invalid citation filename')
    return count_value((directory / filename).read_text(encoding='utf-8'), filename)


def snapshot(data_dir):
    manifest = json.loads((data_dir / 'manifest.json').read_text())
    if manifest.get('schema_version') != 1:
        raise ValueError('Unsupported publication schema')
    for name in ('Pubs.csv', 'Pubs_CustomLinks.csv'):
        if hashlib.sha256((data_dir / name).read_bytes()).hexdigest() != manifest['sha256'][name]:
            raise ValueError('Publication export checksum mismatch: ' + name)
    pubs = publications.read_table(data_dir / 'Pubs.csv', {'id', 'category', 'authors', 'title'})
    links = publications.read_table(data_dir / 'Pubs_CustomLinks.csv',
                                    {'publication_id', 'group', 'label', 'url'})
    publications.validate(pubs, links)
    if len(pubs) != manifest['publications'] or len(links) != manifest['links']:
        raise ValueError('Publication export row count mismatch')
    if any(pub['category'] not in PUBLIC_CATEGORIES for pub in pubs):
        raise ValueError('Private or unknown category in public export')
    return pubs, links


def generate(pubs, links, citations_dir):
    publications.validate(pubs, links)
    link_map = {pub['id']: [] for pub in pubs}
    for link in links:
        link_map[link['publication_id']].append(link)
    outputs = {}
    counts = {}
    for category, (filename, macro, counter) in LISTS.items():
        selected = sorted((pub for pub in pubs if pub['category'] == category),
                          key=lambda pub: -int(pub.get('year') or 0))
        counts[category] = len(selected)
        lines = ['% Generated from Google Sheets. Edit the sheet, not this file.',
                 r'\setcounter{' + counter + 'D}{' + str(len(selected) + 1) + '}',
                 r'\setcounter{' + counter + '}{0}', '']
        for pub in selected:
            own_links = link_map[pub['id']]
            citation = tex(publications.author_display(pub))
            if category != 'working_paper' and pub.get('year'):
                citation += ' (' + tex(pub['year']) + ')'
            citation += ', ' + title_link(pub, own_links)
            suffix = details(pub)
            if suffix:
                citation += ', ' + suffix
            # Preserve working-paper status and previous-version notes, but not press lists.
            if category == 'working_paper':
                notes = [link['label'].strip('[] ') for link in own_links if
                         not link.get('url') and
                         link.get('group', '').casefold() in {'', 'more information'}]
                for note in dict.fromkeys(notes):
                    if note and note.casefold() not in pub.get('publication_details', '').casefold():
                        citation += '. ' + tex(note)
            count = 0
            if category == 'journal_article' and pub.get('scopus_file'):
                count = read_count(citations_dir, pub['scopus_file'].split('/')[-1])
            ending = '' if citation.endswith(('.', '!', '?')) else '.'
            if count:
                # Exactly one font word-space: no sentence spacing or justification stretch.
                if citation.endswith('.'):
                    citation = citation[:-1]
                    ending = '.'
                noun = 'citation' if count == 1 else 'citations'
                citation += (r'\ifshowcitations\hspace{\fontdimen2\font}('
                             + str(count) + ' ' + noun + r')\else' + ending + r'\fi')
            else:
                citation += ending
            lines += ['% publication-id: ' + pub['id'], '\\' + macro + '{' + citation + '}', '']
        outputs[filename] = '\n'.join(lines).encode('utf-8')
    totals = {
        'scopus_total': read_count(citations_dir, 'TotalCitations_raw.txt'),
        'scholar_h_index': read_count(citations_dir, 'GoogleScholarHIndex_raw.txt'),
    }
    outputs['citation-statistics.tex'] = (
        '% Generated citation statistics for the CV header.\n'
        + r'\newcommand{\cvtotalcitations}{\ifshowcitations ' + str(totals['scopus_total']) + '\\fi}\n'
        + r'\newcommand{\cvscholarhindex}{\ifshowcitations ' + str(totals['scholar_h_index']) + '\\fi}\n'
    ).encode('utf-8')
    return outputs, counts, totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--citations-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--publication-revision', required=True)
    parser.add_argument('--citations-tree', required=True)
    args = parser.parse_args()
    for revision in (args.publication_revision, args.citations_tree):
        if not re.fullmatch(r'[0-9a-f]{40}', revision):
            raise ValueError('Invalid source revision')
    pubs, links = snapshot(args.data_dir)
    outputs, counts, totals = generate(pubs, links, args.citations_dir)
    manifest = {'schema_version': 1,
                'publication_revision': args.publication_revision,
                'citations_tree': args.citations_tree,
                'counts': counts, 'statistics': totals,
                'sha256': {name: hashlib.sha256(content).hexdigest() for name, content in outputs.items()}}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (args.output / name).write_bytes(content)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Generated CV lists: ' + ', '.join(f'{key}: {value}' for key, value in counts.items()))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        sys.exit('CV generation stopped: ' + str(error))
