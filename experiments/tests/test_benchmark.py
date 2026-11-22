import tempfile
import unittest
from pathlib import Path
import pandas as pd
from backend.evidence_support import claim_status, supported_items
from experiments.benchmark import validate_queries, benchmark, paired_interval
from experiments.challenge.build import build

class BenchmarkTest(unittest.TestCase):
 def test_guard_scope_and_exemptions(self):
  for text in ['Our hospital offers no-cost dialysis.', 'Not only dialysis but MRI is offered.',
               'No parking. Our dialysis unit is open.']:
   self.assertEqual(claim_status(text,'kidney-dialysis'),'support',text)
  for text,status in [('Patients referred for dialysis','indirect'),('Dialysis is planned','planned_or_historical'),
                       ('Dialysis is not offered','negative'),('Dialysis awareness campaign','indirect')]:
   self.assertEqual(claim_status(text,'kidney-dialysis'),status)
 def test_contradiction_cannot_be_hidden_by_positive(self):
  ev=[{'text':s,'evidence_status':'usable'} for s in ['Dialysis provided','Dialysis discontinued']]
  self.assertEqual(supported_items(ev,'kidney-dialysis')[0],[])
 def test_group_leakage_rejected(self):
  q=pd.DataFrame([dict(query_id='a',service='mri',latitude=20,longitude=80,split='dev',group_id='x'),
                  dict(query_id='b',service='mri',latitude=20,longitude=80,split='test',group_id='x')])
  with self.assertRaises(ValueError):validate_queries(q)
 def test_unlabelled_run_cannot_select_winner(self):
  with tempfile.TemporaryDirectory() as tmp:
   build(Path(tmp)/'input');root=Path(tmp)/'input'
   result=benchmark(pd.read_csv(root/'facilities.csv'),pd.read_csv(root/'evidence.csv'),
                    pd.read_csv(root/'queries.csv'),None,Path(tmp)/'out',methods=['rules'],data_kind='synthetic')
   self.assertIsNone(result['winner'])
 def test_paired_ci_preserves_query_pairing(self):
  p=pd.DataFrame([dict(query_id=q,method=m,group_id=q,ndcg_at_k_pool=v)
                  for q in ['a','b'] for m,v in [('baseline',.5),('candidate',.75)]])
  self.assertEqual(paired_interval(p,'baseline','candidate',draws=20)['delta'],.25)

 def test_all_skipped_attempts_are_checkpointed_after_model_failure(self):
  import json
  from unittest.mock import patch
  from experiments.benchmark import GuardedEngine
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'input';build(root)
   with patch.object(GuardedEngine,'score_service',side_effect=RuntimeError('simulated unavailable model')):
    report=benchmark(pd.read_csv(root/'facilities.csv'),pd.read_csv(root/'evidence.csv'),
       pd.read_csv(root/'queries.csv'),None,Path(tmp)/'out',methods=['rules','cross_encoder'],data_kind='synthetic')
   attempts=json.loads((Path(tmp)/'out'/'attempts.json').read_text())
   self.assertEqual(len(attempts),len(report['configs']))
   self.assertEqual(attempts[-1]['status'],'skipped_after_model_failure')
