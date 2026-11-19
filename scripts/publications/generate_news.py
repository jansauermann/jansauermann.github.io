"""Validate News exports and replace only the marked News body in index.qmd."""
from __future__ import annotations
import calendar
import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

START = '<!-- NEWS:START -->'
END = '<!-- NEWS:END -->'
FIELDS = {'id', 'date_pub', 'date_closer', 'text'}
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December')


def today_stockholm():
    return dt.datetime.now(ZoneInfo('Europe/Stockholm')).date()


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


def render(items, today=None):
    today = today if today is not None else today_stockholm()
    rows = []
    for item in items:
        published = parse_date(item['date_pub'], 'date_pub')
        close = parse_date(item['date_closer'], 'date_closer') if item['date_closer'] else add_months(published, 14)
        if published <= today <= close:
            rows.append((published, item['text'].strip()))
    # A stable sort preserves sheet order for items with the same publication date.
    rows.sort(key=lambda row: row[0], reverse=True)
    body = '\n\n'.join('**' + MONTHS[date.month - 1] + ' ' + str(date.day) + ', ' + str(date.year) + '**: ' + text
                       for date, text in rows)
    return body, len(rows)


def replace_section(source, items, today=None):
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError('News: index.qmd must have exactly one NEWS:START/NEWS:END marker pair')
    before, rest = source.split(START, 1)
    _, after = rest.split(END, 1)
    body, shown = render(items, today)
    return before + START + '\n\n' + body + '\n\n' + END + after, shown
