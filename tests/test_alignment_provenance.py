"""Regression fixtures for alignment provenance, not corpus-wide accuracy claims."""
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.alignment.provenance import source_blocks,exact_span,validate_groups

class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold=[f for f in json.loads((ROOT/'tests/fixtures/speech-turn-fixtures.json').read_text())['fixtures'] if f['work']=='hamlet']
        cls.en,cls.zh=source_blocks('hamlet','part0037')
    def test_reviewed_gold_exact_source_spans(self):
        counts=validate_groups(self.gold,self.en,self.zh)
        self.assertEqual(counts['groups'],len(self.gold))
        self.assertGreaterEqual(counts['englishSpans'],len(self.gold))
    def test_all_cross_translator_turn_fixtures_have_exact_source_spans(self):
        data=json.loads((ROOT/'tests/fixtures/speech-turn-fixtures.json').read_text())
        from scripts.alignment.provenance import read_assignment
        for fixture in data['fixtures']:
            meta=data['sources'][fixture['work']]
            en=read_assignment(ROOT/meta['englishPath']);zh=read_assignment(ROOT/meta['chinesePath'])
            eb={b['id']:b for section in en['sections'] for b in section['blocks']}
            zb={b['id']:b for section in zh['sections'] for b in section['blocks']}
            validate_groups([fixture],eb,zb)
    def test_rejects_rephrased_translation(self):
        span=dict(self.gold[0]['chinese'][0]);span['text']+='伪造'
        with self.assertRaises(ValueError):exact_span(self.zh,span)
    def test_rejects_duplicate_consumption(self):
        with self.assertRaises(ValueError):validate_groups([self.gold[0],self.gold[0]],self.en,self.zh)
    def test_chinese_cannot_exist_without_english(self):
        group={**self.gold[0],'english':[]}
        with self.assertRaises(ValueError):validate_groups([group],self.en,self.zh)
    def test_review_evidence_required(self):
        group={**self.gold[0],'rationale':''}
        with self.assertRaises(ValueError):validate_groups([group],self.en,self.zh)

if __name__=='__main__':unittest.main()
