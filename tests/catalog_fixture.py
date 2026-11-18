"""Synthetic catalog data for deterministic tests, never an inference claim."""
import json
import copy
from cpr import catalog
from cpr.storage import save


def seed(store):
    native = []
    for slug in ("gpt-6.1-sol", "gpt-6.2-sol"):
        entry = copy.deepcopy(json.loads((catalog.BUNDLED / "codex_client_models.json").read_text())["models"][0])
        entry["model_messages"] = {"instructions_template": "You are a test-only coding assistant.", "instructions_variables": {}}
        entry.update({"slug": slug, "display_name": slug, "description": "Synthetic catalog fixture",
                       "base_instructions": "You are a test-only coding assistant.",
                       "minimal_client_version": "0.167.0", "visibility": "list", "priority": 0,
                       "default_reasoning_level": "low", "supported_reasoning_levels": [
                           {"effort": "low", "description": "Low"}, {"effort": "xhigh", "description": "High"}],
                       "context_window": 128000, "max_context_window": 128000})
        native.append(entry)
    entries = [{"id": x["slug"], "object": "model", "owned_by": "openai", "type": "openai",
                "thinking": {"levels": ["low", "xhigh"]}} for x in native]
    routing = {tier: entries if tier != "codex-free" else entries[:1]
               for tier in ("codex-free", "codex-plus", "codex-team", "codex-pro")}
    state = catalog.stage(store, [json.dumps(x).encode() for x in (routing, {"models": native})], "test-fixture")
    save(store.data / "catalog-state.json", state)
    return state
