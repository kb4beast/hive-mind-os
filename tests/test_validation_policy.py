import unittest
from hive_mind_os.validation_policy import CheckPurpose, ValidationScope
D="sha256:"+"c"*64
class ValidationPolicyTests(unittest.TestCase):
 def test_scope_digest_binds_purpose(self):
  a=ValidationScope(D,D,D,D,None,CheckPurpose.DEVELOPER)
  b=ValidationScope(D,D,D,D,None,CheckPurpose.INTEGRATION)
  self.assertNotEqual(a.digest,b.digest)
