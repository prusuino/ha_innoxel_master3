from __future__ import annotations
import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    coordinator = data["coordinator"]  # fast: output module state
    slow = data["slow_coordinator"]  # weather, room climate, diagnostics

    entities = []
    for (mod_class, mod_index), info in coordinator.module_info.items():
        if mod_class != "masterOutModule":
            continue
        desc = info.get("description", "")
        # "In 8 / Out 8" modules: their out channels are LED/status
        # indicators, never loads - expose them as read-only binary
        # sensors instead of switches (any module index).
        in8out8 = "In 8 / Out 8" in desc
        if not in8out8:
            if mod_index < 45:
                continue
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

    # Room climate valve and alarm sensors
    for idx, name in sorted(coordinator.room_climate_modules.items()):
        entities.append(InnoxelRoomClimateValve(slow, entry.entry_id, idx, name))
        entities.append(InnoxelRoomClimateAlarm(slow, entry.entry_id, idx, name))

    # Weather binary sensors
    weather_entities = [
        InnoxelWeatherBinarySensor(slow, entry.entry_id, "rain",          "Wetterstation Regen",    BinarySensorDeviceClass.MOISTURE, "mdi:weather-rainy"),
        InnoxelWeatherBinarySensor(slow, entry.entry_id, "civil_twilight", "Wetterstation Dämmerung", None,                             "mdi:weather-night"),
        InnoxelWeatherBinarySensor(slow, entry.entry_id, "sensor_error",   "Wetterstation Sensor Fehler", BinarySensorDeviceClass.PROBLEM, "mdi:alert-circle"),
    ]
    # Bus supply state diagnostics (on = problem, i.e. anything but "OK")
    supply_entities = [
        InnoxelSupplyBinarySensor(slow, entry.entry_id, key, name)
        for key, name in (
            ("supply_can1",     "Diagnose CAN1 Versorgung"),
            ("supply_can2",     "Diagnose CAN2 Versorgung"),
            ("supply_com1_int", "Diagnose Com1 intern"),
            ("supply_com2_int", "Diagnose Com2 intern"),
            ("supply_com3_int", "Diagnose Com3 intern"),
            ("supply_com3_ext", "Diagnose Com3 extern"),
        )
    ]
    async_add_entities(entities + weather_entities + supply_entities)


class InnoxelBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry_id, mod_index, channel, name):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._mod_index = mod_index
        self._channel = channel
        self._attr_name = name
        self._attr_unique_id = f"innoxel_{entry_id}_binary_{mod_index}_{channel}"

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
        self._attr_device_info = coordinator.device_info
        self._idx = idx
        self._attr_name = f"{room_name} Ventil"
        self._attr_unique_id = f"innoxel_{entry_id}_rc_{idx}_valve"
        self._attr_device_class = BinarySensorDeviceClass.OPENING
        self._attr_icon = "mdi:valve"

    @property
    def is_on(self) -> bool | None:
        rc = (self.coordinator.data or {}).get("roomclimate", {})
        return rc.get(self._idx, {}).get("valve_open")


class InnoxelRoomClimateAlarm(CoordinatorEntity, BinarySensorEntity):
    """Thermostat alarm state ("nothing" = OK, anything else = problem)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:thermometer-alert"

    def __init__(self, coordinator, entry_id, idx, room_name):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._idx = idx
        self._attr_name = f"{room_name} Alarm"
        self._attr_unique_id = f"innoxel_{entry_id}_rc_{idx}_alarm"

    def _alarm(self) -> str | None:
        rc = (self.coordinator.data or {}).get("roomclimate", {})
        return rc.get(self._idx, {}).get("alarm")

    @property
    def is_on(self) -> bool | None:
        alarm = self._alarm()
        if alarm is None:
            return None
        return alarm not in ("", "nothing")

    @property
    def extra_state_attributes(self) -> dict:
        return {"alarm_state": self._alarm()}


class InnoxelSupplyBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cable-data"

    def __init__(self, coordinator, entry_id, data_key, name):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._data_key = data_key
        self._attr_name = name
        self._attr_unique_id = f"innoxel_{entry_id}_diag_{data_key}"

    @property
    def available(self) -> bool:
        # Unavailable instead of stale values when getDeviceStateList keeps failing
        return super().available and self.coordinator.device_status_available

    @property
    def is_on(self) -> bool | None:
        status = (self.coordinator.data or {}).get("devicestatus", {})
        raw = status.get(self._data_key)
        if raw is None:
            return None
        return raw != "OK"

    @property
    def extra_state_attributes(self):
        status = (self.coordinator.data or {}).get("devicestatus", {})
        return {"raw_state": status.get(self._data_key)}


class InnoxelWeatherBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry_id, key, name, device_class, icon):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"innoxel_{entry_id}_weather_{key}"
        self._attr_device_class = device_class
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        weather = (self.coordinator.data or {}).get("weather", {})
        return weather.get(self._key)

    @property
    def extra_state_attributes(self):
        weather = (self.coordinator.data or {}).get("weather", {})
        if self._key == "rain":
            # Raw precipitation value from the station — the wet-side value
            # has never been captured live, so this makes it visible for
            # diagnosis.
            return {"raw_value": weather.get("rain_raw")}
        if self._key == "sensor_error":
            # The four module health flags this sensor is derived from.
            # If the tile ever goes red, these say which one did it.
            return {
                "module_state": weather.get("module_state"),
                "address_conflict": weather.get("address_conflict"),
                "missing_parameters": weather.get("missing_parameters"),
                "lonely": weather.get("lonely"),
            }
        return None
