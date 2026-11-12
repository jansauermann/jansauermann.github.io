#!/usr/bin/env python3
"""Generate a reviewable Quarto research page from Pubs and Pubs_CustomLinks CSVs."""
from __future__ import annotations
import argparse
import csv
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

CATEGORIES = {
    'working_paper': 'Discussion Papers and papers in the editorial process',
    'work_in_progress': 'Selected work in progress',
    'journal_article': 'Peer-reviewed publications',
    'other': 'Research reports and other publications',
}
TYPES = {'article','techreport','unpublished','phdthesis','incollection','misc'}
E = html.escape


def read_table(path, required):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not set(required).issubset(headers):
            raise ValueError(f'{path.name}: missing or duplicate column headings')
        rows=[]
        for n,row in enumerate(reader,2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'{path.name}: row {n} does not match the column headings')
            if any(v.strip() for v in row.values()):
                rows.append({k:v.strip() for k,v in row.items()})
        return rows


def authors(pub):
    names=[n.strip() for n in pub['authors'].split(';') if n.strip()]
    if not names or any(',' not in n for n in names) or len(names)!=len(set(names)):
        raise ValueError(f'{pub["id"]}: authors must be unique Surname, Given entries separated by semicolons')
    return names


def natural(name):
    surname,given=name.split(',',1)
    return given.strip()+' '+surname.strip()


def joined(names):
    if len(names)<2:return ''.join(names)
    if len(names)==2:return names[0]+' and '+names[1]
    return ', '.join(names[:-1])+', and '+names[-1]


def author_display(pub):
    names=authors(pub)
    if len(names)==2:return names[0]+', and '+natural(names[1])
    return joined([names[0]]+[natural(n) for n in names[1:]])


def safe_url(value):
    if not value or re.search(r'[\x00-\x20\x7f\\]',value):
        raise ValueError(f'Invalid URL: {value!r}')
    u=urlsplit(value)
    if u.scheme:
        if u.scheme.lower() not in {'http','https','mailto'}:
            raise ValueError(f'Unsupported URL scheme: {value!r}')
        if u.scheme.lower() in {'http','https'} and not u.netloc:
            raise ValueError(f'Incomplete URL: {value!r}')
    elif u.netloc or value.startswith('/'):
        raise ValueError(f'Use a relative website path or full https URL: {value!r}')
    return value


def normalized_doi(pub):
    doi=re.sub(r'^https?://(?:dx\.)?doi\.org/','',pub.get('doi',''))
    return doi if re.fullmatch(r'10\.\d{4,9}/[^\s{}]+',doi) else ''


def citation(pub):
    get=lambda k:pub.get(k,'')
    if pub['category'] in {'working_paper','work_in_progress'}:
        other=[natural(n) for n in authors(pub) if n!='Sauermann, Jan']
        return E(pub['title'])+(' (with '+E(joined(other))+')' if other else '')
    result=E(author_display(pub))
    if get('year'):result+=' ('+E(get('year'))+')'
    result+=', <em>'+E(pub['title'])+'</em>'
    parts=[]
    if get('journal'):
        outlet='<em>'+E(get('journal'))+'</em>'
        parts.append('<strong>'+outlet+'</strong>' if pub['category']=='journal_article' else outlet)
        volume=E(get('volume'))
        if get('issue'):
            if volume:volume+='('+E(get('issue'))+')'
            elif get('journal')=='Wirtschaft im Wandel':volume=E(get('issue')+'/'+get('year'))
            else:volume=E(get('issue'))
        elif get('month'):volume+=' ('+E(get('month'))+')'
        if volume.strip():parts.append(volume.strip())
        if get('pages'):parts.append('pp. '+E(get('pages')))
        elif get('article_number'):parts.append(E(get('article_number')))
        if pub['category']=='other':
            for key in ['institution','publisher','address']:
                if get(key):parts.append(E(get(key)))
    else:
        if get('entry_type')=='phdthesis':parts.append('PhD thesis')
        if get('booktitle'):parts.append('in: <em>'+E(get('booktitle'))+'</em>')
        series=' '.join(x for x in [get('series'),get('number')] if x)
        if series:parts.append(E(series))
        institution=get('institution')
        if institution and institution.casefold() not in series.casefold():parts.append(E(institution))
        if get('publisher') and get('publisher')!=institution:parts.append(E(get('publisher')))
        if get('address'):parts.append(E(get('address')))
        if get('pages'):parts.append('pp. '+E(get('pages')))
        elif get('article_number'):parts.append(E(get('article_number')))
        if get('month'):parts.append(E(get('month')))
    if get('publication_details'):parts.append(E(get('publication_details')))
    return result+(', '+', '.join(parts) if parts else '')


def latex(value):
    replacements={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$',
                  '#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(replacements.get(c,c) for c in value)


def bibtex(pub, links):
    kind=pub.get('entry_type','misc') or 'misc'
    fields={'author':' and '.join(authors(pub)), 'title':pub['title']}
    for key in ['year','journal','volume','month','issn','keywords','series','booktitle','publisher','address','abstract']:
        if pub.get(key):fields[key]=pub[key]
    if pub.get('issue') and kind=='article':fields['number']=pub['issue']
    elif pub.get('number'):fields['number']=pub['number']
    if pub.get('institution'):fields['school' if kind=='phdthesis' else 'institution']=pub['institution']
    pages=pub.get('pages','') or pub.get('article_number','')
    if pages:fields['pages']=re.sub(r'\s*[–—-]+\s*','--',pages)
    doi=normalized_doi(pub)
    if doi:fields['doi']=doi
    candidates=[l for l in links if l.get('url','').startswith(('https://','http://'))]
    preferred=next((l for l in candidates if l['group']=='Bibliographic references' and l['label']=='Bibliographic URL'),None)
    if not preferred:preferred=next((l for l in candidates if l['group']!='Bibliographic references'),None)
    if preferred:fields['url']=preferred['url']
    eprint=next((l['url'] for l in candidates if l['label']=='Eprint' and not (urlsplit(l['url']).hostname or '').endswith(('.lan','.local'))),'')
    if eprint:fields['eprint']=eprint
    notes=[]
    if kind=='unpublished':notes.append('Work in progress' if pub['category']=='work_in_progress' else 'Unpublished working paper')
    if pub.get('publication_details'):notes.append(pub['publication_details'])
    if notes:fields['note']='; '.join(dict.fromkeys(notes))
    lines=[]
    for key,value in fields.items():
        encoded=value if key in {'doi','url','eprint','pages','year','volume','number','issn'} else latex(value)
        if key=='title':encoded='{'+encoded+'}'
        lines.append('  '+key+' = {'+encoded+'}')
    return '@'+kind+'{'+pub['id']+',\n'+',\n'.join(lines)+'\n}'


def group_rank(group):
    folded=group.casefold()
    if folded=='more information':return (0,'')
    if folded.startswith('non-technical'):return (1,folded)
    if folded=='bibliographic references':return (9,'')
    return (5,folded)


def show_bibtex(pub):
    if pub['category']=='journal_article':
        return True
    if pub['category']!='other':
        return False
    if pub.get('entry_type') in {'techreport','phdthesis','unpublished'}:
        return True
    # Some unpublished research papers are stored as technical reports, e.g. IWH DP.
    return bool(re.search(r'\b(?:working paper|discussion paper|DP)\b',pub.get('series',''),re.I))


def additional_info(pub, links):
    groups={}
    for link in links:
        group=link.get('group','') or 'More information'
        if group.casefold()=='bibliographic references':
            continue
        groups.setdefault(group,[]).append(link)
    blocks=[]
    for group in sorted(groups,key=group_rank):
        def label_text(link):
            label=link['label'].strip()
            while label.startswith('[') and label.endswith(']'):
                label=label[1:-1].strip()
            return E(label)

        def link_url(link):
            url=link['url']
            # This malformed tracking query has a clean equivalent in the source metadata.
            if url.endswith('?via%3Dihub'):url=url.split('?',1)[0]
            return E(safe_url(url),quote=True)

        if group.casefold()=='more information':
            pending=[]
            for link in groups[group]:
                label=label_text(link)
                if link.get('url'):
                    pending.append('<a href="'+link_url(link)+'">['+label+']</a>')
                else:
                    pending.append('<span class="pub-note">['+label+']</span>')
            if pending:blocks.append('<p>'+' '.join(pending)+'</p>')
        else:
            content=[]
            for link in groups[group]:
                label=label_text(link)
                content.append('<a href="'+link_url(link)+'">'+label+'</a>' if link.get('url') else '<span class="pub-note">'+label+'</span>')
            blocks.append('<p>['+E(group)+': '+', '.join(content)+']</p>')
    if pub.get('scopus_file'):
        blocks.append('<p><scopus-citations file="'+E(pub['scopus_file'],quote=True)+'"></scopus-citations></p>')
    return '\n'.join(blocks)


def primary_publication_link(links):
    return next((link['url'] for link in links
                 if link.get('url') and not link['url'].startswith('mailto:')
                 and link.get('group')!='Bibliographic references'),'')


def validate(pubs,links):
    ids=set()
    for p in pubs:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',p['id']) or p['id'] in ids:
            raise ValueError('Invalid/duplicate publication ID: '+p['id'])
        ids.add(p['id'])
        if not p['title']:raise ValueError('Missing title: '+p['id'])
        authors(p)
        if p.get('year') and not re.fullmatch(r'\d{4}',p['year']):raise ValueError('Invalid year: '+p['id'])
        if p.get('entry_type','misc') not in TYPES:raise ValueError('Unknown entry_type: '+p['id'])
        if p.get('scopus_file') and not re.fullmatch(r'citations/[A-Za-z0-9_.-]+\.txt',p['scopus_file']):
            raise ValueError('Invalid counter file: '+p['id'])
    for l in links:
        if l['publication_id'] not in ids:raise ValueError('Link has no matching publication: '+l['publication_id'])
        if not l['label']:raise ValueError('Empty custom link/note label')
        if l.get('url'):safe_url(l['url'])


STYLE_AND_TOGGLE='''```{=html}
<style>
.publication { margin-bottom: .45rem; }
.publication > p { margin-bottom: .1rem; }
.pub-actions { display: flex; flex-wrap: wrap; gap: .25em 1.1em; }
.pub-toggle { background: none; border: 0; color: inherit; padding: 0; font: inherit; font-size: .78em; cursor: pointer; text-align: left; }
.pub-toggle:hover { text-decoration: underline; }
.pub-toggle:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
.pub-detail { padding: .4em 0 .1em; font-size: .9em; }
.publication details[id^="moreinfo-"] .pub-detail { font-size: .78em; }
.publication details[id^="abstract-"] .pub-detail { font-size: .76em; }
.pub-detail p { margin: .35em 0; }
.pub-detail pre, .pub-detail pre code { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }
.pub-detail pre { font-size: .70em; }
.publication details { margin: 0; }
.publication details[open] { margin-top: .1em; }
.pub-note { overflow-wrap: anywhere; }
.pub-direct-links { font-size: .78em; }
.pub-direct-links p { margin: .15em 0; }
.pub-direct-link { color: inherit; text-decoration: none; }
.pub-direct-link:hover { text-decoration: underline; }
</style>
<script>
document.addEventListener('click', event => {
  const button = event.target.closest('.pub-toggle');
  if (!button) return;
  const target = document.getElementById(button.getAttribute('aria-controls'));
  const opening = !target.open;
  document.querySelectorAll('.publication details').forEach(panel => panel.open = false);
  document.querySelectorAll('.pub-toggle').forEach(control => {
    control.setAttribute('aria-expanded', 'false');
    control.querySelector('.tri').textContent = '▸';
  });
  target.open = opening;
  button.setAttribute('aria-expanded', String(opening));
  button.querySelector('.tri').textContent = opening ? '▾' : '▸';
});
</script>
```
'''


def generate(pubs,links,template):
    validate(pubs,links)
    if template.count('{{PUBLICATIONS}}')!=1:raise ValueError('Invalid research page template')
    visible=[p for p in pubs if p['category'] in CATEGORIES]
    if not visible:raise ValueError('No publications in the published categories')
    link_map={p['id']:[] for p in visible}
    for l in links:
        if l['publication_id'] in link_map:link_map[l['publication_id']].append(l)
    all_bib=[];sections=[]
    for category,heading in CATEGORIES.items():
        group=[p for p in visible if p['category']==category]
        if not group:continue
        blocks=[]
        for p in sorted(group,key=lambda p:-int(p.get('year') or 0)):
            key=p['id'];panels=[]
            public_links=[link for link in link_map[key] if link.get('url')
                          and link.get('group','').casefold()!='bibliographic references']
            is_report=category=='other' and p.get('entry_type')=='techreport'
            if category=='other' and not (is_report or show_bibtex(p) or p.get('abstract','').strip()) and len(public_links)<=1:
                primary=primary_publication_link(link_map[key])
                main=citation(p)
                remaining=[];removed_primary=False
                for link in link_map[key]:
                    if primary and not removed_primary and link.get('url')==primary:
                        removed_primary=True
                        continue
                    remaining.append(link)
                if is_report:
                    direct=('<p>'+' '.join('<a class="pub-direct-link" href="'+E(safe_url(link['url']),quote=True)
                                          +'"><span aria-hidden="true">▸</span> More information and download</a>'
                                          for link in public_links)+'</p>') if public_links else ''
                    remaining=[link for link in link_map[key] if not link.get('url')]
                else:
                    primary_label=next((link['label'] for link in public_links if link['url']==primary),'More information and download')
                    if primary_label.strip('[] ').casefold()=='show more information':primary_label='More information and download'
                    direct=('<p><a class="pub-direct-link" href="'+E(safe_url(primary),quote=True)
                            +'"><span aria-hidden="true">▸</span> '+E(primary_label.strip('[] '))+'</a></p>') if primary else ''
                direct+=additional_info(p,remaining)
                if show_bibtex(p):
                    all_bib.append(bibtex(p,link_map[key]))
                    direct+='<p><a href="bibtex/generated/'+key+'.bib" download>[BibTeX]</a></p>'
                blocks.append('<div class="publication" id="pub-'+key+'">\n<p>'+main+'</p>'
                              + ('\n<div class="pub-direct-links">'+direct+'</div>' if direct else '')
                              +'\n</div>')
                continue
            info=additional_info(p,link_map[key])
            if info:panels.append(('moreinfo','More information and download',info))
            if p.get('abstract','').strip():panels.append(('abstract','Abstract','<p>'+E(p['abstract']).replace('\n','<br>')+'</p>'))
            if show_bibtex(p):
                bib=bibtex(p,link_map[key]);all_bib.append(bib)
                panels.append(('bibtex','BibTeX','<pre><code class="language-bibtex">'+E(bib)+'</code></pre>'))
            controls='\n'.join('<button class="pub-toggle" type="button" aria-expanded="false" aria-controls="'+kind+'-'+key+'"><span class="tri" aria-hidden="true">▸</span> '+label+'</button>' for kind,label,content in panels)
            bodies='\n'.join('<details id="'+kind+'-'+key+'"><summary hidden>'+label+'</summary><div class="pub-detail">'+content+'</div></details>' for kind,label,content in panels)
            blocks.append('<div class="publication" id="pub-'+key+'">\n<p>'+citation(p)+'</p>\n<div class="pub-actions">'+controls+'</div>\n'+bodies+'\n</div>')
        sections.append('## '+heading+'\n\n```{=html}\n'+'\n\n'.join(blocks)+'\n```\n')
    qmd=template.replace('{{PUBLICATIONS}}','\n'.join(sections)+'\n'+STYLE_AND_TOGGLE)
    stats={'shown':len(visible),'excluded_by_category':len(pubs)-len(visible),
           'custom_rows_available':sum(len(v) for v in link_map.values()),
           'custom_rows_shown':sum(1 for rows in link_map.values() for link in rows
                                   if link.get('group','').casefold()!='bibliographic references'),
           'bibtex_entries':len(all_bib)}
    return qmd,'\n\n'.join(all_bib)+'\n',stats


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pubs',type=Path,required=True)
    parser.add_argument('--links',type=Path,required=True)
    parser.add_argument('--template',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--bib-output',type=Path)
    parser.add_argument('--bib-dir',type=Path,help='Generated individual BibTeX files (default: beside QMD in bibtex/generated)')
    args=parser.parse_args()
    pubs=read_table(args.pubs,{'id','category','authors','title'})
    links=read_table(args.links,{'publication_id','group','label','url'})
    qmd,bib,stats=generate(pubs,links,args.template.read_text(encoding='utf-8'))
    bib_dir=args.bib_dir or args.output.parent/'bibtex/generated'
    for p in pubs:
        if p['category']=='other' and show_bibtex(p):
            bib_dir.mkdir(parents=True,exist_ok=True)
            pub_links=[link for link in links if link['publication_id']==p['id']]
            (bib_dir/(p['id']+'.bib')).write_text(bibtex(p,pub_links)+'\n',encoding='utf-8')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(qmd,encoding='utf-8')
    if args.bib_output:args.bib_output.write_text(bib,encoding='utf-8')
    print(json.dumps(stats))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,csv.Error) as error:
        print('Research preview generation stopped: '+str(error),file=sys.stderr)
        sys.exit(1)
