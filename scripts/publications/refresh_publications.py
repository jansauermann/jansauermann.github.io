#!/usr/bin/env python3
"""Read the public GitHub snapshot, validate it, and regenerate the configured QMD."""
from __future__ import annotations
import argparse
import csv
import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import generate_research as generator

PUB_FIELDS=['id','category','entry_type','authors','title','year','journal','volume','issue','pages',
            'article_number','month','doi','issn','keywords','series','number','booktitle','institution',
            'publisher','address','publication_details','abstract','scopus_file']
LINK_FIELDS=['publication_id','group','label','url']


def download(url):
    result=subprocess.run(['/usr/bin/curl','--fail','--silent','--show-error','--location',
                           '--proto','=https','--proto-redir','=https','--connect-timeout','10',
                           '--max-time','30','--retry','1','--retry-max-time','45',
                           '--header','User-Agent: PublicationSync',url],capture_output=True)
    if result.returncode:
        raise ValueError('Cannot download the publication export. Check your internet connection and the first Apps Script export. '+result.stderr.decode(errors='replace').strip())
    return result.stdout


def atomic_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    handle,temp=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name+'.')
    try:
        with os.fdopen(handle,'wb') as stream:stream.write(data)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def update(site,fixture=None):
    scripts=Path(__file__).resolve().parent
    config=json.loads((scripts/'publication-sync.json').read_text())
    target=config['target']
    if target not in {'research2.qmd','research.qmd'}:raise ValueError('target must be research2.qmd or research.qmd')
    repo=config['repository'];branch=config['branch']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid repository')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',branch):raise ValueError('Invalid branch')
    names=('Pubs.csv','Pubs_CustomLinks.csv','manifest.json')
    if fixture:
        files={name:(fixture/name).read_bytes() for name in names};revision='local test'
    else:
        ref=json.loads(download(f'https://api.github.com/repos/{repo}/git/ref/heads/{branch}'))
        revision=ref['object']['sha']
        if not re.fullmatch(r'[0-9a-f]{40}',revision):raise ValueError('Invalid data revision from GitHub')
        files={name:download(f'https://raw.githubusercontent.com/{repo}/{revision}/data/{name}') for name in names}
    manifest=json.loads(files['manifest.json'])
    if manifest.get('schema_version')!=1:raise ValueError('Unsupported publication export schema')
    for name,fields in [('Pubs.csv',PUB_FIELDS),('Pubs_CustomLinks.csv',LINK_FIELDS)]:
        if hashlib.sha256(files[name]).hexdigest()!=manifest['sha256'].get(name):raise ValueError('Export integrity check failed: '+name)
        headers=next(csv.reader(io.StringIO(files[name].decode('utf-8-sig'),newline='')),[])
        # Accept both the existing export and its main_url extension during migration.
        expected=[fields, fields+['main_url']] if name=='Pubs.csv' else [fields]
        if headers not in expected:raise ValueError('Unexpected CSV columns: '+name)
    with tempfile.TemporaryDirectory(prefix='publication-export-') as temp:
        temp=Path(temp)
        for name in names:(temp/name).write_bytes(files[name])
        pubs=generator.read_table(temp/'Pubs.csv',{'id','category','authors','title'})
        links=generator.read_table(temp/'Pubs_CustomLinks.csv',{'publication_id','group','label','url'})
    if len(pubs)!=manifest['publications'] or len(links)!=manifest['links']:raise ValueError('Export row counts do not match')
    if any(p['category'] not in generator.CATEGORIES for p in pubs):raise ValueError('Unexpected private category in public export')
    template=(scripts/'research-template.txt').read_text(encoding='utf-8')
    if target=='research.qmd':template=template.replace('title: "Research — preview"','title: "Research"')
    qmd,_,stats=generator.generate(pubs,links,template)
    content=qmd.encode('utf-8')
    # Prepare all content before replacing any output. Individual BibTeX files go first.
    assets={}
    for pub in pubs:
        if pub['category']=='other' and generator.show_bibtex(pub):
            pub_links=[l for l in links if l['publication_id']==pub['id']]
            assets[site/'bibtex/generated'/(pub['id']+'.bib')]=(generator.bibtex(pub,pub_links)+'\n').encode('utf-8')
    destination=site/target
    old=destination.read_bytes() if destination.exists() else None
    if old!=content and old is not None:
        digest=hashlib.sha256(old).hexdigest()[:16]
        backup=site/'.publication-backups'/(destination.stem+'-'+digest+'.qmd')
        if not backup.exists():atomic_write(backup,old)
    for path,data in assets.items():
        if not path.exists() or path.read_bytes()!=data:atomic_write(path,data)
    if old!=content:atomic_write(destination,content)
    state={'revision':revision,'target':target,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**stats}
    atomic_write(site/'.publication-sync/last-success.json',(json.dumps(state,indent=2)+'\n').encode())
    print(('Updated ' if old!=content else 'Unchanged ')+target+f": {stats['shown']} publications. Data revision: {revision}")
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args();site=args.site.resolve()
    if not (site/'_quarto.yml').exists():raise ValueError('This is not the website folder: _quarto.yml is missing')
    state_dir=site/'.publication-sync';state_dir.mkdir(exist_ok=True)
    with (state_dir/'update.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('A publication update is already running')
        update(site,args.fixture)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,csv.Error) as error:
        print('Publication update stopped: '+str(error),file=sys.stderr)
        sys.exit(1)
