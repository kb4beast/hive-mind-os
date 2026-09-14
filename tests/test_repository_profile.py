import tempfile
import unittest
from pathlib import Path

from hive_mind_os.repository_profile import (CapabilityGrant, CapabilityReport, CapabilityStatus, HostIdentity, HostToolBinding, ProfileCapability, RepositoryProfile, RepositoryProfileError, RepositoryProfileStore)

D = "sha256:" + "a" * 64

def profile(root, **changes):
    base = dict(profile_id="host.profile", identity=HostIdentity("tenant.one", "repo.one", "host.issuer", D), repository_root=str(root), workspace_root=str(root.parent / "work"), state_root=str(root.parent / "state"), cache_root=str(root.parent / "cache"), grants=(CapabilityGrant(ProfileCapability.LOCAL_BUILD, "grant.build", D),), tools=(HostToolBinding("oci.runner", "absent", None, None, "linux", ("oci", "{workspace}"), ("{workspace}",), status=CapabilityStatus.UNAVAILABLE), HostToolBinding("rojo.cli", "absent", None, None, "windows", ("rojo", "build"), (), status=CapabilityStatus.UNAVAILABLE), HostToolBinding("studio.vm", "absent", None, None, "windows", ("studio",), (), status=CapabilityStatus.UNAVAILABLE)), reports=(CapabilityReport("oci.runner", CapabilityStatus.UNAVAILABLE, "not installed"),), external_destinations=(), sensitivity="unknown")
    base.update(changes); return RepositoryProfile(**base)

class RepositoryProfileTests(unittest.TestCase):
    def test_host_identity_digest_and_read_only_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "target"; root.mkdir(); item = profile(root)
            self.assertTrue(item.profile_digest.startswith("sha256:")); self.assertTrue(item.allows(ProfileCapability.READ_ONLY_PLAN)); self.assertFalse(item.allows(ProfileCapability.CODE_PR))
            self.assertFalse(item.allows(ProfileCapability.LEARNING_EXPORT, destination="https://example.invalid"))
    def test_external_profiles_have_distinct_subject_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "target"; root.mkdir(); a = profile(root)
            b = profile(root, identity=HostIdentity("tenant.two", "repo.two", "host.issuer", D))
            self.assertNotEqual(a.profile_digest, b.profile_digest)
            with self.assertRaises(RepositoryProfileError):
                HostIdentity("tenant.one", "repo.one", "repo.one", D)
    def test_target_owned_and_root_escape_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "target"; root.mkdir()
            with self.assertRaises(RepositoryProfileError): profile(root, state_root=str(root / "state"))
            with self.assertRaises(RepositoryProfileError): profile(root, workspace_root=str(root.parent / "same"), state_root=str(root.parent / "same"))
    def test_git_common_dir_and_alternate_paths_cannot_be_profile_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "target"; root.mkdir(); control = Path(temp) / "control"; control.mkdir()
            (root / ".git").write_text("gitdir: ../control\n", encoding="utf-8")
            with self.assertRaises(RepositoryProfileError): profile(root, state_root=str(control / "state"))
    def test_unknown_command_and_destination_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "target"; root.mkdir()
            with self.assertRaises(RepositoryProfileError): profile(root, tools=(HostToolBinding("bad.command", "v1", "relative.exe", D, "x", ("x",), (), status=CapabilityStatus.UNTESTED),))
            with self.assertRaises(RepositoryProfileError): profile(root, external_destinations=("http://bad",))
    def test_revocation_is_checked_at_next_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "target"; root.mkdir(); item = profile(root, grants=(CapabilityGrant(ProfileCapability.CODE_PR, "grant.pr", D, revoked=True),))
            self.assertFalse(item.allows(ProfileCapability.CODE_PR))
    def test_atomic_store_never_activates_partial_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "target"; root.mkdir(); store = RepositoryProfileStore(Path(temp) / "host-profiles", repository_root=root); item = profile(root)
            stored = store.write(item); self.assertTrue(stored.is_file()); self.assertEqual(store.read_document(item.profile_id)["profile_digest"], item.profile_digest)
            self.assertFalse(any(path.suffix == ".tmp" for path in stored.parent.iterdir()))
            with self.assertRaises(Exception): RepositoryProfileStore(root / "host-profiles", repository_root=root)

if __name__ == "__main__": unittest.main()
