"""Diagnostics download (Settings → Devices & services → entry menu →
Download diagnostics).

The file carries what an issue report needs: the versions of the master, the
modules and channels read from its configuration, how covers were matched to
their virtual input channels, what the two polls last returned, and the
entities with their current state.

Host, user name, password, MAC address, UUID and the location stored in the
master are redacted; of the last error only the type is kept, its text can
repeat the address. Module, channel and entity names stay readable; they are
the names from your INNOXEL configuration.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

REDACTED = "**REDACTED**"
TO_REDACT = {
    "host",
    "username",
    "password",
    "mac",
    "uuid",
    "location",
    "location_details",
    "configuration_url",
    # attributes of the device identity sensor
    "standort",
    "installation",
}
# The state of this sensor is the location name stored in the master.
IDENTITY_SENSOR_SUFFIX = "_diag_device_identity"
# An installation has a few dozen modules with up to eight channels each;
# the limits only stop a runaway value from filling the file.
MAX_ITEMS = 600
MAX_TEXT = 500


def _compact(value: Any, depth: int = 0) -> Any:
    """A JSON-safe, size-limited copy of a value, with the keys in TO_REDACT replaced."""
    if depth > 8:
        return "…"
    if isinstance(value, dict):
        items = list(value.items())
        out = {
            _key(key): (
                REDACTED
                if str(key).lower() in TO_REDACT and item not in (None, "")
                else _compact(item, depth + 1)
            )
            for key, item in items[:MAX_ITEMS]
        }
        if len(items) > MAX_ITEMS:
            out["…"] = f"{len(items) - MAX_ITEMS} more"
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        out_list = [_compact(item, depth + 1) for item in items[:MAX_ITEMS]]
        if len(items) > MAX_ITEMS:
            out_list.append(f"… {len(items) - MAX_ITEMS} more")
        return out_list
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + "…"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _key(key: Any) -> str:
    """Dictionary keys are often (module class, index) pairs."""
    if isinstance(key, tuple):
        return "/".join(str(part) for part in key)
    return str(key)


def _coordinator(coordinator: Any) -> dict[str, Any]:
    error = coordinator.last_exception
    interval = coordinator.update_interval
    return {
        "last_update_success": coordinator.last_update_success,
        "last_error": type(error).__name__ if error else None,
        "update_interval_seconds": interval.total_seconds() if interval else None,
        "data": _compact(coordinator.data),
    }


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return the diagnostics of one master."""
    diagnostics: dict[str, Any] = {
        "entry": {
            "version": entry.version,
            "state": entry.state.value,
            "data": _compact(dict(entry.data)),
            "options": _compact(dict(entry.options)),
        },
    }

    if entry.state is ConfigEntryState.LOADED:
        fast = entry.runtime_data["coordinator"]
        slow = entry.runtime_data["slow_coordinator"]
        diagnostics["master"] = _compact(fast.device_data)
        diagnostics["modules"] = {
            "modules": _compact(fast.module_info),
            "time_switches": _compact(fast.time_switch_modules),
            "room_climate": _compact(fast.room_climate_modules),
            "blind_modules_g2": _compact(fast.blind_modules),
            # Cover name -> the virtual input channels found for it. A cover
            # missing here falls back to a short jog instead of a full run.
            "cover_input_channels": _compact(fast.input_channel_map),
        }
        diagnostics["polls"] = {
            "state": _coordinator(fast),
            "slow": _coordinator(slow),
            "device_status_available": slow.device_status_available,
        }

    registry = er.async_get(hass)
    entities = []
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        state = hass.states.get(item.entity_id)
        entities.append(
            {
                "entity_id": item.entity_id,
                "unique_id": item.unique_id,
                "original_name": item.original_name,
                "disabled_by": item.disabled_by,
                "state": (
                    None
                    if state is None
                    else REDACTED
                    if item.unique_id.endswith(IDENTITY_SENSOR_SUFFIX)
                    else state.state
                ),
                "attributes": _compact(dict(state.attributes)) if state else None,
            }
        )
    diagnostics["entities"] = sorted(entities, key=lambda entity: entity["entity_id"])
    return diagnostics
