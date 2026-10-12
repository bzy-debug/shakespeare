#!/usr/bin/env python3
"""Rebuild the English reader corpus, using pinned public-domain source snapshots.

Python 3 standard library only. Pass --mit-source /path/to/TheMITTech/shakespeare
for initial acquisition; subsequent builds use the committed source archive.
The two Gutenberg HTML snapshots retain their complete notices and licences.
This importer does not translate, paraphrase, or infer bilingual alignment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
import zipfile

COMMIT = '6b82db852c7322dd33e95db347f0ddfc812c6409'
MIT_URL = 'https://shakespeare.mit.edu/'
RETRIEVED = '2026-10-12'
PINNED_MIT_ARCHIVE_SHA256 = '13d60111bdf4ebe68a6aa0d576937de15ac5dc31303487e12961702769e159b6'
PINNED_GUTENBERG_SHA256 = {'gutenberg-1506.html': '6f6a612fcb25a36c89d12c7200be3876701478f6d669ab9c7cf4c2f6a056c91a', 'gutenberg-1770.html': '401c2bc8d6edf9f4e7d97689c1611b3ef314c7530796f3850c748018fbd8245e'}
ROOT = Path(__file__).resolve().parents[1]


def clean(text):
    return ' '.join(text.split())


def lines(text):
    return '\n'.join(clean(line) for line in text.split('\n') if clean(line))


def roman(value):
    numbers = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    vals = [numbers[c] for c in value.upper()]
    return sum(-v if i + 1 < len(vals) and v < vals[i + 1] else v for i, v in enumerate(vals))


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag == 'br': self.parts.append('\n')


def plaintext(html):
    p = Text(); p.feed(html); return lines(''.join(p.parts))


class MITEvents(HTMLParser):
    """Parse explicit headings, speaker labels, stage directions and line anchors.

    Text outside these structures is an error, rather than silently discarded.
    Whitespace and the source's navigation/header tables are not body text.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events, self.unclaimed = [], []
        self.skip, self.capture = None, None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.skip: return
        if tag in ('head', 'table'):
            self.skip = tag; return
        if self.capture:
            if tag == 'br': self.capture['parts'].append('\n')
            return
        anchor = attrs.get('name', '')
        if tag in ('h3', 'b', 'i') or (tag == 'a' and re.fullmatch(r'[\d.]+', anchor)):
            self.capture = {'tag': tag, 'anchor': anchor, 'parts': []}
    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip: self.skip = None
            return
        if self.capture and tag == self.capture['tag']:
            c = self.capture
            self.events.append((c['tag'], clean(''.join(c['parts'])), c['anchor']))
            self.capture = None
    def handle_data(self, data):
        if self.skip: return
        if self.capture: self.capture['parts'].append(data)
        elif clean(data): self.unclaimed.append(clean(data))


class Elements(HTMLParser):
    """Read paragraph/verse blocks and section headings in simple HTML editions."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = []
        self.capture = None
        self.skip = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.skip: return
        if tag in ('head', 'table', 'style', 'script'):
            self.skip = tag; return
        if self.capture:
            if tag == 'br': self.capture['parts'].append('\n')
            if tag == 'a' and attrs.get('id'): self.capture['anchor'] = attrs['id']
            return
        if tag in ('p', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5'):
            self.capture = {'tag': tag, 'parts': [], 'attrs': attrs, 'anchor': attrs.get('id')}
    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip: self.skip = None
            return
        if self.capture and tag == self.capture['tag']:
            c = self.capture
            self.events.append((c['tag'], lines(''.join(c['parts'])), c['attrs'], c['anchor']))
            self.capture = None
    def handle_data(self, data):
        if not self.skip and self.capture: self.capture['parts'].append(data)
    def close(self):
        # Sonnet CLIV ends after its final BR without closing HTML tags.
        # HTML permits omitted end tags; preserve the final complete stanza.
        if self.capture:
            c = self.capture
            self.events.append((c['tag'], lines(''.join(c['parts'])), c['attrs'], c['anchor']))
            self.capture = None
        super().close()


def mit_work(work_id, title, content):
    p = MITEvents(); p.feed(content)
    assert not p.unclaimed, (work_id, 'Unparsed source body text', p.unclaimed[:10])
    assert p.capture is None, (work_id, 'Unclosed text capture')
    sections, section, speaker, act = [], None, None, 0
    pending = None
    seen_acts = set()
    expected_lines, imported_lines = [], []

    def flush():
        nonlocal pending
        if pending:
            section['blocks'].append(pending)
            pending = None

    def new_section(label, sid, scene=None):
        nonlocal section, speaker
        flush()
        section = {'id': sid, 'label': label, 'act': act, 'sourceUrl': MIT_URL + work_id + '/full.html', 'blocks': []}
        if scene is not None: section['scene'] = scene
        sections.append(section)
        speaker = None

    for tag, text, anchor in p.events:
        if not text: continue
        if tag == 'h3':
            if match := re.fullmatch(r'ACT ([IVXLC]+)', text, re.I):
                act = roman(match[1]); seen_acts.add(act)
                new_section(text, f'act-{act}-opening')
            elif match := re.match(r'SCENE ([IVXLC]+)\.', text, re.I):
                scene = roman(match[1])
                label = ('Induction · ' if act == 0 else f'Act {act} · ') + text
                new_section(label, f'{act}.{scene}', scene)
            else:
                new_section((f'Act {act} · ' if act else '') + text, f'{act}-{len(sections) + 1}-{text.split()[0].lower()}')
        elif tag == 'b':
            flush(); speaker = text
        elif tag == 'i':
            flush()
            assert section is not None, (work_id, 'Stage direction before section')
            section['blocks'].append({'kind': 'stage', 'text': text})
        elif tag == 'a':
            expected_lines.append(text)
            assert section is not None, (work_id, 'Line before section')
            if pending is None:
                pending = {'kind': 'speech' if speaker else 'text', 'text': text, 'sourceLine': anchor}
                if speaker: pending['speaker'] = speaker
            else: pending['text'] += '\n' + text
            imported_lines.append(text)
    flush()
    sections = [s for s in sections if s['blocks']]
    assert seen_acts == {1, 2, 3, 4, 5}, (work_id, seen_acts)
    assert expected_lines == imported_lines
    assert len(expected_lines) > 1200, (work_id, len(expected_lines))
    # Anchors and stage directions preserve MIT's original ordering, including
    # choruses/headings embedded in speech text. No editorial scene repair.
    return {'id': work_id, 'title': title, 'kind': 'play', 'source': 'MIT Shakespeare (Complete Moby Shakespeare)', 'sourceUrl': MIT_URL + work_id + '/full.html', 'sourceRevision': COMMIT, 'sections': sections, 'sourceLineCount': len(expected_lines)}


def mit_poem(work_id, title, path, content):
    p = Elements(); p.feed(content); p.close()
    sections, current = [], None
    opening = {'lovers_complaint': 'FROM off a hill', 'rape_of_lucrece': 'FROM the besieged', 'venus_and_adonis': 'EVEN as the sun'}[work_id]
    def begin(label, sid):
        nonlocal current
        current = {'id': sid, 'label': label, 'sourceUrl': MIT_URL + path, 'blocks': []}
        sections.append(current)
    for tag, text, attrs, anchor in p.events:
        if not text: continue
        if tag.startswith('h'):
            if clean(text).lower() == title.lower(): continue
            begin(text, f'section-{len(sections) + 1}')
        else:
            if text.startswith(opening): begin(title, 'poem')
            elif current is None: begin('Dedication and epigraph', 'dedication')
            current['blocks'].append({'kind': 'verse' if tag == 'blockquote' else 'text', 'text': text})
    assert any(s['id'] == 'poem' for s in sections), work_id
    return {'id': work_id, 'title': title, 'kind': 'poetry', 'source': 'MIT Shakespeare (Complete Moby Shakespeare)', 'sourceUrl': MIT_URL + path, 'sourceRevision': COMMIT, 'sections': [s for s in sections if s['blocks']]}


def gutenberg_work(work_id, title, number, content):
    # Original licensed snapshots remain intact; trim only the reader extraction.
    content = re.split(r'\*\*\* END OF THE PROJECT GUTENBERG', content, maxsplit=1, flags=re.I)[0]
    start = content.find('<h3>Dramatis Personæ') if number == 1506 else content.find('<h4 id="id00002"')
    assert start >= 0
    p = Elements(); p.feed(content[start:]); p.close()
    sections, current, act, carry_speaker = [], None, 0, None
    def begin(label, sid, scene=None):
        nonlocal current, carry_speaker
        current = {'id': sid, 'label': label, 'act': act, 'blocks': []}
        if scene is not None: current['scene'] = scene
        sections.append(current); carry_speaker = None
    for tag, text, attrs, anchor in p.events:
        if not text: continue
        text = lines(text)
        both = re.match(r'ACT ([IVXLC]+)\. SCENE ([IVXLC]+)\.', text, re.I)
        if tag.startswith('h') and both:
            act, scene = roman(both[1]), roman(both[2])
            begin(clean(text), f'{act}.{scene}', scene)
        elif tag.startswith('h') and (match := re.fullmatch(r'ACT ([IVXLC]+)', text, re.I)):
            act = roman(match[1]); continue
        elif tag.startswith('h') and (match := re.match(r'SCENE ([IVXLC]+)\.', text, re.I)):
            scene = roman(match[1]); begin(f'Act {act} · {clean(text)}', f'{act}.{scene}', scene)
        elif tag.startswith('h') and text.upper() in ('PROLOGUE', 'EPILOGUE'):
            begin(text, text.lower())
        elif tag.startswith('h') and ('PERSON' in text.upper() or 'PERSONÆ' in text.upper()):
            begin(text, 'dramatis-personae')
        else:
            if current is None: begin('Front matter', 'front-matter')
            kind = 'text'
            speaker = None
            if attrs.get('class') in ('scenedesc', 'right') or (text.startswith('[') and text.endswith(']')):
                kind = 'stage'
            elif current['id'] != 'dramatis-personae':
                first, _, rest = text.partition('\n')
                if re.fullmatch(r"[A-Z][A-Z ’'.,0-9–-]*\.", first) and first != 'FINIS.':
                    speaker = first.rstrip('.')
                    carry_speaker = speaker
                    if not rest: continue
                    text, kind = rest, 'speech'
                elif carry_speaker and not tag.startswith('h'):
                    speaker, kind = carry_speaker, 'speech'
                elif tag.startswith('h'): kind = 'heading'
            block = {'kind': kind, 'text': text}
            if speaker: block['speaker'] = speaker
            if anchor: block['sourceAnchor'] = anchor
            current['blocks'].append(block)
        if current and anchor and 'sourceUrl' not in current:
            current['sourceUrl'] = f'https://www.gutenberg.org/ebooks/{number}'
    return {'id': work_id, 'title': title, 'kind': 'play', 'source': f'Project Gutenberg #{number}', 'sourceUrl': f'https://www.gutenberg.org/ebooks/{number}', 'sourceSnapshot': f'sources/gutenberg-{number}.html', 'licenseUrl': 'https://www.gutenberg.org/policy/license.html', 'attributionNote': 'William Shakespeare and John Fletcher' if number == 1506 else 'Attributed in part to William Shakespeare; authorship is disputed.', 'sections': [s for s in sections if s['blocks']]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mit-source', type=Path)
    ap.add_argument('--output', type=Path, default=ROOT / 'data/english-collection')
    args = ap.parse_args()
    out = args.output; (out / 'sources').mkdir(parents=True, exist_ok=True)
    archive = out / 'sources' / f'mit-shakespeare-{COMMIT}.zip'
    if args.mit_source:
        actual_commit = subprocess.check_output(['git', '-C', str(args.mit_source), 'rev-parse', 'HEAD'], text=True).strip()
        assert actual_commit == COMMIT, ('Unexpected MIT source revision', actual_commit)
        files = ['index.html'] + [str(p.relative_to(args.mit_source)) for p in args.mit_source.glob('*/full.html')]
        files += [f'Poetry/{name}' for name in ['LoversComplaint.html', 'RapeOfLucrece.html', 'VenusAndAdonis.html', 'various']]
        files += [str(p.relative_to(args.mit_source)) for p in args.mit_source.glob('Poetry/sonnet.*.html')]
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for path in sorted(set(files)):
                info = zipfile.ZipInfo(path, date_time=(2023, 5, 10, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, (args.mit_source / path).read_bytes())
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == PINNED_MIT_ARCHIVE_SHA256, 'MIT source archive checksum mismatch'
    for filename, sha in PINNED_GUTENBERG_SHA256.items():
        assert hashlib.sha256((out / 'sources' / filename).read_bytes()).hexdigest() == sha, ('Gutenberg snapshot checksum mismatch', filename)
    with zipfile.ZipFile(archive) as z:
        source_files = {name: z.read(name) for name in z.namelist()}
    def read(path):
        data = source_files[path]
        try: return data.decode('utf-8')
        except UnicodeDecodeError: return data.decode('latin-1')
    titles = [(m[1], clean(plaintext(m[2]))) for m in re.finditer(r'<a\s+href="([\w]+?)/index.html"[^>]*>(.*?)</a>', read('index.html'), re.I | re.S)]
    assert len(titles) == 37
    works = [mit_work(work_id, title, read(f'{work_id}/full.html')) for work_id, title in titles]
    sonnets = []
    paths = sorted((name for name in source_files if re.fullmatch(r'Poetry/sonnet\.[IVXLC]+\.html', name)), key=lambda x: roman(x.split('.')[1]))
    assert len(paths) == 154
    for path in paths:
        n = roman(path.split('.')[1]); p = Elements(); p.feed(read(path)); p.close()
        stanzas = [{'kind': 'verse', 'text': text} for tag, text, _, _ in p.events if tag == 'blockquote']
        assert stanzas, path
        sonnets.append({'id': str(n), 'label': f'Sonnet {n}', 'sourceUrl': MIT_URL + path, 'blocks': stanzas})
    assert [int(s['id']) for s in sonnets] == list(range(1, 155))
    works.append({'id': 'sonnets', 'title': 'The Sonnets', 'kind': 'poetry', 'source': 'MIT Shakespeare (Complete Moby Shakespeare)', 'sourceUrl': MIT_URL + 'Poetry/sonnets.html', 'sourceRevision': COMMIT, 'sections': sonnets})
    for work_id, title, path in [('lovers_complaint', "A Lover's Complaint", 'Poetry/LoversComplaint.html'), ('rape_of_lucrece', 'The Rape of Lucrece', 'Poetry/RapeOfLucrece.html'), ('venus_and_adonis', 'Venus and Adonis', 'Poetry/VenusAndAdonis.html')]:
        works.append(mit_poem(work_id, title, path, read(path)))
    various = read('Poetry/various')
    split = re.split(r'^\s*(THE PASSIONATE PILGRIM|SONNETS TO SUNDRY NOTES OF MUSIC|THE PHOENIX AND THE TURTLE)\s*$', various, flags=re.M)
    assert len(split) == 7
    for work_id, title, body in zip(['passionate_pilgrim', 'sundry_notes_of_music', 'phoenix_and_turtle'], ['The Passionate Pilgrim', 'Sonnets to Sundry Notes of Music', 'The Phoenix and the Turtle'], split[2::2]):
        sections, current = [], None
        for chunk in re.split(r'\n\s*\n', body.strip()):
            text = lines(chunk)
            if not text: continue
            if re.fullmatch(r'[IVXLC]+\.', text):
                n = roman(text.rstrip('.')); current = {'id': str(n), 'label': f'Poem {n}', 'blocks': []}; sections.append(current)
            else:
                if current is None:
                    current = {'id': 'poem', 'label': title, 'blocks': []}; sections.append(current)
                current['blocks'].append({'kind': 'heading' if text == 'THRENOS.' else 'verse', 'text': text})
        works.append({'id': work_id, 'title': title, 'kind': 'poetry', 'source': 'MIT Shakespeare (Complete Moby Shakespeare)', 'sourceUrl': MIT_URL + 'Poetry/various', 'sourceRevision': COMMIT, 'attributionNote': 'The Passionate Pilgrim and Sundry Notes include poems by other writers; preserved as collected in this historical source.' if work_id != 'phoenix_and_turtle' else '', 'sections': sections})
    for work_id, title, number in [('two_noble_kinsmen', 'The Two Noble Kinsmen', 1506), ('edwardiii', 'King Edward III', 1770)]:
        works.append(gutenberg_work(work_id, title, number, (out / 'sources' / f'gutenberg-{number}.html').read_text(encoding='utf-8')))
    catalog = []
    for work in works:
        work['sourceLabel'] = 'Project Gutenberg' if work['source'].startswith('Project Gutenberg') else 'MIT Shakespeare'
        assert work['sections'], work['id']
        ids = [s['id'] for s in work['sections']]
        assert len(ids) == len(set(ids)), (work['id'], ids)
        for section in work['sections']:
            assert section['blocks'], (work['id'], section['id'])
            for i, block in enumerate(section['blocks'], 1):
                block['id'] = f"{work['id']}:{section['id']}:{i}"
                assert block['text'].strip()
        work['sectionCount'] = len(work['sections'])
        work['blockCount'] = sum(len(s['blocks']) for s in work['sections'])
        work['wordCount'] = sum(len(b['text'].split()) for s in work['sections'] for b in s['blocks'])
        payload = json.dumps(work, ensure_ascii=False, separators=(',', ':'))
        (out / f"{work['id']}.js").write_text('window.SHAKESPEARE_ENGLISH = window.SHAKESPEARE_ENGLISH || {};\nwindow.SHAKESPEARE_ENGLISH[' + json.dumps(work['id']) + '] = ' + payload + ';\n', encoding='utf-8')
        summary = {k: v for k, v in work.items() if k != 'sections'}
        summary['file'] = f"data/english-collection/{work['id']}.js"
        summary['sections'] = [{k: v for k, v in s.items() if k != 'blocks'} for s in work['sections']]
        catalog.append(summary)
    (out / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'catalog.js').write_text('window.SHAKESPEARE_ENGLISH_CATALOG = ' + json.dumps(catalog, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    manifest = {'retrieved': RETRIEVED, 'mitRepository': 'https://github.com/TheMITTech/shakespeare', 'mitCommit': COMMIT, 'mitSourceArchive': archive.name, 'mitArchiveSha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'mitFiles': {p: hashlib.sha256(d).hexdigest() for p, d in sorted(source_files.items())}, 'gutenbergSources': [{'file': f'gutenberg-{n}.html', 'url': u, 'sha256': hashlib.sha256((out / 'sources' / f'gutenberg-{n}.html').read_bytes()).hexdigest()} for n, u in [(1506, 'https://www.gutenberg.org/files/1506/1506-h/1506-h.htm'), (1770, 'https://www.gutenberg.org/cache/epub/1770/pg1770.html')]], 'workCount': len(works), 'playCount': sum(w['kind'] == 'play' for w in works), 'poetryCollectionCount': sum(w['kind'] == 'poetry' for w in works), 'sectionCount': sum(w['sectionCount'] for w in works), 'blockCount': sum(w['blockCount'] for w in works), 'wordCount': sum(w['wordCount'] for w in works)}
    (out / 'sources' / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k.endswith('Count')}, indent=2))

if __name__ == '__main__':
    main()
