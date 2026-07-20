from __future__ import annotations
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]

    entities = []

    # Physical/virtual output switches (description-based, no index limit)
    for (mod_class, mod_index), info in coordinator.module_info.items():
        if mod_class != "masterOutModule":
            continue
        desc = info.get("description", "")
        if "Switch" not in desc and "Virtuell" not in desc:
            continue
        ch_names = info.get("channels", {})
        for ch_idx, ch_name in sorted(ch_names.items()):
            if not ch_name:
                continue
            entities.append(
                InnoxelSwitch(
                    coordinator, client, entry.entry_id,
                    mod_index, ch_idx, ch_name,
                )
            )

    # Timeswitch modules
    for ts_index, ts_name in coordinator.time_switch_modules.items():
        entities.append(
            InnoxelTimeSwitchSwitch(coordinator, client, entry.entry_id, ts_index, ts_name)
        )

    async_add_entities(entities)


class InnoxelSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, client, entry_id, mod_index, channel, ch_name):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._client = client
        self._mod_index = mod_index
        self._channel = channel
        self._attr_name = f"[o{mod_index:02d}-{channel}] {ch_name}"
        self._attr_unique_id = f"innoxel_{entry_id}_switch_{mod_index}_{channel}"

    @property
    def is_on(self) -> bool:
        state = self.coordinator.data or {}
        channels = state.get(("masterOutModule", self._mod_index), {}).get("channels", {})
        return channels.get(self._channel) == "on"

    async def async_turn_on(self, **kwargs) -> None:
        if not self.is_on:
            await self._client.trigger_out_module(self._mod_index, self._channel)
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        if self.is_on:
            await self._client.trigger_out_module(self._mod_index, self._channel)
        await self.coordinator.async_refresh()


class InnoxelTimeSwitchSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, client, entry_id, index, name):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._client = client
        self._index = index
        self._attr_name = name
        self._attr_unique_id = f"innoxel_{entry_id}_ts_{index}"
        self.entity_id = f"switch.innoxel_ts_{index}"

    @property
    def is_on(self) -> bool | None:
        ts = (self.coordinator.data or {}).get("timeswitch", {})
        return ts.get(self._index) == "enabled"

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.set_time_switch_state(self._index, True)
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.set_time_switch_state(self._index, False)
        await self.coordinator.async_refresh()
