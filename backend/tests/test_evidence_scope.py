import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence_support import claim_status,supported_items

class ScopeTest(unittest.TestCase):
 def test_missing_and_unknown(self):
  self.assertEqual(supported_items(None,'mri')[0],[])
  self.assertEqual(claim_status('A statement','unknown'),'unreviewed')
 def test_unrelated_negation_does_not_leak(self):
  self.assertEqual(claim_status('No parking. MRI available.','mri'),'support')
 def test_policies_separate_uncertain_referral_from_denial(self):
  e=[dict(text='Patients referred elsewhere for MRI.',evidence_status='usable')]
  self.assertEqual(len(supported_items(e,'mri','explicit')[0]),1)
  self.assertEqual(len(supported_items(e,'mri','strict')[0]),0)
 def test_field_membership_is_preserved(self):
  e=[dict(text='MRI available.',evidence_status='elsewhere')]
  self.assertEqual(supported_items(e,'mri')[0],[])
