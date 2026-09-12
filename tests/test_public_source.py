from pathlib import Path
import importlib.util
import tempfile
import unittest
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("public_source", Path(__file__).resolve().parents[1] / "scripts/check_public_source.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicSourceTests(unittest.TestCase):
    def test_private_binding_match_is_reported_without_value(self):
        rules = module.inspect("README.md", b"https://private-node.example", [b"private-node.example"])
        self.assertEqual(rules, ["private-host-binding"])

    def test_tailnet_address_and_private_key_are_detected(self):
        value = b"node." + b"tailabcd" + b".ts.net"
        self.assertIn("tailnet-address", module.inspect("src/test.txt", value, []))
        key = b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----"
        self.assertIn("private-key", module.inspect("src/test.txt", key, []))

    def test_operator_placeholders_are_allowed(self):
        self.assertEqual(module.inspect("README.md", b"YOUR-MACHINE.YOUR-TAILNET.ts.net and 127.0.0.1", []), [])

    def test_sensitive_files_are_rejected_even_without_secret_pattern(self):
        for path in (".env.local", ".local/sandbox/host.json", "sample.wav", "test-results/result.txt", "data.sqlite"):
            with self.subTest(path=path):
                self.assertTrue(module.inspect(path, b"", []))
        self.assertEqual(module.inspect(".env.example", b"placeholder", []), [])

    def test_required_binding_cannot_silently_disappear(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                module.private_values(Path(directory) / "missing.json", required=True)

    def test_private_ipv4_and_ipv6_addresses_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            binding = Path(directory) / "host.json"
            binding.write_text(json.dumps({"ip_addresses": ["192.0.2.8", "2001:db8::8"]}))
            private = module.private_values(binding)
            for address in (b"192.0.2.8", b"2001:db8::8", b"2001:0db8:0000:0000:0000:0000:0000:0008"):
                self.assertIn("private-host-binding", module.inspect("README.md", address, private))

    def test_required_binding_cannot_be_empty_or_omit_addresses(self):
        with tempfile.TemporaryDirectory() as directory:
            binding = Path(directory) / "host.json"
            for document in ({}, {field: "private-marker" for field in module.PRIVATE_FIELDS}):
                binding.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    module.private_values(binding, required=True)

    def test_binding_summary_does_not_echo_connection_metadata(self):
        helper_spec = importlib.util.spec_from_file_location("sandbox", Path(__file__).resolve().parents[1] / "scripts/sandbox.py")
        helper = importlib.util.module_from_spec(helper_spec)
        helper_spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as directory:
            binding = Path(directory) / "host.json"
            binding.write_text(json.dumps({"schema_version": 1, "ssh_hostname": "private-marker.example", "identity_file": "/private-key-path-marker"}))
            output = io.StringIO()
            with patch.object(helper, "BINDING", binding), patch("sys.argv", ["sandbox.py", "binding"]), redirect_stdout(output):
                helper.main()
            self.assertEqual(json.loads(output.getvalue()), {"configured": True, "schemaVersion": 1})
            self.assertNotIn("marker", output.getvalue())


if __name__ == "__main__":
    unittest.main()
