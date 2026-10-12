#!/usr/bin/env python3
"""Overlay source-exact editorial corrections without double-using text.

A conflicting automatic group is wholly displaced, never partially reassigned.
Its remaining English blocks are explicitly unresolved in the reading data.
"""
from pathlib import Path
import argparse,json,collections,hashlib
from provenance import read_assignment,exact_span
ROOT=Path(__file__).resolve().parents[2]

def groups(data):return data.get('groups',[g for gg in data.get('results',{}).values() for g in gg])
def ids(g):return g.get('englishBlockIds') or list(dict.fromkeys(s['blockId'] for s in g.get('english',g.get('en',[]))))
def spans(g):return g.get('chinese',g.get('zh',[]))
def overlaps(a,b):return any(x['blockId']==y['blockId'] and max(x['start'],y['start'])<min(x['end'],y['end']) for x in a for y in b)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--auto',type=Path,required=True);ap.add_argument('--review',type=Path,action='append',default=[]);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True);reviews=collections.defaultdict(list)
 allowed={w['id'] for w in json.loads((Path(__file__).resolve().parents[2]/'data/english-collection/catalog.json').read_text()) if w['kind']=='play'}
 for path in args.review:
  d=json.loads(path.read_text())
  for g in d.get('fixtures',groups(d)):
   keys=ids(g)
   if keys:
    eid=keys[0].split(':')[0]
    ew=read_assignment(ROOT/'data/english-collection'/f'{eid}.js');eb={b['id']:b for sec in ew['sections'] for b in sec['blocks']}
    for span in g.get('english',g.get('en',[])):exact_span(eb,span)
    prior={k for old in reviews[eid] for k in ids(old)}
    if set(keys)<=prior:continue
    if set(keys)&prior:raise ValueError('Partially overlapping reviewed whole turns')
    item=g|{'englishBlockIds':keys,'status':'semantically_reviewed'}
    item.pop('english',None);item.pop('en',None)
    reviews[eid].append(item)
 summary={}
 for path in sorted(args.auto.glob('*.json')):
  if path.stem not in allowed:continue
  d=json.loads(path.read_text())
  if not ('groups' in d or 'results' in d):continue
  original=groups(d);eid=d.get('work',d.get('id',path.stem))
  if isinstance(eid,dict):eid=eid['id']
  source_path=ROOT/'data/english-collection'/f'{eid}.js';source=read_assignment(source_path);eb={b['id']:b for section in source['sections'] for b in section['blocks']}
  for g in original:
   for span in g.get('english',g.get('en',[])):exact_span(eb,span)
  reviewed=reviews.get(eid,[]);used={i for g in reviewed for i in ids(g)};zz=[s for g in reviewed for s in spans(g)];accepted=[];displaced=[]
  for g in original:
   if used.intersection(ids(g)) or overlaps(spans(g),zz):displaced.append(g.get('id',ids(g)))
   else:accepted.append(g)
  lean=[]
  for g in reviewed+accepted:
   lean.append({k:g[k] for k in ('englishBlockIds','chinese','status','kind','method','rationale','relation','risks','matchingPool') if k in g})
  output={'schemaVersion':1,'work':eid,'unit':'whole English block','provenance':d.get('provenance',{})|{'englishSourceSha256':hashlib.sha256(source_path.read_bytes()).hexdigest()},'groups':lean,'displacedAutomaticGroups':displaced}
  (args.out/(eid+'.json')).write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n');summary[eid]={'reviewedGroups':len(reviewed),'automaticGroups':len(accepted),'displacedGroups':len(displaced)}
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
