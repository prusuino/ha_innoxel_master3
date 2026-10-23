from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]  # identity: which room climate modules exist
    slow = data["slow_coordinator"]  # room climate data
    client = data["client"]
    entities = [
        InnoxelRoomClimate(slow, client, entry.entry_id, idx, name)
        for idx, name in sorted(coordinator.room_climate_modules.items())
    ]
    async_add_entities(entities)


class InnoxelRoomClimate(CoordinatorEntity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 5.0
    _attr_max_temp = 28.0
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator, client, entry_id, idx, room_name):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._idx = idx
        self._client = client
        self._attr_name = room_name
        self._attr_unique_id = f"innoxel_{entry_id}_rc_{idx}_climate"

    def _rc(self) -> dict:
        return (self.coordinator.data or {}).get("roomclimate", {}).get(self._idx, {})

    @property
    def current_temperature(self) -> float | None:
        return self._rc().get("actual_temp")

    @property
    def target_temperature(self) -> float | None:
        return self._rc().get("set_temp")

    @property
    def hvac_action(self) -> HVACAction:
        # ``operatingState`` is the room controller's *mode* (heating or
        # cooling season), not whether energy is flowing right now: on a
        # Master 3 it reads "heating" all winter long, even with the valve
        # closed. The valve state is the actual demand, so it decides;
        # the operating state only selects heating vs. cooling.
        rc = self._rc()
        valve_open = rc.get("valve_open")
        if valve_open is None:
            # Firmware without valve state: the operating state is all we have.
            operating = (rc.get("operating_state") or "").lower()
            if operating == "heating":
                return HVACAction.HEATING
            if operating == "cooling":
                return HVACAction.COOLING
            return HVACAction.IDLE
        if not valve_open:
            return HVACAction.IDLE
        operating = (rc.get("operating_state") or "").lower()
        if operating == "cooling":
            return HVACAction.COOLING
        return HVACAction.HEATING

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        await self._client.set_room_climate_temperature(self._idx, temp)
        await self.coordinator.async_request_refresh()
