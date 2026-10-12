import json,sys,unittest,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.alignment.provenance import read_assignment,exact_span,check_no_overlap

class AlignedDataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.catalog=json.loads((ROOT/'data/aligned-collection/manifest.json').read_text())['works']
 def test_all_english_preserved_exactly_once_in_order(self):
  self.assertEqual(len(self.catalog),39)
  for m in self.catalog:
   original=read_assignment(ROOT/'data/english-collection'/f'{m["id"]}.js');aligned=read_assignment(ROOT/m['file']);rows=[r for s in aligned['sections'] for r in s['rows']]
   originals=[b for s in original['sections'] for b in s['blocks']];groups=collections.OrderedDict()
   for row in rows:groups.setdefault(row['english']['blockId'],[]).append(row['english'])
   self.assertEqual(list(groups),[b['id'] for b in originals],m['id'])
   for b in originals:
    cursor=0
    for span in groups[b['id']]:self.assertEqual(span['start'],cursor);self.assertEqual(span['text'],b['text'][span['start']:span['end']]);cursor=span['end']
    self.assertEqual(cursor,len(b['text']))
 def test_exact_chinese_no_repeated_consumption(self):
  for m in self.catalog:
   work=read_assignment(ROOT/m['file']);source=read_assignment(ROOT/'data/chinese-collection/works'/f'{work["chineseId"]}.js');blocks={b['id']:b for s in source['sections'] for b in s['blocks']};spans=[]
   for g in work['groups']:
    self.assertIn(g['status'],('semantically_reviewed','automatically_aligned'))
    self.assertTrue(g['rowIds']);self.assertEqual(g['chineseText'],'\n'.join(exact_span(blocks,s) for s in g['chinese']))
    if g['status']=='semantically_reviewed':self.assertTrue(g['rationale'])
    spans+=g['chinese']
   check_no_overlap(spans)
 def test_whole_blocks_and_consistent_coverage(self):
  for m in self.catalog:
   work=read_assignment(ROOT/m['file']);rows=[r for s in work['sections'] for r in s['rows']];ids=[r['id'] for r in rows]
   self.assertEqual(len(ids),len(set(ids)))
   for row in rows:self.assertEqual(row['id'],row['english']['blockId']);self.assertEqual(row['english']['start'],0)
   self.assertEqual(m['englishUnits'],len(rows))
   self.assertEqual(m['englishUnits'],m['reviewedUnits']+m['automaticUnits']+m['unresolvedUnits'])
   self.assertTrue(all(r['groupId'] is None for r in rows if r['status']=='unresolved'))
 def test_every_play_has_alignment_records_and_some_matched_speech(self):
  for m in self.catalog:
   self.assertTrue((ROOT/'data/alignment-records'/f'{m["id"]}.json').exists(),m['id'])
   self.assertGreater(m['matchedSpeechUnits'],0,m['id'])
 def test_reviewed_gap_closures(self):
  works={m['id']:m for m in self.catalog}
  self.assertEqual(works['midsummer']['matchedSpeechUnits'],521)
  self.assertEqual(works['midsummer']['speechUnits'],521)
  self.assertEqual(works['pericles']['matchedSpeechUnits'],669)
  work=read_assignment(ROOT/works['pericles']['file'])
  pending=[r for sec in work['sections'] for r in sec['rows'] if r['kind']=='speech' and r['status']=='unresolved']
  self.assertEqual(len(pending),1)
  self.assertEqual(pending[0]['english']['text'],'SCENE I:')
 def test_play_catalogs_only(self):
  for name in ('english','chinese'):
   catalog=json.loads((ROOT/f'data/{name}-collection/catalog.json').read_text());self.assertEqual(len(catalog),39);self.assertTrue(all(w['kind']=='play' for w in catalog))

class BuilderGuardTests(unittest.TestCase):
 def reject(self,group):
  import tempfile,subprocess
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);(base/'records').mkdir();(base/'records/hamlet.json').write_text(json.dumps({'groups':[group]}))
   result=subprocess.run([sys.executable,str(ROOT/'scripts/alignment/build_reader.py'),'--candidates',str(base/'records'),'--out',str(base/'out')],capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0,result.stdout);return result.stderr
 def fixture(self):
  work=read_assignment(ROOT/'data/english-collection/hamlet.js');block=work['sections'][0]['blocks'][1]
  fixture=json.loads((ROOT/'tests/fixtures/speech-turn-fixtures.json').read_text())['fixtures'][0]
  return {'englishBlockIds':[block['id']],'english':[{'blockId':block['id'],'start':0,'end':len(block['text']),'text':block['text']}],'chinese':fixture['chinese'],'status':'automatically_aligned'}
 def test_unresolved_records_are_not_promoted(self):
  group=self.fixture();group['status']='unresolved';self.assertIn('unaccepted alignment status',self.reject(group))
 def test_partial_english_span_cannot_label_whole_speech(self):
  group=self.fixture();group['english'][0]['end']-=1;group['english'][0]['text']=group['english'][0]['text'][:-1];self.assertIn('partial English span',self.reject(group))
 def test_image_glyph_class_is_preserved(self):
  sys.path.insert(0,str(ROOT/'scripts/alignment'))
  from build_reader import chinese_html
  blocks={'z':{'text':'a中b','html':'<p>a<img class="epub-image epub-inline" src="data/chinese-collection/images/glyph.png" alt="字"/>中b</p>'}}
  markup=chinese_html(blocks,[{'blockId':'z','start':0,'end':3,'text':'a中b'}]);self.assertIn('epub-inline',markup);self.assertIn('glyph.png',markup)
 def test_cross_section_shared_translation_rejected(self):
  group=self.fixture();group['englishBlockIds'].append('hamlet:1.2:2');group.pop('english');self.assertIn('crosses English sections',self.reject(group))

if __name__=='__main__':unittest.main()
