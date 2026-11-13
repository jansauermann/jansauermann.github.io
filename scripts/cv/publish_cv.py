#!/usr/bin/env python3
"""Publish the generated CV snapshot atomically on its own GitHub branch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def api(method, path, body=None, allow_missing=False):
    repo = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid repository')
    request = Request('https://api.github.com/repos/' + repo + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      method=method, headers={
                          'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                          'Accept': 'application/vnd.github+json',
                          'Content-Type': 'application/json',
                          'X-GitHub-Api-Version': '2022-11-28',
                          'User-Agent': 'CV-publication-sync'})
    try:
        with urlopen(request, timeout=45) as response:
            return json.load(response)
    except HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        raise ValueError(f'GitHub request failed ({error.code}): {method} {path}') from None


def blob_sha(content):
    return hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()


def publish(directory):
    names = {'publications.tex', 'working-papers.tex', 'other-publications.tex',
             'citation-statistics.tex', 'manifest.json'}
    files = {f'cv/{name}': (directory / name).read_bytes() for name in sorted(names)}
    manifest = json.loads(files['cv/manifest.json'])
    if set(manifest['sha256']) != names - {'manifest.json'}:
        raise ValueError('Unexpected generated file list')
    for name, digest in manifest['sha256'].items():
        if hashlib.sha256(files['cv/' + name]).hexdigest() != digest:
            raise ValueError('Generated file checksum mismatch')
    # Do not overwrite a newer Sheet export with output generated from an older one.
    current = api('GET', '/git/ref/heads/publication-data')['object']['sha']
    if current != manifest['publication_revision']:
        raise ValueError('Publication data changed during generation. The next run will retry.')
    head = api('GET', '/git/ref/heads/cv-data', allow_missing=True)
    parent = head['object']['sha'] if head else None
    if parent:
        old = api('GET', '/git/trees/' + parent + '?recursive=1')
        existing = {item['path']: item['sha'] for item in old['tree'] if item['type'] == 'blob'}
        if existing == {name: blob_sha(content) for name, content in files.items()}:
            print('CV export unchanged; no commit needed.')
            return parent
    tree = api('POST', '/git/trees', {'tree': [
        {'path': name, 'mode': '100644', 'type': 'blob', 'content': content.decode('utf-8')}
        for name, content in files.items()]})
    commit = api('POST', '/git/commits', {
        'message': 'Generate CV lists from publication data and citation statistics',
        'tree': tree['sha'], 'parents': [parent] if parent else []})
    if parent:
        api('PATCH', '/git/refs/heads/cv-data', {'sha': commit['sha'], 'force': False})
    else:
        api('POST', '/git/refs', {'ref': 'refs/heads/cv-data', 'sha': commit['sha']})
    print('CV export ready at commit ' + commit['sha'])
    return commit['sha']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    try:
        publish(args.directory)
    except (ValueError, OSError, KeyError) as error:
        sys.exit('CV publication stopped: ' + str(error))
