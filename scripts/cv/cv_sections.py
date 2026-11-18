"""Public CV activity lists; raw private sheet rows are never accepted."""
import hashlib
import json
import re
import unicodedata

PRESENTATION_TYPES = ('conference', 'seminars', 'policy', 'comments')
PRESENTATION_FILES = tuple('presentations-' + kind + '.tex' for kind in PRESENTATION_TYPES)


def alphabetical(value):
    return ''.join(char for char in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(char)), value.casefold()


def clean_name(value):
    return ' '.join(unicodedata.normalize('NFC', value).split())


def presentations_snapshot(data_dir):
    name = 'Presentations.json'
    manifest = json.loads((data_dir / 'manifest.json').read_text())
    expected = manifest.get('sha256', {}).get(name)
    if not expected:
        raise ValueError('Presentations.json is missing. Update Code.gs and run syncPublicationExport.')
    content = (data_dir / name).read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError('Presentation export checksum mismatch')
    data = json.loads(content)
    if set(data) != {'schema_version', *PRESENTATION_TYPES} or data['schema_version'] != 1:
        raise ValueError('Presentations must contain ONLY the four public place/year lists')
    for kind in PRESENTATION_TYPES:
        if not isinstance(data[kind], list):
            raise ValueError('Invalid presentation list: ' + kind)
        for item in data[kind]:
            if not isinstance(item, dict) or set(item) != {'place', 'years'}:
                raise ValueError('Presentation entries must contain ONLY place and years')
            if not isinstance(item['place'], str) or not item['place'].strip():
                raise ValueError('Missing presentation place')
            if not isinstance(item['years'], list) or not item['years'] or any(
                    type(year) is not int or not 1000 <= year <= 9999 for year in item['years']):
                raise ValueError('Invalid presentation year list')
    return data


def presentations_tex(data, escape):
    outputs, counts = {}, {}
    for kind in PRESENTATION_TYPES:
        grouped = {}
        for item in data[kind]:
            place = clean_name(item['place'])
            entry = grouped.setdefault(place.casefold(), {'place': place, 'years': set()})
            entry['years'].update(item['years'])
        entries = sorted(grouped.values(), key=lambda item: alphabetical(item['place']))
        text = '; '.join(escape(item['place']) + ' (' + ', '.join(map(str, sorted(item['years']))) + ')'
                         for item in entries)
        outputs['presentations-' + kind + '.tex'] = (text + '%\n').encode('utf-8')
        counts['presentation_places_' + kind] = len(entries)
    return outputs, counts


def press_tex(links, escape):
    names = {}
    for link in links:
        if link.get('group', '').strip().casefold() != 'press':
            continue
        name = clean_name(link['label'].strip('[] '))
        if name:
            names.setdefault(name.casefold(), name)
    outlets = sorted(names.values(), key=alphabetical)
    # Preserve the existing CV media section's comma-separated style.
    return {'media-press.tex': (', '.join(escape(name) for name in outlets) + '%\n').encode('utf-8')}, {
        'press_outlets': len(outlets)}
