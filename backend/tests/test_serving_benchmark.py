"""Exercise the actual backend adapter with synthetic records and deterministic logits."""
import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import config
from benchmark_serving import benchmark_serving, plans
from cross_encoder import CrossEncoderScorer
from test_serving_cross_encoder import snapshot, FakeModel

class ServingBenchmarkTest(unittest.TestCase):
 def inputs(self):
  snap=snapshot()
  snap.index.at[1,'evidence']=[dict(text='Dialysis is not available at this specialized hospital.',
      field='procedure',pos=0,evidence_status='usable')]
  queries=pd.DataFrame([dict(query_id=s,service='dialysis',latitude=26.9,longitude=75.8,split=s,group_id=s) for s in ['dev','test']])
  qrels=pd.DataFrame([dict(query_id=s,unique_id=u,relevance=g) for s in ['dev','test']
                     for u,g in [('near',3),('far',0),('blocked',0),('outside',3)]])
  configs=[('baseline',dict(method='cross_encoder',model='fake',guard='off',text_weight=4/7,travel_multiplier=1.)),
           ('explicit',dict(method='cross_encoder',model='fake',guard='explicit',text_weight=4/7,travel_multiplier=1.))]
  return snap,queries,qrels,configs
 def test_real_serving_adapter_excludes_negatives_and_restores_config(self):
  snap,q,labels,cfg=self.inputs();original=config.CLAIM_GUARD_POLICY
  with tempfile.TemporaryDirectory() as tmp:
   report=benchmark_serving(snap,q,labels,Path(tmp)/'run',cfg,CrossEncoderScorer(model=FakeModel()),'synthetic')
   self.assertEqual(report['winner'],'explicit')
   per=pd.read_csv(Path(tmp)/'run'/'test_per_query.csv')
   self.assertTrue(per.candidate_recall_pool.isna().all())
   raw=json.loads((Path(tmp)/'run'/'test_responses_explicit.json').read_text())
   self.assertNotIn('far',[r['id'] for r in raw[0]['response']['results']])
  self.assertEqual(config.CLAIM_GUARD_POLICY,original)
 def test_unjudged_serving_data_never_selects_winner(self):
  snap,q,_,cfg=self.inputs()
  with tempfile.TemporaryDirectory() as tmp:
   report=benchmark_serving(snap,q,None,Path(tmp)/'run',cfg,CrossEncoderScorer(model=FakeModel()),'synthetic')
   self.assertIsNone(report['winner'])
 def test_plan_includes_exact_old_default_and_policy_ablations(self):
  p=plans()
  self.assertEqual(p[0][0],'baseline')
  self.assertEqual(p[0][1]['guard'],'off')
  self.assertEqual(p[0][1]['text_weight'],4/7)
  self.assertEqual({c['guard'] for _,c in p},{'off','explicit','strict'})
  self.assertEqual(len(p),len({tuple(c.values()) for _,c in p}))
