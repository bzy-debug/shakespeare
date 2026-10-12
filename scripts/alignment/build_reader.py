#!/usr/bin/env python3
"""Build plays-only, whole-English-block bilingual reading data.

No sentence segmentation: every original English block is rendered exactly once.
Alignment records cite unchanged Chinese source spans, never generated translation.
"""
from pathlib import Path
import argparse,html,json,hashlib
from html.parser import HTMLParser
from provenance import read_assignment,exact_span,check_no_overlap
ROOT=Path(__file__).resolve().parents[2]

def write_js(path,name,value):
 raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
 path.write_text(f'window.{name} = {raw};\n')

class ImagePositions(HTMLParser):
 def __init__(self,markup):
  super().__init__(convert_charrefs=True);self.pos=0;self.images=[];self.feed(markup)
 def handle_data(self,text):self.pos+=len(text)
 def handle_starttag(self,tag,attrs):
  if tag=='img':self.images.append((self.pos,dict(attrs)))

def chinese_html(blocks,spans):
 result=[]
 for s in spans:
  b=blocks[s['blockId']];exact_span(blocks,s);a,z=s['start'],s['end'];cursor=a;parts=[]
  for pos,attrs in ImagePositions(b['html']).images:
   if a<=pos<z:
    parts.append(html.escape(b['text'][cursor:pos]));src=attrs.get('src','')
    if not src.startswith('data/chinese-collection/images/'):raise ValueError('Unsafe image source')
    parts.append('<img src="'+html.escape(src,quote=True)+'" alt="'+html.escape(attrs.get('alt',''),quote=True)+'" class="'+html.escape(attrs.get('class',''),quote=True)+'">');cursor=pos
  parts.append(html.escape(b['text'][cursor:z]));result.append(''.join(parts))
 return '\n'.join(result)

def records(data):
 if 'groups' in data:return data['groups']
 return [g for groups in data.get('results',{}).values() for g in groups]

def build(candidates,out):
 zcat=json.loads((ROOT/'data/chinese-collection/catalog.json').read_text());ecat=json.loads((ROOT/'data/english-collection/catalog.json').read_text());summaries=[]
 out.mkdir(parents=True,exist_ok=True)
 for meta in ecat:
  if meta['kind']!='play':continue
  eid=meta['id'];zmeta=next(z for z in zcat if z['kind']=='play' and z['englishId']==eid)
  en=read_assignment(ROOT/meta['file']);zh=read_assignment(ROOT/zmeta['file']);eb={b['id']:b for s in en['sections'] for b in s['blocks']};zb={b['id']:b for s in zh['sections'] for b in s['blocks']}
  sections=[];rows=[]
  for s in en['sections']:
   rr=[{'id':b['id'],'english':{'blockId':b['id'],'start':0,'end':len(b['text']),'text':b['text']},'speaker':b.get('speaker'),'kind':b['kind'],'groupId':None,'status':'unresolved'} for b in s['blocks']]
   sections.append({k:v for k,v in s.items() if k!='blocks'}|{'rows':rr});rows.extend(rr)
  byid={r['id']:r for r in rows};order={r['id']:i for i,r in enumerate(rows)};section_by_id={r['id']:s['id'] for s in sections for r in s['rows']};groups=[];used=set();zhspans=[]
  path=candidates/f'{eid}.json'
  data=json.loads(path.read_text()) if path.exists() else {}
  expected=data.get('provenance',{}).get('englishSourceSha256')
  if expected and expected!=hashlib.sha256((ROOT/meta['file']).read_bytes()).hexdigest():raise ValueError(f'{eid}: stale English alignment source')
  for i,g in enumerate(records(data)):
   zz=g.get('chinese',g.get('zh',[]));ee=g.get('english',g.get('en',[]));ids=g.get('englishBlockIds') or list(dict.fromkeys(p['blockId'] for p in ee))
   if not ids or not zz:continue
   status=g.get('status')
   if status not in ('automatically_aligned','semantically_reviewed'):
    raise ValueError(f'{eid}: unaccepted alignment status {status!r}')
   for span in ee:
    exact_span(eb,span)
    if span['start']!=0 or span['end']!=len(eb[span['blockId']]['text']):
     raise ValueError(f'{eid}: partial English span cannot label a whole speech')
   if any(k not in eb for k in ids):raise ValueError(f'{eid}: unknown English block')
   if len(ids)!=len(set(ids)):raise ValueError(f'{eid}: repeated English block inside group')
   ids=sorted(ids,key=order.get)
   if len({section_by_id[k] for k in ids})!=1:raise ValueError(f'{eid}: group crosses English sections')
   if used.intersection(ids):raise ValueError(f'{eid}: English block assigned twice')
   for p in zz:exact_span(zb,p)
   check_no_overlap(zz);zhspans.extend(zz);used.update(ids)
   group={'id':f'{eid}-turn-{i}','english':[byid[k]['english'] for k in ids],'chinese':zz,'rowIds':ids,'status':status,'kind':g.get('kind'),'rationale':g.get('rationale',''),'relation':f'{len(ids)}:{len(zz)}','chineseText':'\n'.join(exact_span(zb,p) for p in zz),'chineseHtml':chinese_html(zb,zz)}
   if g.get('sourceVariants'):group['sourceVariants']=g['sourceVariants']
   groups.append(group)
   for k in ids:byid[k]['groupId']=group['id'];byid[k]['status']=status
  for resolution in data.get('resolutions',[]):
   span=resolution['english'];key=span['blockId'];exact_span(eb,span)
   if span['start']!=0 or span['end']!=len(eb[key]['text']):raise ValueError(f'{eid}: partial resolution span')
   if key in used:raise ValueError(f'{eid}: resolution conflicts with accepted group or resolution')
   if resolution.get('status') not in ('source_omission','source_artifact') or not resolution.get('rationale') or not resolution.get('evidence'):
    raise ValueError(f'{eid}: resolution requires reviewed classification and evidence')
   used.add(key);byid[key]['status']=resolution['status'];byid[key]['resolution']=resolution
  check_no_overlap(zhspans)
  counts={'englishUnits':len(rows),'speechUnits':sum(r['kind']=='speech' for r in rows),'reviewedUnits':sum(r['status']=='semantically_reviewed' for r in rows),'automaticUnits':sum(r['status']=='automatically_aligned' for r in rows),'unresolvedUnits':sum(r['status']=='unresolved' for r in rows),'groups':len(groups),'resolvedWithoutTranslationUnits':sum(r['status'] in ('source_omission','source_artifact') for r in rows)}
  counts['matchedSpeechUnits']=sum(r['kind']=='speech' and r['groupId'] is not None for r in rows)
  counts['speechCharacters']=sum(len(r['english']['text']) for r in rows if r['kind']=='speech')
  counts['matchedSpeechCharacters']=sum(len(r['english']['text']) for r in rows if r['kind']=='speech' and r['groupId'] is not None)
  counts['chineseCharacters']=sum(s['end']-s['start'] for s in zhspans)
  work={'id':eid,'title':meta['title'],'chineseId':zmeta['id'],'chineseTitle':zmeta['title'],'translator':zmeta['translator'],'source':{k:meta[k] for k in ('sourceUrl','sourceLabel') if k in meta},'alignmentPolicy':'Whole English speech blocks, with separate stage blocks; no within-speech sentence alignment. Chinese uses exact source spans. Uncertain mappings remain unresolved.','sourceHashes':{'english':hashlib.sha256((ROOT/meta['file']).read_bytes()).hexdigest(),'chinese':hashlib.sha256((ROOT/zmeta['file']).read_bytes()).hexdigest(),'alignmentRecords':hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None},'sections':sections,'groups':groups,'counts':counts}
  raw=json.dumps(work,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c');(out/f'{eid}.js').write_text('window.SHAKESPEARE_ALIGNED = window.SHAKESPEARE_ALIGNED || {};\nwindow.SHAKESPEARE_ALIGNED['+json.dumps(eid)+'] = '+raw+';\n')
  summaries.append({'id':eid,'chineseId':zmeta['id'],'title':meta['title'],'file':f'data/aligned-collection/{eid}.js',**counts})
 # Only generated output files are cleaned here; preserve unrelated artifacts.
 allowed={m['id']+'.js' for m in summaries}|{'catalog.js'}
 for p in out.glob('*.js'):
  if p.name not in allowed:p.unlink()
 write_js(out/'catalog.js','SHAKESPEARE_ALIGNED_CATALOG',summaries)
 manifest={'schemaVersion':2,'unit':'original English block','policy':'plays only; speech-block alignment, not sentence alignment','works':summaries,'totals':{k:sum(w[k] for w in summaries) for k in ('englishUnits','speechUnits','matchedSpeechUnits','reviewedUnits','automaticUnits','unresolvedUnits','resolvedWithoutTranslationUnits','speechCharacters','matchedSpeechCharacters','chineseCharacters')}}
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps(manifest['totals']))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--candidates',type=Path,default=ROOT/'data/alignment-records');ap.add_argument('--out',type=Path,default=ROOT/'data/aligned-collection');args=ap.parse_args();build(args.candidates,args.out)
