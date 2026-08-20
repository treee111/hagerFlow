"""Checks that translation placeholders are actually filled in by the flow.

hassfest rejects URLs inside translation strings, so they are passed in as
description placeholders instead. It does not verify that the code supplies
them — a missing one would show up literally as "{portal_url}" in the dialog.

    python3 tests/test_translations.py
"""

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "hager_flow"

STRINGS = COMPONENT / "strings.json"
TRANSLATIONS = sorted((COMPONENT / "translations").glob("*.json"))
CONFIG_FLOW = COMPONENT / "config_flow.py"

# Supplied by Home Assistant itself rather than by the config flow.
BUILTIN_PLACEHOLDERS = {"brand", "name", "integration"}


def _placeholders_per_step():
    """Map each step_id to the placeholder names async_show_form passes for it.

    Parsed from the source so that a placeholder supplied for one step is not
    mistaken for one supplied for another.
    """
    supplied = {}
    tree = ast.parse(CONFIG_FLOW.read_text())

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "async_show_form"):
            continue

        keywords = {kw.arg: kw.value for kw in node.keywords}
        step = keywords.get("step_id")
        if not isinstance(step, ast.Constant):
            continue

        names = set()
        placeholders = keywords.get("description_placeholders")
        if isinstance(placeholders, ast.Dict):
            names = {
                key.value
                for key in placeholders.keys
                if isinstance(key, ast.Constant)
            }
        supplied[step.value] = names

    return supplied


def _placeholders(text):
    """Return the {placeholder} names used in a string."""
    return set(re.findall(r"\{(\w+)\}", text))


def _steps(path):
    """Yield (step_id, field, text) for every translatable step string."""
    data = json.loads(path.read_text())
    for step_id, step in data.get("config", {}).get("step", {}).items():
        for key, value in step.items():
            if isinstance(value, str):
                yield step_id, key, value


def test_no_urls_in_translations():
    """hassfest rejects URLs inside translation strings."""
    for path in [STRINGS, *TRANSLATIONS]:
        urls = re.findall(r"https?://\S+", path.read_text())
        assert not urls, f"{path.name} still contains URLs: {urls}"


def test_placeholders_are_supplied_by_config_flow():
    """Every placeholder used in a step must be passed for that same step."""
    supplied = _placeholders_per_step()
    assert supplied, "no async_show_form calls found in config_flow.py"

    for path in [STRINGS, *TRANSLATIONS]:
        for step_id, key, text in _steps(path):
            needed = _placeholders(text) - BUILTIN_PLACEHOLDERS
            if not needed:
                continue
            assert step_id in supplied, (
                f"{path.name}: step '{step_id}' uses {sorted(needed)} but "
                f"config_flow.py shows no form for it"
            )
            missing = needed - supplied[step_id]
            assert not missing, (
                f"{path.name}: step '{step_id}' uses {sorted(missing)} in "
                f"'{key}', but that step does not supply it"
            )


def test_translations_match_strings():
    """en.json must mirror strings.json, de.json must cover the same keys."""

    def flatten(data, prefix=""):
        keys = set()
        for key, value in data.items():
            if isinstance(value, dict):
                keys |= flatten(value, f"{prefix}.{key}")
            else:
                keys.add(f"{prefix}.{key}")
        return keys

    base = json.loads(STRINGS.read_text())
    english = json.loads((COMPONENT / "translations" / "en.json").read_text())
    assert english == base, "translations/en.json is out of sync with strings.json"

    german = json.loads((COMPONENT / "translations" / "de.json").read_text())
    missing = flatten(base) - flatten(german)
    assert not missing, f"de.json is missing keys: {sorted(missing)}"


if __name__ == "__main__":
    failures = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
            except AssertionError as err:
                print(f"FAIL {name}: {err}")
                failures += 1
            else:
                print(f"ok   {name}")
    sys.exit(1 if failures else 0)
