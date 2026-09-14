import unittest
from hive_mind_os.cortex.repository.mission_bindings import MissionBindingDescriptor, ConfiguredMissionBindingsProvider, MissionBindingError
D="sha256:"+"d"*64
class ConfiguredMissionBindingTests(unittest.TestCase):
 def descriptor(self): return MissionBindingDescriptor("config",D,"tenant","repository","v1",(("adapter","v1"),),("provider",),"authority",D,"state")
 def test_wrong_tenant_blocks_before_resolver(self):
  called=[]; p=ConfiguredMissionBindingsProvider(self.descriptor(),lambda *_: called.append(True))
  with self.assertRaises(MissionBindingError): p.resolve({"tenant_id":"other","repository_id":"repository","configuration_digest":self.descriptor().digest},__import__('pathlib').Path('.'))
  self.assertFalse(called)
