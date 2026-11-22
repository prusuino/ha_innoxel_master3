"""The diagnostics download: modules, polls and entities, with the address,
the credentials and the identity of the master redacted."""
from __future__ import annotations

from datetime import timedelta
import json
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.innoxel.const import DOMAIN
from custom_components.innoxel.diagnostics import (
    MAX_ITEMS,
    REDACTED,
    _compact,
    async_get_config_entry_diagnostics,
)

DATA = {CONF_HOST: "192.0.2.20", CONF_PORT: 5001, CONF_USERNAME: "ha-user", CONF_PASSWORD: "s3cret-pw"}
SECRETS = ("192.0.2.20", "ha-user", "s3cret-pw", "00:11:22:33:44:55", "innoxel-1234", "Example Street")


def _coordinators() -> dict:
    fast = MagicMock()
    fast.last_update_success = True
    fast.last_exception = None
    fast.update_interval = timedelta(seconds=1)
    fast.data = {"outputs": {(3, 0): True, (3, 1): False}, "dims": {(40, 2): 55}}
    fast.device_data = {
        "model": "Master 3",
        "manufacturer": "INNOXEL",
        "sw_version": "1.6.0.0 (Base 1.2.0.0)",
        "hw_version": "2.0",
        "mac": "00:11:22:33:44:55",
        "uuid": "uuid:innoxel-1234",
        "location": "Example Street 1",
        "location_details": "Example Street, basement",
        "configuration_url": "http://192.0.2.20:5001/webhome.html",
    }
    fast.module_info = {
        ("masterOutModule", 3): {"name": "Switch 1", "channels": {0: "Kitchen", 1: "Hall"}},
        ("masterInModule", 174): {"name": "Virtual", "channels": {0: "Blind kitchen auf", 1: "Blind kitchen ab"}},
    }
    fast.time_switch_modules = {0: "S1"}
    fast.room_climate_modules = {0: "Living room"}
    fast.blind_modules = {}
    fast.input_channel_map = {"Blind kitchen": {"up": (174, 0), "down": (174, 1)}}

    slow = MagicMock()
    slow.last_update_success = False
    slow.last_exception = UpdateFailed("Innoxel slow update failed: http://192.0.2.20:5001/control")
    slow.update_interval = timedelta(seconds=10)
    slow.data = {"weather": {"temperature": 5.5}, "timeswitch": {0: True}, "roomclimate": {}, "devicestatus": {}}
    slow.device_status_available = True
    return {"coordinator": fast, "slow_coordinator": slow, "client": MagicMock()}


async def test_diagnostics_of_a_loaded_master_hide_address_credentials_and_identity(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="uuid:innoxel-1234", title="Innoxel", data=DATA)
    entry.add_to_hass(hass)
    entry.runtime_data = _coordinators()
    entry.mock_state(hass, ConfigEntryState.LOADED)

    registry = er.async_get(hass)
    identity = registry.async_get_or_create(
        "sensor", DOMAIN, f"innoxel_{entry.entry_id}_diag_device_identity", config_entry=entry
    )
    light = registry.async_get_or_create(
        "switch", DOMAIN, f"innoxel_{entry.entry_id}_binary_3_0", config_entry=entry
    )
    hass.states.async_set(
        identity.entity_id,
        "Example Street 1",
        {"mac": "00:11:22:33:44:55", "uuid": "innoxel-1234", "standort": "Example Street 1",
         "installation": "Example Street, basement", "firmware": "1.6.0.0"},
    )
    hass.states.async_set(light.entity_id, "on", {"friendly_name": "Kitchen"})

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(diagnostics)  # must be plain JSON
    for secret in SECRETS:
        assert secret not in text, secret

    assert diagnostics["entry"]["data"] == {
        CONF_HOST: REDACTED, CONF_PORT: 5001, CONF_USERNAME: REDACTED, CONF_PASSWORD: REDACTED,
    }
    assert diagnostics["master"]["sw_version"] == "1.6.0.0 (Base 1.2.0.0)"
    assert diagnostics["master"]["mac"] == REDACTED
    assert diagnostics["master"]["configuration_url"] == REDACTED
    # (module class, index) keys become readable text
    assert diagnostics["modules"]["modules"]["masterOutModule/3"]["channels"] == {"0": "Kitchen", "1": "Hall"}
    assert diagnostics["modules"]["cover_input_channels"] == {"Blind kitchen": {"up": [174, 0], "down": [174, 1]}}
    assert diagnostics["polls"]["state"] == {
        "last_update_success": True,
        "last_error": None,
        "update_interval_seconds": 1.0,
        "data": {"outputs": {"3/0": True, "3/1": False}, "dims": {"40/2": 55}},
    }
    # Only the type of the last error: its text repeats the address.
    assert diagnostics["polls"]["slow"]["last_error"] == "UpdateFailed"
    assert diagnostics["polls"]["slow"]["data"]["weather"] == {"temperature": 5.5}

    by_id = {entity["entity_id"]: entity for entity in diagnostics["entities"]}
    assert by_id[light.entity_id]["state"] == "on"
    assert by_id[identity.entity_id]["state"] == REDACTED
    assert by_id[identity.entity_id]["attributes"]["standort"] == REDACTED
    assert by_id[identity.entity_id]["attributes"]["firmware"] == "1.6.0.0"


async def test_diagnostics_of_a_master_that_is_not_loaded(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="uuid:innoxel-1234", title="Innoxel", data=DATA)
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    json.dumps(diagnostics)
    assert diagnostics["entry"]["state"] == "not_loaded"
    assert diagnostics["entry"]["data"][CONF_PASSWORD] == REDACTED
    assert "master" not in diagnostics and "polls" not in diagnostics
    assert diagnostics["entities"] == []


def test_compact_limits_size_and_depth() -> None:
    many = _compact({n: n for n in range(MAX_ITEMS + 5)})
    assert len(many) == MAX_ITEMS + 1 and many["…"] == "5 more"
    assert _compact(list(range(MAX_ITEMS + 2)))[-1] == "… 2 more"
    assert _compact("x" * 2000).endswith("…") and len(_compact("x" * 2000)) == 501
    deep: dict = {}
    node = deep
    for _ in range(12):
        node["a"] = {}
        node = node["a"]
    assert "…" in json.dumps(_compact(deep), ensure_ascii=False)
    assert _compact({"password": ""}) == {"password": ""}  # nothing to hide
    assert _compact(object()).startswith("<object")
