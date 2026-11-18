"""Gate the one-time export-format transition without replacing the previous CV."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def ready(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    if not all(name in manifest.get('sha256', {}) for name in ('RefereeLists.json', 'Presentations.json')):
        return False
    for name in ('RefereeLists.json', 'Presentations.json'):
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != manifest['sha256'][name]:
            raise ValueError('CV activity export checksum mismatch: ' + name)
    refs = json.loads((directory / 'RefereeLists.json').read_text())
    return 'conference' in refs


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()
    available = ready(args.data_dir)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('ready=' + str(available).lower() + '\n')
    print('Activity export ready.' if available else
          'Waiting for updated Google Apps Script export (Presentations + conference refereeing). Previous CV retained.')
