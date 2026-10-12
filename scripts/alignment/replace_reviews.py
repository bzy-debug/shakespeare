#!/usr/bin/env python3
"""Apply an explicit, hash-pinned semantic correction without dropping English.

The proposal names complete accepted groups through their English block IDs.
Every removed English block must be covered by reviewed replacement data or an
explicit source resolution. Original records are retained in a correction ledger.
"""
import argparse,hashlib,json,tempfile
from pathlib import Path
from add_reviews import apply,ROOT

def replace(path,records):
 proposal=json.loads(path.read_text());eid=proposal['workId'];target=records/f'{eid}.json';original=target.read_bytes();before=json.loads(original)
 if proposal.get('alignmentRecordsSha256')!=hashlib.sha256(original).hexdigest():raise ValueError('Correction baseline hash differs')
 ids=set(proposal.get('replacementEnglishBlockIds',[]))
 if not ids:raise ValueError('Explicit replacement English IDs required')
 removed=[];kept=[]
 for group in before['groups']:
  keys=set(group['englishBlockIds'])
  if group.get('chinese') and keys.intersection(ids):
   if not keys<=ids:raise ValueError('Correction must replace a complete accepted group')
   removed.append(group)
  else:kept.append(group)
 if {k for g in removed for k in g['englishBlockIds']}!=ids:raise ValueError('Replacement names unaccepted English block')
 covered={k for g in proposal['groups'] for k in g['englishBlockIds']}|{r['english']['blockId'] for r in proposal.get('resolutions',[])}
 if not ids<=covered:raise ValueError('Correction drops previously accepted English')
 with tempfile.TemporaryDirectory(dir=records.parent) as temp:
  temp=Path(temp);copy=before|{'groups':kept};copy.setdefault('reviewReplacements',[]).append({'proposalSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'baselineSha256':hashlib.sha256(original).hexdigest(),'removedGroups':removed})
  scratch=temp/f'{eid}.json';scratch.write_text(json.dumps(copy,ensure_ascii=False,separators=(',',':'))+'\n')
  result=apply(path,temp)
  # Commit the target only after all exact-source and conflict validation passes.
  if target.read_bytes()!=original:raise ValueError('Correction target changed during validation')
  scratch.replace(target)
 return result|{'replacedGroups':len(removed),'replacedEnglishBlocks':len(ids)}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--review',type=Path,required=True);parser.add_argument('--records',type=Path,default=ROOT/'data/alignment-records');args=parser.parse_args();print(json.dumps(replace(args.review,args.records)))
