"""Offline tests for the register parsing and token handling.

Runs without Home Assistant installed and without any credentials:

    python3 tests/test_parse.py
"""

import importlib.util
import sys
import types
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "hager_flow"


def _stub(name, **attrs):
    """Register a minimal stand-in module so the component can be imported."""
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


class _Coordinator:
    """Stand-in for DataUpdateCoordinator."""

    def __init__(self, *args, **kwargs):
        pass

    def __class_getitem__(cls, item):
        return cls


if "aiohttp" not in sys.modules:
    try:
        import aiohttp  # noqa: F401
    except ModuleNotFoundError:
        # Only the type references are needed here, not a working HTTP stack.
        _stub(
            "aiohttp",
            ClientTimeout=lambda **kwargs: None,
            ClientSession=object,
            ClientError=type("ClientError", (Exception,), {}),
            ContentTypeError=type("ContentTypeError", (Exception,), {}),
        )

_stub("homeassistant")
_stub("homeassistant.config_entries", ConfigEntry=object)
_stub("homeassistant.core", HomeAssistant=object)
_stub(
    "homeassistant.exceptions",
    ConfigEntryAuthFailed=type("ConfigEntryAuthFailed", (Exception,), {}),
)
_stub("homeassistant.helpers")
_stub(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=_Coordinator,
    UpdateFailed=type("UpdateFailed", (Exception,), {}),
)
_stub("homeassistant.util")
_stub("homeassistant.util.dt", utcnow=lambda: None)

package = types.ModuleType("hager_flow")
package.__path__ = [str(COMPONENT)]
sys.modules["hager_flow"] = package

for name in ("const", "api", "coordinator"):
    spec = importlib.util.spec_from_file_location(
        f"hager_flow.{name}", COMPONENT / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"hager_flow.{name}"] = module
    spec.loader.exec_module(module)

from hager_flow.api import _jwt_expiry  # noqa: E402
from hager_flow.coordinator import HagerFlowCoordinator  # noqa: E402

parse = HagerFlowCoordinator._parse

# Synthetic daytime reading: 3000 W from the panels, 1200 W charging the
# battery, 1200 W used by the house and the remaining 600 W exported.
RAW = {
    "offlineLevel": 0,
    "SOC": 55,
    "POWER_PV_S1": 1200, "POWER_PV_S2": 1000, "POWER_PV_S3": 800,
    "POWER_BAT_1": 400, "POWER_BAT_2": 400, "POWER_BAT_3": 400,
    "POWER_ROOTLM_L1": -200, "POWER_ROOTLM_L2": -200, "POWER_ROOTLM_L3": -200,
    "POWER_C_L1": 300, "POWER_C_L2": 400, "POWER_C_L3": 500,
    "POWER_AC_L1": 600, "POWER_AC_L2": 600, "POWER_AC_L3": 600,
}
# Synthetic cumulative counters in watt-hours, built the way the backend
# reports them: NetIn is the export register and NetOut the import one, and
# Production is the balance without the battery, so it satisfies
# Production == Consumption + NetIn - NetOut exactly.
ENERGY = {
    "Production": 950000.0, "Consumption": 800000.0,
    "NetIn": 400000.0, "NetOut": 250000.0,
    "BatPowerIn": 300000.0, "BatPowerOut": 275500.0,
}

# A discharging counterpart, so both signs get exercised.
RAW_DISCHARGING = {
    "offlineLevel": 0,
    "SOC": 40,
    "POWER_PV_S1": 0, "POWER_PV_S2": 0, "POWER_PV_S3": 0,
    "POWER_BAT_1": -100, "POWER_BAT_2": -100, "POWER_BAT_3": -100,
    "POWER_ROOTLM_L1": 50, "POWER_ROOTLM_L2": 50, "POWER_ROOTLM_L3": 50,
    "POWER_C_L1": 150, "POWER_C_L2": 150, "POWER_C_L3": 150,
}


def test_power_values_while_charging():
    """Per-phase and per-string registers are summed with the right signs."""
    out = parse(RAW, ENERGY)
    assert out["soc"] == 55
    assert out["pv_power"] == 3000
    assert out["house_power"] == 1200
    assert out["inverter_power"] == 1800
    assert out["battery_power"] == 1200
    assert out["battery_charge_power"] == 1200
    assert out["battery_discharge_power"] == 0
    assert out["grid_power"] == -600
    assert out["grid_export_power"] == 600
    assert out["grid_import_power"] == 0
    assert out["online"] is True


def test_power_values_while_discharging():
    """Negative battery and positive grid values map to the other direction."""
    out = parse(RAW_DISCHARGING, {})
    assert out["pv_power"] == 0
    assert out["house_power"] == 450
    assert out["battery_power"] == -300
    assert out["battery_discharge_power"] == 300
    assert out["battery_charge_power"] == 0
    assert out["grid_power"] == 150
    assert out["grid_import_power"] == 150
    assert out["grid_export_power"] == 0


def test_energy_balance():
    """Everything flowing in must equal everything flowing out."""
    for raw in (RAW, RAW_DISCHARGING):
        out = parse(raw, {})
        incoming = (
            out["pv_power"] + out["battery_discharge_power"] + out["grid_import_power"]
        )
        outgoing = (
            out["house_power"] + out["battery_charge_power"] + out["grid_export_power"]
        )
        assert incoming == outgoing, (incoming, outgoing)


def test_energy_counters_converted_to_kwh():
    """Counters arrive in watt-hours and are exposed in kilowatt-hours."""
    out = parse(RAW, ENERGY)
    assert out["house_energy"] == 800.0
    assert out["battery_charge_energy"] == 300.0
    assert out["battery_discharge_energy"] == 275.5


def test_grid_counters_are_named_from_the_grids_point_of_view():
    """NetIn is the export register, NetOut the import one — not the reverse."""
    out = parse(RAW, ENERGY)
    assert out["grid_export_energy"] == 400.0, "NetIn must land on export"
    assert out["grid_import_energy"] == 250.0, "NetOut must land on import"


def test_pv_energy_adds_the_battery_back_in():
    """Production omits the battery, so it is not the production counter.

    Guards the identity the backend actually reports; a night-time reading with
    no sun still moves Production, which is what makes the raw value unusable.
    """
    identity = ENERGY["Consumption"] + ENERGY["NetIn"] - ENERGY["NetOut"]
    assert identity == ENERGY["Production"], "fixture no longer matches the backend"

    out = parse(RAW, ENERGY)
    assert out["pv_energy"] == 974.5
    assert out["pv_energy"] != ENERGY["Production"] / 1000

    # House load overnight: no sun, no grid flow, battery covering the house.
    night = {
        "Production": 950100.0, "Consumption": 800100.0,
        "NetIn": 400000.0, "NetOut": 250000.0,
        "BatPowerIn": 300000.0, "BatPowerOut": 275600.0,
    }
    assert parse(RAW_DISCHARGING, night)["pv_energy"] == 974.5, (
        "derived production must stand still while the sun is down"
    )


def test_missing_energy_is_none():
    """Before the first energy poll the counters are unknown, not zero."""
    out = parse(RAW, {})
    assert out["pv_energy"] is None
    assert out["soc"] == 55


def test_partial_energy_payload_leaves_pv_unknown():
    """The derived counter needs all three registers, or it stays None."""
    partial = dict(ENERGY)
    del partial["BatPowerOut"]
    assert parse(RAW, partial)["pv_energy"] is None
    assert parse(RAW, {**ENERGY, "Production": None})["pv_energy"] is None


def test_missing_registers_do_not_crash():
    """Absent or null registers count as zero instead of raising."""
    out = parse({"offlineLevel": 1, "POWER_BAT_1": None}, {})
    assert out["battery_power"] == 0
    assert out["online"] is False


def test_jwt_expiry():
    """The expiry claim is read, and malformed tokens return None."""
    import base64
    import json

    payload = base64.urlsafe_b64encode(json.dumps({"exp": 2000000000}).encode())
    token = f"header.{payload.decode().rstrip('=')}.signature"
    assert _jwt_expiry(token) == 2000000000
    assert _jwt_expiry("not.a.jwt") is None
    assert _jwt_expiry("garbage") is None


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
