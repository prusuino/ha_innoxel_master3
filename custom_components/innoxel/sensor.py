from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfElectricPotential, UnitOfSpeed, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_WEATHER_SENSORS = [
    # (data_key, name, entity_suffix, device_class, unit, icon)
    ("temperature_air",  "Wetterstation Temperatur",          "temperature",       SensorDeviceClass.TEMPERATURE,   UnitOfTemperature.CELSIUS,           "mdi:thermometer"),
    ("temperature_felt", "Wetterstation Gefühlte Temperatur", "temperature_felt",  SensorDeviceClass.TEMPERATURE,   UnitOfTemperature.CELSIUS,           "mdi:thermometer-lines"),
    ("wind_ms",          "Wetterstation Wind",                "wind_ms",           SensorDeviceClass.WIND_SPEED,    UnitOfSpeed.METERS_PER_SECOND,       "mdi:weather-windy"),
    ("sun_east",         "Wetterstation Sonne Ost",           "sun_east",          SensorDeviceClass.ILLUMINANCE,   "lx",                                "mdi:weather-sunny"),
    ("sun_south",        "Wetterstation Sonne Süd",           "sun_south",         SensorDeviceClass.ILLUMINANCE,   "lx",                                "mdi:weather-sunny"),
    ("sun_west",         "Wetterstation Sonne West",          "sun_west",          SensorDeviceClass.ILLUMINANCE,   "lx",                                "mdi:weather-sunny"),
    ("twilight_lux",     "Wetterstation Dämmerung Lux",       "twilight",          SensorDeviceClass.ILLUMINANCE,   "lx",                                "mdi:weather-sunset"),
]

_DEVICE_SENSORS = [
    # (data_key, name, device_class, unit, icon)
    ("voltage_main",      "Diagnose Speisung",                SensorDeviceClass.VOLTAGE,     UnitOfElectricPotential.VOLT, "mdi:flash"),
    ("voltage_cpu",       "Diagnose Spannung CPU",            SensorDeviceClass.VOLTAGE,     UnitOfElectricPotential.VOLT, "mdi:chip"),
    ("voltage_backup",    "Diagnose Spannung Backup-Batterie", SensorDeviceClass.VOLTAGE,    UnitOfElectricPotential.VOLT, "mdi:battery-heart-variant"),
    ("voltage_keymatrix", "Diagnose Spannung Tastenmatrix",   SensorDeviceClass.VOLTAGE,     UnitOfElectricPotential.VOLT, "mdi:gesture-tap-button"),
    ("temp_cpu_base",     "Diagnose Temperatur Basis-CPU",    SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,    "mdi:thermometer"),
    ("temp_cpu_host",     "Diagnose Temperatur Host-CPU",     SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,    "mdi:thermometer-alert"),
    ("uptime_days",       "Diagnose Uptime",                  SensorDeviceClass.DURATION,    UnitOfTime.DAYS,              "mdi:timer-outline"),
    ("serial_errors",     "Diagnose CAN Serielle Fehler",     None,                          None,                         "mdi:alert-circle-check"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list = [
        InnoxelWeatherSensor(coordinator, entry.entry_id, *row)
        for row in _WEATHER_SENSORS
    ]
    for idx, name in sorted(coordinator.room_climate_modules.items()):
        entities.append(InnoxelRoomClimateSensor(coordinator, entry.entry_id, idx, name, "actual_temp", "Ist-Temp"))
        entities.append(InnoxelRoomClimateSensor(coordinator, entry.entry_id, idx, name, "set_temp",    "Soll-Temp"))
    entities.extend(
        InnoxelDeviceSensor(coordinator, entry.entry_id, *row)
        for row in _DEVICE_SENSORS
    )
    async_add_entities(entities)


class InnoxelWeatherSensor(CoordinatorEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id, data_key, name, entity_suffix,
                 device_class, unit, icon):
        super().__init__(coordinator)
        self._data_key = data_key
        self._attr_name = name
        self._attr_unique_id = f"innoxel_{entry_id}_weather_{entity_suffix}"
        self.entity_id = f"sensor.innoxel_weather_{entity_suffix}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon

    @property
    def native_value(self):
        weather = (self.coordinator.data or {}).get("weather", {})
        return weather.get(self._data_key)


class InnoxelDeviceSensor(CoordinatorEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id, data_key, name, device_class, unit, icon):
        super().__init__(coordinator)
        self._data_key = data_key
        self._attr_name = name
        self._attr_unique_id = f"innoxel_{entry_id}_diag_{data_key}"
        self.entity_id = f"sensor.innoxel_diag_{data_key}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon

    @property
    def native_value(self):
        status = (self.coordinator.data or {}).get("devicestatus", {})
        return status.get(self._data_key)

    @property
    def extra_state_attributes(self):
        if self._data_key != "serial_errors":
            return None
        status = (self.coordinator.data or {}).get("devicestatus", {})
        return status.get("serial_errors_detail")


class InnoxelRoomClimateSensor(CoordinatorEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, entry_id, idx, room_name, data_key, label):
        super().__init__(coordinator)
        self._idx = idx
        self._data_key = data_key
        self._attr_name = f"{room_name} {label}"
        self._attr_unique_id = f"innoxel_{entry_id}_rc_{idx}_{data_key}"
        suffix = "temp" if data_key == "actual_temp" else "setpoint"
        self.entity_id = f"sensor.innoxel_rc{idx:02d}_{suffix}"
        self._attr_icon = "mdi:thermometer" if data_key == "actual_temp" else "mdi:thermometer-chevron-up"

    @property
    def native_value(self):
        rc = (self.coordinator.data or {}).get("roomclimate", {})
        return rc.get(self._idx, {}).get(self._data_key)
