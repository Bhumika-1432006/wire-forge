"""verify-wire builds a forge-shaped action dir from a catalog hit, offline."""

import json

from wireforge.wireaction import ACTION_TEMPLATE, build_action_dir

HIT = {"action_id": "act_x_search", "catalog": "x", "credits": 2,
       "params": {"required": [{"name": "q", "type": "string", "default": "shoes"}],
                  "optional": [{"name": "sort", "type": "string"}]}}


def test_action_dir_matches_forge_layout(tmp_path):
    d = build_action_dir("act_x_search", "https://x.test", tmp_path, HIT)
    spec = json.loads((d / "spec.json").read_text(encoding="utf-8"))
    assert spec["action_id"] == "act_x_search" and spec["type"] == "read"
    assert {p["name"]: p["required"] for p in spec["parameters"]} == {"q": True, "sort": False}
    assert "https://x.test" in spec["description"]
    assert json.loads((d / "test_params.json").read_text(encoding="utf-8")) == {"q": "shoes"}
    code = (d / "action.py").read_text(encoding="utf-8")
    assert "def run(params: dict, client)" in code and "act_x_search" in code


def test_action_template_compiles():
    compile(ACTION_TEMPLATE.format(api="https://api.test/v1", action_id="a_b"), "action.py", "exec")
