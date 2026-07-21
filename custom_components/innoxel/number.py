from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENABLE_COOLING,
    DOMAIN,
    RC_FIELD_ABSENCE_COOLING,
    RC_FIELD_ABSENCE_HEATING,
    RC_FIELD_NIGHT_COOLING,
    RC_FIELD_NIGHT_HEATING,
    RC_FIELD_SET_COOLING,
)

# (data key, SOAP field, entity_id suffix, name suffix, cooling-only)
_SETPOINTS = [
    ("night_setback_heating", RC_FIELD_NIGHT_HEATING, "night_setback", "Nachtabsenkung", False),
    ("absence_setback_heating", RC_FIELD_ABSENCE_HEATING, "absence_setback", "Abwesenheit", False),
    ("set_temp_cooling", RC_FIELD_SET_COOLING, "setpoint_cooling", "Sollwert Kühlen", True),
    ("night_setback_cooling", RC_FIELD_NIGHT_COOLING, "night_setback_cooling", "Nachtabsenkung Kühlen", True),
    ("absence_setback_cooling", RC_FIELD_ABSENCE_COOLING, "absence_setback_cooling", "Abwesenheit Kühlen", True),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    cooling = entry.options.get(
        CONF_ENABLE_COOLING, entry.data.get(CONF_ENABLE_COOLING, False)
    )
    entities = [
        InnoxelRoomClimateSetpoint(coordinator, client, entry.entry_id, idx, name, spec)
        for idx, name in sorted(coordinator.room_climate_modules.items())
        for spec in _SETPOINTS
        if cooling or not spec[4]
    ]
    async_add_entities(entities)


class InnoxelRoomClimateSetpoint(CoordinatorEntity, NumberEntity):
    """One writable thermostat temperature (night/absence setback, cooling setpoints)."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 5.0
    _attr_native_max_value = 28.0
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, client, entry_id, idx, room_name, spec):
        super().__init__(coordinator)
        data_key, soap_field, suffix, name_suffix, _ = spec
        self._attr_device_info = coordinator.device_info
        self._idx = idx
        self._client = client
        self._data_key = data_key
        self._soap_field = soap_field
        self._attr_name = f"{room_name} {name_suffix}"
        self._attr_unique_id = f"innoxel_{entry_id}_rc_{idx}_{data_key}"
        self.entity_id = f"number.innoxel_rc{idx:02d}_{suffix}"

    @property
    def native_value(self) -> float | None:
        rc = (self.coordinator.data or {}).get("roomclimate", {})
        return rc.get(self._idx, {}).get(self._data_key)

    async def async_set_native_value(self, value: float) -> None:
        await self._client.set_room_climate_value(self._idx, self._soap_field, value)
        await self.coordinator.async_request_refresh()
