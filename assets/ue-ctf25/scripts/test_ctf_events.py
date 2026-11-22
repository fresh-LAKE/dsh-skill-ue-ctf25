"""Regression checks; all generated data and mock bridge exports stay in temp dirs.

Run: python -B -m unittest discover -s scripts -p test_ctf_events.py
"""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import ctf_events as c


class EventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ue-ctf25-test-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def package(self, rec=None):
        rec = rec or c.template("flag_on")
        rec.obj = 0
        return c.Package(bytes([6, 4, 1, 0]), 0x30,
                         [c.new_event([rec], [])], [c.Obj(0, 2, "Mario")],
                         b"TYAL" + struct.pack("<I", len(c.TYAL)) + c.TYAL + b"!DNE")

    def candidate(self):
        out = self.folder / "candidate.json"
        self.package().save(out)
        return out

    def test_all_source_roundtrips_and_templates(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(["ctf_events.py", "selftest"]), 0)

    def test_invalid_envelope_is_rejected(self):
        path = self.candidate()
        original = json.loads(path.read_text(encoding="utf-8"))
        for key, value in [("SHA256", "0" * 64), ("Length", 1), ("Base64", "!!!")]:
            with self.subTest(key=key):
                doc = json.loads(json.dumps(original))
                doc["Formats"][0][key] = value
                path.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaises(ValueError):
                    c.Package.load(path)
        original["Formats"] *= 2
        path.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaises(ValueError):
            c.Package.load(path)

    def test_invalid_binary_lengths_are_rejected(self):
        original = self.package().to_bytes()
        # Event, record and parameter lengths respectively; none may be trusted
        # without checking the enclosing record boundary and count.
        for offset, fmt, value in [(24, "<h", -14), (38, "<H", 16),
                                   (54, "<H", 36), (54, "<H", 0)]:
            with self.subTest(offset=offset, value=value):
                data = bytearray(original)
                struct.pack_into(fmt, data, offset, value)
                with self.assertRaises(ValueError):
                    c.Package.from_bytes(data)
        end = 24 + struct.unpack_from("<I", original, 20)[0]
        data = bytearray(original[:end] + b"\0\0" + original[end:])
        struct.pack_into("<I", data, 20, end - 24 + 2)
        with self.assertRaises(ValueError):
            c.Package.from_bytes(data)

    def test_missing_embedded_object_and_duplicate_ids(self):
        pkg = self.package(c.template("overlap_group"))
        self.assertTrue(any("t1 object id" in e for e in pkg.verify()))
        pkg.objects.append(c.Obj(2, 3, "Group.Water", group_id=5))
        self.assertEqual(pkg.verify(), [])
        pkg.objects.append(c.Obj(2, 2, "Duplicate"))
        self.assertTrue(any("duplicate" in e for e in pkg.verify()))

    def test_immediate_check_uses_child_flag(self):
        rec = c.Rec(True, bytearray.fromhex(
            "1000fffff0ff00000000200000000000"), [])
        pkg = self.package(rec)
        struct.pack_into("<H", pkg.events[0].header, 8, 1)
        self.assertEqual(pkg.verify(), [])  # Group hierarchy alone is allowed.
        struct.pack_into("<H", pkg.events[0].header, 4, 0x8000)
        self.assertTrue(any("immediate" in e for e in pkg.verify()))
        struct.pack_into("<H", pkg.events[0].header, 8, 0)
        self.assertTrue(any("immediate" in e for e in pkg.verify()))

    def test_empty_icon_payload_roundtrips(self):
        pkg = self.package()
        pkg.objects[0].icon_tag = b"OIC2"
        data = pkg.to_bytes()
        self.assertEqual(c.Package.from_bytes(data).to_bytes(), data)

    def test_action_names_do_not_use_condition_opcodes(self):
        rec = c.Rec(False, bytearray(14), [])
        struct.pack_into("<hh", rec.header, 2, -1, -1)
        self.assertTrue(rec.text({0: "Mario"}).startswith("? "))

    def test_truncated_metadata_is_rejected(self):
        data = self.package().to_bytes()
        for marker, offset in [(b"SJBO", 8), (b"TYAL", 8)]:
            bad = bytearray(data)
            struct.pack_into("<I", bad, data.index(marker) + offset - 4, 0x7fffffff)
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                c.Package.from_bytes(bad)

    def test_selftest_does_not_skip_bad_events(self):
        path = self.candidate()
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["Formats"][0]["SHA256"] = "0" * 64
        path.write_text(json.dumps(doc), encoding="utf-8")
        output = io.StringIO()
        with patch.object(c, "REF", self.folder), patch.object(c, "PROVENANCE", {}), \
                contextlib.redirect_stdout(output):
            self.assertEqual(c.main(["ctf_events.py", "selftest"]), 1)
        self.assertIn("FAIL candidate.json", output.getvalue())

    def test_diff_accepts_windows_drive_colons(self):
        pkg = self.package()
        output = io.StringIO()
        with patch.object(c.Package, "load", return_value=pkg) as load, \
                contextlib.redirect_stdout(output):
            self.assertEqual(c.main(["ctf_events.py", "diff",
                                     r"D:\some folder\left.json:0",
                                     r"C:\right.json:0"]), 0)
        self.assertEqual(load.call_args_list[0].args, (r"D:\some folder\left.json",))
        self.assertEqual(load.call_args_list[1].args, (r"C:\right.json",))

    def test_example_passes_both_verifiers(self):
        out = self.folder / "infinite-jump.json"
        for script, args in [("example_infinite_jump.py", [str(out)]),
                             ("ctf_events.py", ["verify", str(out)]),
                             ("verify_events.py", [str(out)])]:
            result = subprocess.run([sys.executable, "-B", "-X", "utf8",
                                     str(c.HERE / script), *args],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"),
                         "requires Windows PowerShell; uses a mock bridge only")
    def test_import_wrapper_export_handling(self):
        candidate = self.candidate()
        # An old future-dated export must not hide the newly created readback.
        old = self.folder / "ctf-clipboard-old.json"
        shutil.copyfile(candidate, old)
        os.utime(old, (2200000000, 2200000000))
        bridge = self.folder / "MockBridge.ps1"
        wrapper = c.HERE / "ImportAndVerify.ps1"
        for scenario, statement, expected in [
            ("success", "", 0),
            ("export_failure", "exit 7", 1),
            ("ambiguous", "Copy-Item -LiteralPath $source -Destination (Join-Path $PSScriptRoot 'ctf-clipboard-extra.json')", 1),
            ("corrupt", "$doc = Get-Content -LiteralPath $dest -Raw | ConvertFrom-Json; $doc.Formats[0].SHA256 = 'bad'; $doc | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $dest -Encoding UTF8", 1),
        ]:
            with self.subTest(scenario=scenario):
                for name in ("ctf-clipboard-new.json", "ctf-clipboard-extra.json"):
                    (self.folder / name).unlink(missing_ok=True)
                bridge.write_text(
                    "param($Mode, $Path, $FormatName)\n"
                    "if ($Mode -eq 'Import') { exit 0 }\n"
                    "$source = Join-Path $PSScriptRoot 'candidate.json'\n"
                    "$dest = Join-Path $PSScriptRoot 'ctf-clipboard-new.json'\n"
                    "Copy-Item -LiteralPath $source -Destination $dest\n"
                    + statement + "\n", encoding="utf-8-sig")
                result = subprocess.run([
                    "powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
                    "-File", str(wrapper), "-Path", str(candidate), "-Bridge", str(bridge)],
                    capture_output=True)
                self.assertEqual(result.returncode, expected, result.stderr)


if __name__ == "__main__":
    unittest.main()
