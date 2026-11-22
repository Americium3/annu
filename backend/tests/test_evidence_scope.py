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

 def test_access_convenience_is_not_service_denial(self):
  for text in ['No appointment is needed for MRI.', 'No waiting for MRI.',
               'Our hospital not only provides MRI but also CT.']:
   self.assertEqual(claim_status(text,'mri'),'support',text)

 def test_referral_center_is_not_an_outgoing_referral(self):
  text='Burns unit is a high-referral center for complex burns (thermal, electric and chemical) in coastal and central Karnataka'
  self.assertEqual(claim_status(text,'burns'),'support')
  self.assertEqual(claim_status(text,'burns',recognize_referral_centers=False),'indirect')
  self.assertEqual(claim_status('Patients referred elsewhere to a burns referral center.','burns'),'indirect')
