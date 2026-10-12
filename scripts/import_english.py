#!/usr/bin/env python3
"""Rebuild the 39-play English reader using pinned public-domain source snapshots.

Python 3 standard library only. Pass --mit-source /path/to/TheMITTech/shakespeare
for initial acquisition; subsequent builds use the committed source archive.
The two Gutenberg HTML snapshots retain their complete notices and licences.
This importer does not translate, paraphrase, or infer bilingual alignment.
The pinned MIT provenance archive is intentionally unchanged, including its poetry
pages; only the 39 plays are extracted into published reader payloads.
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
ROLE_CUE_FILE = ROOT / 'data/english-collection/sources/mit-embedded-role-cues.json'
ROLE_CUE_MANIFEST = json.loads(ROLE_CUE_FILE.read_text(encoding='utf-8'))
assert ROLE_CUE_MANIFEST['sourceRevision'] == COMMIT
assert ROLE_CUE_MANIFEST['sourceArchiveSha256'] == PINNED_MIT_ARCHIVE_SHA256
ROLE_CUES = {(c['workId'], c['sourceAnchor']): c for c in ROLE_CUE_MANIFEST['occurrences']}
assert len(ROLE_CUES) == len(ROLE_CUE_MANIFEST['occurrences']) == 108
MARKUP_CORRECTION_FILE = ROOT / 'data/english-collection/sources/specific-markup-corrections.json'
MARKUP_CORRECTION_MANIFEST = json.loads(MARKUP_CORRECTION_FILE.read_text(encoding='utf-8'))
MARKUP_CORRECTIONS = MARKUP_CORRECTION_MANIFEST['occurrences']
SPLIT_ROLE_FILE = ROOT / 'data/english-collection/sources/mit-split-role-prefixes.json'
SPLIT_ROLE_MANIFEST = json.loads(SPLIT_ROLE_FILE.read_text(encoding='utf-8'))
SPLIT_ROLES = {(c['archiveEntry'].split('/')[0], c['sourceAnchor']): c for c in SPLIT_ROLE_MANIFEST['occurrences']}
assert len(SPLIT_ROLES) == 320


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
        self.raw_line_text = {}
        self.speech_anchor = None
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
        if tag == 'a' and anchor.startswith('speech'):
            self.speech_anchor = anchor
        if tag == 'b':
            anchor = self.speech_anchor or ''
        if tag in ('h3', 'b', 'i') or (tag == 'a' and re.fullmatch(r'[\d.]+', anchor)):
            self.capture = {'tag': tag, 'anchor': anchor, 'parts': []}
    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip: self.skip = None
            return
        if self.capture and tag == self.capture['tag']:
            c = self.capture
            raw = ''.join(c['parts'])
            if c['tag'] == 'a':
                assert c['anchor'] not in self.raw_line_text, ('Duplicate source line anchor', c['anchor'])
                self.raw_line_text[c['anchor']] = raw
            self.events.append((c['tag'], clean(raw), c['anchor']))
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
        # HTML permits omitted end tags; preserve the final complete block.
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
    applied_cues = set()
    pending_prefix = None
    applied_markup = []
    pending_split = None
    active_split = None
    pending_heading = None
    applied_split = set()

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
            assert pending_prefix is None and pending_heading is None, (work_id, 'Unconsumed markup correction')
            flush()
            correction = next((c for c in MARKUP_CORRECTIONS if c['workId'] == work_id and c['kind'] in ('speaker_label_is_spoken_prefix', 'speaker_label_is_scene_heading') and c['sectionId'] == (section or {}).get('id') and c['speechAnchor'] == anchor), None)
            if pending_split:
                assert anchor == pending_split['followingSpeechAnchor'] and text == pending_split['followingBoldLabel'], (work_id, anchor, 'Reviewed split role context changed')
                assert active_split is None
                speaker = pending_split['joinedLabel']
                active_split = pending_split
                pending_split = None
            elif correction:
                assert text == correction['rawLabelText'], (work_id, anchor, 'Reviewed source context changed')
                if correction['kind'] == 'speaker_label_is_spoken_prefix':
                    assert speaker == correction['speaker']
                    pending_prefix = correction
                else:
                    assert act == correction['correctedAct']
                    new_section(f"Act {act} · {text}. {correction['rawNumberedLineText']}", correction['correctedSectionId'], correction['correctedScene'])
                    pending_heading = correction
                applied_markup.append(correction)
            else:
                speaker = text
        elif tag == 'i':
            flush()
            assert section is not None, (work_id, 'Stage direction before section')
            section['blocks'].append({'kind': 'stage', 'text': text})
        elif tag == 'a':
            expected_lines.append(text)
            assert section is not None, (work_id, 'Line before section')
            numbered_text = text
            split = SPLIT_ROLES.get((work_id, anchor))
            if split:
                assert pending_split is None and active_split is None
                assert p.raw_line_text[anchor] == split['rawPrefix'] and split['originalHtml'] in content, (work_id, anchor, 'Reviewed split role source changed')
                flush()
                pending_split = split
                applied_split.add(anchor)
                imported_lines.append(text)
                continue
            heading_correction = pending_heading
            if heading_correction:
                assert anchor == heading_correction['sourceLine'] and text == heading_correction['rawNumberedLineText']
                pending_heading = None
            prefix_correction = pending_prefix
            if prefix_correction:
                assert anchor == prefix_correction['sourceLine'] and p.raw_line_text[anchor] == prefix_correction['rawNumberedLineText'], (work_id, anchor, 'Reviewed numbered text changed')
                text = prefix_correction['rawLabelText'] + ' ' + text
                pending_prefix = None
            cue = ROLE_CUES.get((work_id, anchor))
            if cue:
                raw = p.raw_line_text[anchor]
                assert raw == cue['rawLineText'], (work_id, anchor, 'Reviewed role cue source changed')
                prefix, delimiter, body = raw.partition('\t')
                assert delimiter and prefix == cue['rawRolePrefix'] and clean(body), (work_id, anchor, 'Invalid role cue')
                flush()
                speaker = cue['speaker']
                text = clean(body)
                applied_cues.add(anchor)
            if pending is None:
                pending = {'kind': 'heading' if heading_correction else 'speech' if speaker else 'text', 'text': text, 'sourceLine': anchor}
                if speaker: pending['speaker'] = speaker
                if prefix_correction or heading_correction:
                    pending['sourceMarkupCorrection'] = prefix_correction or heading_correction
                if active_split:
                    pending['sourceRolePrefix'] = active_split
                    active_split = None
                if cue:
                    pending['sourceRoleCue'] = {
                        'method': ROLE_CUE_MANIFEST['extractionRevision'], 'sourceAnchor': anchor,
                        'rawRolePrefix': cue['rawRolePrefix'], 'rawLineText': cue['rawLineText']}
            else: pending['text'] += '\n' + text
            # The displayed speech omits only the reviewed role prefix. Include
            # that prefix in exact source accounting; all numbered lines remain.
            imported_lines.append(clean(cue['rawRolePrefix'] + '\t' + text) if cue else numbered_text)
    flush()
    sections = [s for s in sections if s['blocks']]
    assert seen_acts == {1, 2, 3, 4, 5}, (work_id, seen_acts)
    assert expected_lines == imported_lines
    assert len(expected_lines) > 1200, (work_id, len(expected_lines))
    # Anchors and stage directions preserve MIT's original ordering, including
    # choruses/headings embedded in speech text. Only reviewed exact allowlists
    # repair source label/heading defects; pinned source bytes stay unchanged.
    assert applied_cues == {anchor for wid, anchor in ROLE_CUES if wid == work_id}, (work_id, 'Missing reviewed role cues')
    assert pending_prefix is None and pending_heading is None and pending_split is None and active_split is None
    assert applied_split == {anchor for wid, anchor in SPLIT_ROLES if wid == work_id}
    assert len(applied_markup) == sum(c['workId'] == work_id and c['kind'] in ('speaker_label_is_spoken_prefix', 'speaker_label_is_scene_heading') for c in MARKUP_CORRECTIONS)
    result = {'id': work_id, 'title': title, 'kind': 'play', 'source': 'MIT Shakespeare (Complete Moby Shakespeare)', 'sourceUrl': MIT_URL + work_id + '/full.html', 'sourceRevision': COMMIT, 'sections': sections, 'sourceLineCount': len(expected_lines)}
    if applied_cues:
        result.update(sourceExtractionRevision=ROLE_CUE_MANIFEST['extractionRevision'], sourceRoleCueCount=len(applied_cues))
    if applied_markup:
        result.update(sourceExtractionRevision=MARKUP_CORRECTION_MANIFEST['extractionRevision'], sourceMarkupCorrectionCount=len(applied_markup))
    if applied_split:
        result.update(sourceSplitRoleExtractionRevision=SPLIT_ROLE_MANIFEST['extractionRevision'], sourceSplitRoleCount=len(applied_split))
    return result


def gutenberg_work(work_id, title, number, content):
    # Original licensed snapshots remain intact; trim only the reader extraction.
    content = re.split(r'\*\*\* END OF THE PROJECT GUTENBERG', content, maxsplit=1, flags=re.I)[0]
    start = content.find('<h3>Dramatis Personæ') if number == 1506 else content.find('<h4 id="id00002"')
    assert start >= 0
    p = Elements(); p.feed(content[start:]); p.close()
    sections, current, act, carry_speaker = [], None, 0, None
    applied_markup = []
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
            correction = next((c for c in MARKUP_CORRECTIONS if c['workId'] == work_id and c['kind'] == 'missing_speaker_corroborated_by_edition' and c['sourceAnchor'] == anchor), None)
            if correction:
                assert current['id'] == correction['sectionId'] and text == correction['sourceText'] and speaker == correction['previousCarriedSpeaker'], (work_id, anchor, 'Reviewed source context changed')
                assert correction['rawSourceParagraph'] in content
                speaker = correction['speaker']
                carry_speaker = speaker
                block['sourceMarkupCorrection'] = correction
                applied_markup.append(correction)
            if speaker: block['speaker'] = speaker
            if anchor: block['sourceAnchor'] = anchor
            current['blocks'].append(block)
        if current and anchor and 'sourceUrl' not in current:
            current['sourceUrl'] = f'https://www.gutenberg.org/ebooks/{number}'
    assert len(applied_markup) == sum(c['workId'] == work_id and c['kind'] == 'missing_speaker_corroborated_by_edition' for c in MARKUP_CORRECTIONS)
    result = {'id': work_id, 'title': title, 'kind': 'play', 'source': f'Project Gutenberg #{number}', 'sourceUrl': f'https://www.gutenberg.org/ebooks/{number}', 'sourceSnapshot': f'sources/gutenberg-{number}.html', 'licenseUrl': 'https://www.gutenberg.org/policy/license.html', 'attributionNote': 'William Shakespeare and John Fletcher' if number == 1506 else 'Attributed in part to William Shakespeare; authorship is disputed.', 'sections': [s for s in sections if s['blocks']]}
    if applied_markup:
        result.update(sourceExtractionRevision=MARKUP_CORRECTION_MANIFEST['extractionRevision'], sourceMarkupCorrectionCount=len(applied_markup))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mit-source', type=Path)
    ap.add_argument('--output', type=Path, default=ROOT / 'data/english-collection')
    args = ap.parse_args()
    out = args.output; (out / 'sources').mkdir(parents=True, exist_ok=True)
    (out / 'sources' / ROLE_CUE_FILE.name).write_bytes(ROLE_CUE_FILE.read_bytes())
    (out / 'sources' / MARKUP_CORRECTION_FILE.name).write_bytes(MARKUP_CORRECTION_FILE.read_bytes())
    (out / 'sources' / SPLIT_ROLE_FILE.name).write_bytes(SPLIT_ROLE_FILE.read_bytes())
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
    for work_id, title, number in [('two_noble_kinsmen', 'The Two Noble Kinsmen', 1506), ('edwardiii', 'King Edward III', 1770)]:
        works.append(gutenberg_work(work_id, title, number, (out / 'sources' / f'gutenberg-{number}.html').read_text(encoding='utf-8')))
    assert len(works) == 39 and all(w['kind'] == 'play' for w in works)
    # Old published poetry payloads must not survive an in-place plays-only build.
    for work_id in ('sonnets', 'lovers_complaint', 'rape_of_lucrece', 'venus_and_adonis',
                    'passionate_pilgrim', 'sundry_notes_of_music', 'phoenix_and_turtle'):
        (out / f'{work_id}.js').unlink(missing_ok=True)
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
    manifest = {'splitRolePrefixes': {'revision': SPLIT_ROLE_MANIFEST['extractionRevision'], 'count': len(SPLIT_ROLES), 'countsByWork': SPLIT_ROLE_MANIFEST['countsByWork'], 'file': SPLIT_ROLE_FILE.name, 'sha256': hashlib.sha256(SPLIT_ROLE_FILE.read_bytes()).hexdigest()}, 'specificMarkupCorrections': {'revision': MARKUP_CORRECTION_MANIFEST['extractionRevision'], 'count': len(MARKUP_CORRECTIONS), 'file': MARKUP_CORRECTION_FILE.name, 'sha256': hashlib.sha256(MARKUP_CORRECTION_FILE.read_bytes()).hexdigest()}, 'roleCueExtractionRevision': ROLE_CUE_MANIFEST['extractionRevision'], 'roleCueCount': len(ROLE_CUES), 'roleCueCountsByWork': ROLE_CUE_MANIFEST['countsByWork'], 'roleCueAllowlist': {'file': ROLE_CUE_FILE.name, 'sha256': hashlib.sha256(ROLE_CUE_FILE.read_bytes()).hexdigest()}, 'scope': '39 plays only; no poetry reader payloads', 'archiveScopeNote': 'The pinned MIT archive is an unmodified historical provenance snapshot and contains poetry source pages. These pages are not extracted into the reader corpus.', 'retrieved': RETRIEVED, 'mitRepository': 'https://github.com/TheMITTech/shakespeare', 'mitCommit': COMMIT, 'mitSourceArchive': archive.name, 'mitArchiveSha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'mitFiles': {p: hashlib.sha256(d).hexdigest() for p, d in sorted(source_files.items())}, 'gutenbergSources': [{'file': f'gutenberg-{n}.html', 'url': u, 'sha256': hashlib.sha256((out / 'sources' / f'gutenberg-{n}.html').read_bytes()).hexdigest()} for n, u in [(1506, 'https://www.gutenberg.org/files/1506/1506-h/1506-h.htm'), (1770, 'https://www.gutenberg.org/cache/epub/1770/pg1770.html')]], 'workCount': len(works), 'playCount': sum(w['kind'] == 'play' for w in works), 'poetryCollectionCount': sum(w['kind'] == 'poetry' for w in works), 'sectionCount': sum(w['sectionCount'] for w in works), 'blockCount': sum(w['blockCount'] for w in works), 'wordCount': sum(w['wordCount'] for w in works)}
    (out / 'sources' / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k.endswith('Count')}, indent=2))

if __name__ == '__main__':
    main()
