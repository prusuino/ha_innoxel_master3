from __future__ import annotations
import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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

    entities = []
    for (mod_class, mod_index), info in coordinator.module_info.items():
        if mod_class != "masterOutModule" or mod_index < 45:
            continue
        desc = info.get("description", "")
        if "Switch" in desc or "Virtuell" in desc:
            continue  # handled by switch.py
        ch_names = info.get("channels", {})
        for ch_idx, ch_name in sorted(ch_names.items()):
            if not ch_name.strip():
                continue
            display_name = f"[o{mod_index:02d}-{ch_idx}] {ch_name}"
            entities.append(
                InnoxelBinarySensor(
                    coordinator,
                    entry.entry_id,
                    mod_index,
                    ch_idx,
                    display_name,
                )
            )

    # Room climate valve sensors
    for idx, name in sorted(coordinator.room_climate_modules.items()):
        entities.append(InnoxelRoomClimateValve(coordinator, entry.entry_id, idx, name))

    # Weather binary sensors
    weather_entities = [
        InnoxelWeatherBinarySensor(coordinator, entry.entry_id, "rain",          "Wetterstation Regen",    "rain",    BinarySensorDeviceClass.MOISTURE, "mdi:weather-rainy"),
        InnoxelWeatherBinarySensor(coordinator, entry.entry_id, "civil_twilight", "Wetterstation Dämmerung", "dawn",   None,                             "mdi:weather-night"),
        InnoxelWeatherBinarySensor(coordinator, entry.entry_id, "sensor_error",   "Wetterstation Sensor Fehler", "sensor_error", BinarySensorDeviceClass.PROBLEM, "mdi:alert-circle"),
    ]
    async_add_entities(entities + weather_entities)


class InnoxelBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry_id, mod_index, channel, name):
        super().__init__(coordinator)
        self._mod_index = mod_index
        self._channel = channel
        self._attr_name = name
        self._attr_unique_id = f"innoxel_{entry_id}_binary_{mod_index}_{channel}"
        self.entity_id = f"binary_sensor.innoxel_o{mod_index:02d}_{channel}"

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data or {}
        channels = state.get(("masterOutModule", self._mod_index), {}).get("channels", {})
        val = channels.get(self._channel)
        if val is None:
            return None
        return val == "on"


class InnoxelRoomClimateValve(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry_id, idx, room_name):
        super().__init__(coordinator)
        self._idx = idx
        self._attr_name = f"{room_name} Ventil"
        self._attr_unique_id = f"innoxel_{entry_id}_rc_{idx}_valve"
        self.entity_id = f"binary_sensor.innoxel_rc{idx:02d}_valve"
        self._attr_device_class = BinarySensorDeviceClass.OPENING
        self._attr_icon = "mdi:valve"

    @property
    def is_on(self) -> bool | None:
        rc = (self.coordinator.data or {}).get("roomclimate", {})
        return rc.get(self._idx, {}).get("valve_open")


class InnoxelWeatherBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry_id, key, name, suffix, device_class, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"innoxel_{entry_id}_weather_{key}"
        self.entity_id = f"binary_sensor.innoxel_weather_{suffix}"
        self._attr_device_class = device_class
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        weather = (self.coordinator.data or {}).get("weather", {})
        return weather.get(self._key)
