from pathlib import Path
from unittest import mock
import copy
import json
import io
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / "plugin/scripts"), str(BASE / "plugin/scripts/vendor")]
from cpr import catalog, codex, engine
from cpr.controller import Controller
from cpr.storage import Store, save, read
from catalog_fixture import seed


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "router")
        self.home = Path(self.temp.name) / "codex"
        self.home.mkdir()
        self.store.save({"codex_home": str(self.home), "gateway_port": 45678,
                         "keys": [{"id": "fixture", "label": "fixture", "key": "sk-test-" + "a" * 60}]})
        save(self.store.access_path, {"client": "fixture", "management": "fixture"})
        (self.home / "config.toml").write_text('model="gpt-6.2-sol"\nmodel_reasoning_effort="xhigh"\n')
        seed(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_catalog_projection_keeps_model_ids_and_tier_boundaries(self):
        state = catalog.prepare(self.store)
        routing = read(Path(state["catalog"]))
        client = read(Path(state["codex-catalog"]))
        self.assertIn("gpt-6.2-sol", {x["id"] for x in routing["codex-pro"]})
        self.assertIn("gpt-6.2-sol", {x["slug"] for x in client["models"]})
        self.assertNotIn("gpt-6.2-sol", {x["id"] for x in routing["codex-free"]})
        self.assertEqual(Path(state["catalog"]).stat().st_mode & 0o777, 0o600)
        engine.render(self.store)
        self.assertEqual(read(self.store.config_path)["models"], catalog.sources(self.store))

    def test_activation_inherits_current_model_and_writes_multiple_client_choices(self):
        with mock.patch("cpr.engine.models", return_value=["gpt-6.2-sol", "gpt-6.1-sol"]), \
             mock.patch.object(Controller, "status", return_value={"running": True, "accounts": ["fixture"]}), \
             mock.patch("cpr.codex.check_competing_writer"):
            Controller(self.store).dispatch("activate", {})
        import tomlkit
        config = tomlkit.parse((self.home / "config.toml").read_text())
        self.assertEqual(config["model"], "gpt-6.2-sol")
        self.assertEqual(config["model_reasoning_effort"], "xhigh")
        self.assertEqual(config["model_catalog_json"], str(catalog.client_path(self.store)))
        self.assertEqual({x["slug"] for x in read(catalog.client_path(self.store))["models"]}, {"gpt-6.2-sol", "gpt-6.1-sol"})
        codex.restore(self.store)
        self.assertNotIn("model_catalog_json", (self.home / "config.toml").read_text())

    def test_unknown_models_are_rejected_without_changing_user_choice(self):
        original = (self.home / "config.toml").read_bytes()
        with mock.patch("cpr.engine.models", return_value=["gpt-6.1-sol"]), \
             mock.patch.object(Controller, "status", return_value={"running": True, "accounts": ["fixture"]}):
            with self.assertRaises(ValueError):
                Controller(self.store).dispatch("activate", {"model": "gpt-6.2-sol"})
        self.assertEqual((self.home / "config.toml").read_bytes(), original)

    def test_failed_directory_download_keeps_last_valid_generation(self):
        before = catalog.prepare(self.store)
        with mock.patch("cpr.catalog.urllib.request.urlopen", side_effect=OSError):
            result = catalog.refresh(self.store)
        self.assertFalse(result["ok"])
        self.assertEqual(catalog.prepare(self.store)["generation"], before["generation"])

    def test_malformed_native_catalog_rejected(self):
        source = catalog.prepare(self.store)
        routing = read(Path(source["catalog"]))
        native = read(Path(source["codex-catalog"]))
        native["models"][0]["slug"] = "bad model\n"
        with self.assertRaises(ValueError):
            catalog.validate(routing, native)

    def test_engine_rejection_rolls_back_the_catalog_generation(self):
        previous = catalog.prepare(self.store)
        routing = read(Path(previous["catalog"]))
        native = read(Path(previous["codex-catalog"]))
        native["models"][0]["description"] += " fixture generation"
        def response(request, **_):
            value = native if request.full_url.endswith("codex_client_models.json") else routing
            return io.BytesIO(json.dumps(value).encode())
        with mock.patch("cpr.catalog.urllib.request.urlopen", side_effect=response), \
             mock.patch("cpr.engine.management", side_effect=RuntimeError("fixture rejection")):
            result = catalog.refresh(self.store)
        self.assertFalse(result["ok"])
        self.assertEqual(catalog.prepare(self.store)["generation"], previous["generation"])
        self.assertEqual(read(self.store.config_path)["models"], catalog.sources(self.store))


if __name__ == "__main__":
    unittest.main()
