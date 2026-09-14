import unittest

from hive_mind_os.roblox_profile import ProfileStatus, RobloxProfile

D = "sha256:" + "a" * 64


class RobloxProfileTests(unittest.TestCase):
    def profile(self, **changes):
        values = {
            "profile_id": "roblox.rojo.v1",
            "profile_selection_receipt_digest": D,
            "source_refs": ("ref:source/rojo", "ref:rights/fixture"),
            "toolchain_versions": {"rojo": "7.5.1"},
            "executable_paths": {"rojo": "C:/tools/rojo.exe"},
            "executable_digests": {"rojo": D},
            "image_digest": D,
            "project_manifest_paths": ("default.project.json",),
            "source_roots": ("src",),
            "package_lock_digests": (D,),
            "build_commands": (("C:/tools/rojo.exe", "build", "-o", "out.rbxlx"),),
            "static_check_commands": (("C:/tools/rojo.exe", "sourcemap"),),
            "artifact_paths": ("out.rbxlx",),
            "asset_manifest_digest": D,
            "runtime_requirements": {
                "host": "dedicated-windows",
                "asset_rights_refs": ["ref:rights/fixture"],
            },
            "capability_status": ProfileStatus.STATIC_VALIDATED,
        }
        values.update(changes)
        return RobloxProfile(**values)

    def test_complete_sealed_static_profile_is_still_not_runtime_evidence(self):
        profile = self.profile()
        self.assertEqual(profile.capability_status, ProfileStatus.STATIC_VALIDATED)
        self.assertNotIn("PRODUCTION", profile.capability_status.value)

    def test_changed_tool_missing_lock_and_injected_command_are_rejected(self):
        with self.assertRaises(ValueError):
            self.profile(executable_digests={"rojo": "unsealed"})
        with self.assertRaises(ValueError):
            self.profile(package_lock_digests=())
        with self.assertRaises(ValueError):
            self.profile(build_commands=(("powershell", "-Command", "download"),))

    def test_escape_path_is_rejected(self):
        with self.assertRaises(ValueError):
            self.profile(artifact_paths=("../other-tenant/game.rbxlx",))


if __name__ == "__main__":
    unittest.main()
