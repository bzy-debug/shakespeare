#!/usr/bin/env python3
"""Add reviewed whole-block matches only where the current reader has a gap.

Conflicts require a separate explicit correction; this command never silently
replaces an existing alignment or reuses a Chinese source character.
"""
from pathlib import Path
import argparse,hashlib,json
from provenance import read_assignment,exact_span,check_no_overlap
ROOT=Path(__file__).resolve().parents[2]
def apply(path,records):
 incoming=json.loads(path.read_text());eid=incoming['workId']
 catalog=json.loads((ROOT/'data/chinese-collection/catalog.json').read_text());meta=next(m for m in catalog if m.get('englishId')==eid and m['kind']=='play')
 en=read_assignment(ROOT/'data/english-collection'/f'{eid}.js');zh=read_assignment(ROOT/meta['file'])
 eb={b['id']:b for sec in en['sections'] for b in sec['blocks']};zb={b['id']:b for sec in zh['sections'] for b in sec['blocks']};sections={b['id']:sec['id'] for sec in en['sections'] for b in sec['blocks']}
 target=records/f'{eid}.json';current=json.loads(target.read_text());used={k for g in current['groups'] if g.get('chinese') for k in g['englishBlockIds']};zz=[s for g in current['groups'] if g['englishBlockIds'] for s in g['chinese']];added=[]
 used.update(r['english']['blockId'] for r in current.get('resolutions',[]))
 for g in incoming['groups']:
  ids=g['englishBlockIds']
  if g.get('status')!='semantically_reviewed' or not g.get('rationale'):raise ValueError('Review status and evidence required')
  if not ids or len(ids)!=len(set(ids)) or used.intersection(ids):raise ValueError('English blocks already aligned or duplicated')
  if {p['blockId'] for p in g['english']}!=set(ids):raise ValueError('English review evidence missing')
  for p in g['english']:
   exact_span(eb,p)
   if p['start']!=0 or p['end']!=len(eb[p['blockId']]['text']):raise ValueError('Partial English block')
  if len({sections[k] for k in ids})!=1:raise ValueError('Cross-section group')
  if not g['chinese']:raise ValueError('Empty translation')
  for p in g['chinese']:exact_span(zb,p)
  zz.extend(g['chinese']);used.update(ids)
  added.append({k:g[k] for k in ('englishBlockIds','chinese','status','kind','method','rationale','reviewNotes','sourceVariants','reviewer','matchingPool','reviewGroupId') if k in g})
 resolutions=incoming.get('resolutions',[])
 for r in resolutions:
  span=r['english'];key=span['blockId'];exact_span(eb,span)
  if key in used or span['start']!=0 or span['end']!=len(eb[key]['text']):raise ValueError('Resolution overlaps accepted block or is partial')
  if r.get('status') not in ('source_omission','source_artifact') or not r.get('rationale') or not r.get('evidence'):raise ValueError('Resolution classification and evidence required')
  used.add(key)
 check_no_overlap(zz)
 new_ids={k for g in added for k in g['englishBlockIds']}|{r['english']['blockId'] for r in resolutions}
 kept=[]
 for g in current['groups']:
  if not g['englishBlockIds']:
   # Unmatched Chinese is a provenance ledger, not consumed reader content.
   # Retain only source intervals not now consumed by a reviewed match.
   remaining=[]
   for p in g['chinese']:
    intervals=[(p['start'],p['end'])]
    for new in (s for a in added for s in a['chinese'] if s['blockId']==p['blockId']):
     intervals=[piece for lo,hi in intervals for piece in ((lo,min(hi,new['start'])),(max(lo,new['end']),hi)) if piece[0]<piece[1]]
    remaining.extend({'blockId':p['blockId'],'start':lo,'end':hi,'text':zb[p['blockId']]['text'][lo:hi]} for lo,hi in intervals)
   if not remaining:continue
   g=g|{'chinese':remaining,'relation':f'0 English blocks : {len(remaining)} withheld Chinese spans'}
  if not g.get('chinese'):
   g=g|{'englishBlockIds':[k for k in g['englishBlockIds'] if k not in new_ids]}
   if not g['englishBlockIds']:continue
  kept.append(g)
 current.setdefault('resolutions',[]).extend(resolutions)
 current['groups']=kept+added;current.setdefault('reviewUpdates',[]).append({'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'addedGroups':len(added),'resolvedWithoutTranslation':len(resolutions),'addedEnglishBlocks':sum(len(g['englishBlockIds']) for g in added),'method':'model-agent whole-speech semantic source review'})
 target.write_text(json.dumps(current,ensure_ascii=False,separators=(',',':'))+'\n')
 return {'work':eid,'groups':len(added),'resolvedWithoutTranslation':len(resolutions),'englishBlocks':sum(len(g['englishBlockIds']) for g in added)}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--records',type=Path,default=ROOT/'data/alignment-records');ap.add_argument('--review',type=Path,required=True,action='append');args=ap.parse_args()
 for path in args.review:print(json.dumps(apply(path,args.records)))
