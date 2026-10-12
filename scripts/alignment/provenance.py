"""Exact source-span helpers for English-led alignment; no generated translation."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def read_assignment(path):
    raw=Path(path).read_text(encoding='utf-8')
    # Work files have an initialization statement followed by one JSON assignment.
    payload=raw.split('\n',1)[1].split('=',1)[1].strip().removesuffix(';')
    return json.loads(payload)

def source_blocks(english_id, chinese_id):
    english=read_assignment(ROOT/'data/english-collection'/f'{english_id}.js')
    chinese=read_assignment(ROOT/'data/chinese-collection/works'/f'{chinese_id}.js')
    return ({b['id']:b for s in english['sections'] for b in s['blocks']},
            {b['id']:b for s in chinese['sections'] for b in s['blocks']})

def exact_span(blocks, span):
    text=blocks[span['blockId']]['text']
    start,end=span['start'],span['end']
    if not (isinstance(start,int) and isinstance(end,int) and 0<=start<end<=len(text)):
        raise ValueError(f'Invalid source span: {span}')
    actual=text[start:end]
    if span.get('text',actual)!=actual:
        raise ValueError(f'Modified source text: {span["blockId"]}:{start}:{end}')
    return actual

def check_no_overlap(spans):
    consumed={}
    for span in spans:
        key=span['blockId'];a,b=span['start'],span['end']
        for c,d in consumed.get(key,[]):
            if max(a,c)<min(b,d): raise ValueError(f'Duplicate consumption {key}:{a}:{b}')
        consumed.setdefault(key,[]).append((a,b))


def validate_groups(groups, english_blocks, chinese_blocks):
    en_spans=[];zh_spans=[]
    for group in groups:
        if not group.get('english'): raise ValueError('Alignment group requires English ground truth')
        if group.get('status')=='semantically_reviewed' and not group.get('rationale'):
            raise ValueError('Reviewed status requires evidence')
        for span in group['english']:exact_span(english_blocks,span)
        for span in group.get('chinese',[]):exact_span(chinese_blocks,span)
        en_spans.extend(group['english']);zh_spans.extend(group.get('chinese',[]))
    check_no_overlap(en_spans);check_no_overlap(zh_spans)
    return {'groups':len(groups),'englishSpans':len(en_spans),'chineseSpans':len(zh_spans)}
