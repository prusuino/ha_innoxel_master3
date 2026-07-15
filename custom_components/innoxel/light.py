from __future__ import annotations
import logging

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
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
    for (mod_class, mod_index), info in coordinator.module_info.items():
        if mod_class != "masterDimModule":
            continue
        ch_names = info.get("channels", {})
        for ch, ch_name in sorted(ch_names.items()):
            entities.append(
                InnoxelLight(
                    coordinator, client, entry.entry_id,
                    mod_index, ch, ch_name,
                )
            )
    async_add_entities(entities)


class InnoxelLight(CoordinatorEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator, client, entry_id, mod_index, channel, description):
        super().__init__(coordinator)
        self._client = client
        self._mod_index = mod_index
        self._channel = channel
        self._description = description
        self._attr_name = f"[d{mod_index:02d}-{channel}] {description}"
        self._attr_unique_id = f"innoxel_{entry_id}_light_{mod_index}_{channel}"

    @property
    def extra_state_attributes(self) -> dict:
        return {"bezeichnung": self._description} if self._description else {}

    def _value(self) -> int:
        state = self.coordinator.data or {}
        channels = state.get(("masterDimModule", self._mod_index), {}).get("channels", {})
        try:
            return int(channels.get(self._channel, 0))
        except (ValueError, TypeError):
            return 0

    @property
    def is_on(self) -> bool:
        return self._value() > 0

    @property
    def brightness(self) -> int:
        return round(self._value() / 100 * 255)

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            value = round(kwargs[ATTR_BRIGHTNESS] / 255 * 100)
        else:
            value = 100
        await self._client.set_dim_value(self._mod_index, self._channel, max(1, value))
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.set_dim_value(self._mod_index, self._channel, 0)
        await self.coordinator.async_refresh()
