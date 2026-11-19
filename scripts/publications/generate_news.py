"""Validate News exports and replace only the marked News body in index.qmd."""
from __future__ import annotations
import calendar
import datetime as dt
import json
import re
from pathlib import Path

START = '<!-- NEWS:START -->'
END = '<!-- NEWS:END -->'
FIELDS = {'id', 'date_pub', 'date_closer', 'text'}
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December')


def parse_date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('News: ' + field + ' must be an ISO date (YYYY-MM-DD)')
    try:
        return dt.date.fromisoformat(value)
    except ValueError as error:
        raise ValueError('News: invalid ' + field) from error


def add_months(date, months):
    index = date.year * 12 + date.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return dt.date(year, month, min(date.day, calendar.monthrange(year, month)[1]))


def read_snapshot(content):
    data = json.loads(content)
    if not isinstance(data, dict) or set(data) != {'schema_version', 'items'} or data['schema_version'] != 1:
        raise ValueError('News: unsupported export format')
    if not isinstance(data['items'], list):
        raise ValueError('News: items must be a list')
    seen = set()
    for item in data['items']:
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise ValueError('News: unexpected fields in export')
        if not all(isinstance(value, str) for value in item.values()):
            raise ValueError('News: exported fields must be text')
        key = item['id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', key) or key in seen:
            raise ValueError('News: invalid or duplicate id')
        seen.add(key)
        if not item['text'].strip():
            raise ValueError('News: missing text for ' + key)
        published = parse_date(item['date_pub'], 'date_pub')
        close = parse_date(item['date_closer'], 'date_closer') if item['date_closer'] else add_months(published, 14)
        if close < published:
            raise ValueError('News: date_closer precedes date_pub for ' + key)
    return data['items']


def render(items):
    rows=[]
    for item in items:
        published=parse_date(item['date_pub'],'date_pub')
        closed=parse_date(item['date_closer'],'date_closer') if item['date_closer'] else add_months(published,14)
        rows.append((published,closed,item['id'],item['text'].strip()))
    # Include every entry. The visitor's browser applies the Stockholm date window.
    rows.sort(key=lambda row:row[0],reverse=True)
    blocks=[]
    for published,closed,key,text in rows:
        date=MONTHS[published.month-1]+' '+str(published.day)+', '+str(published.year)
        attrs=('.news-item data-news-id="'+key+'" data-news-pub="'+published.isoformat()
               +'" data-news-close="'+closed.isoformat()+'" hidden="hidden"')
        blocks.append('::: {'+attrs+'}\n\n**'+date+'**: '+text+'\n\n:::')
    script=Path(__file__).with_name('news_visibility.js').read_text(encoding='utf-8')
    controls='```{=html}\n<style>.news-item[hidden] { display: none !important; }</style>\n<script>\n'+script+'\n</script>\n```'
    return '\n\n'.join(blocks+[controls]),len(rows)


def replace_section(source, items):
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError('News: index.qmd must have exactly one NEWS:START/NEWS:END marker pair')
    before, rest = source.split(START, 1)
    _, after = rest.split(END, 1)
    body, shown = render(items)
    return before + START + '\n\n' + body + '\n\n' + END + after, shown
