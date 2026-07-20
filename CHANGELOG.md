# Changelog

## 1.1.0 — 2026-07-20

- Added: hardware diagnostic entities for the Innoxel Master itself, read via the SOAP `getDeviceStateList` action (polled every 60 seconds; diagnostics failures never break the regular state updates). All entities use `entity_category: diagnostic`, so they appear in the Diagnostic section of the device page:
  - Sensors: main supply voltage, CPU voltage, backup battery voltage, key matrix voltage, base CPU temperature, host CPU temperature, uptime (days), and a serial error counter (sum of errors, CRC errors, and violations, with the individual counters as attributes)
  - Binary sensors (problem class, on = not OK): CAN1/CAN2 bus supply, Com1–Com3 internal, Com3 external — each with the raw reported state as a `raw_state` attribute

## 1.0.2 — 2026-07-20

- Fixed: the twilight binary sensor (`binary_sensor.*_weather_dawn`) was always off, so automations triggering on dusk never fired. The Innoxel controller reports the `isCivilTwilight` attribute as `yes`/`no`, but the parser compared it against `true`. Same bug class as the 1.0.1 rain fix — Innoxel SOAP boolean attributes are always `yes`/`no`.

## 1.0.1 — 2026-07-18

- Fixed: the rain binary sensor could stay off during rain. The weather station's precipitation element had only ever been observed reporting `dry`; the wet-side value was assumed to be `wet` but had never been captured live. The sensor now treats anything other than `dry` as rain, and exposes the station's raw precipitation value as a `raw_value` attribute for diagnosis.

## 1.0.0 — 2026-07-15

Initial public release.

- Native SOAP integration for the Innoxel Master 3 home automation controller
- Platforms: `cover`, `switch`, `light`, `binary_sensor`, `sensor`, `climate`
- Covers use the Innoxel virtual InModule channels for full-travel movement (`autoImpulse`) when a matching input channel is found (fuzzy name matching against the configured output channel name), falling back to a short output pulse otherwise
- Weather station sensors (temperature, wind, sun brightness per direction, twilight, rain, sensor error) via `masterWeatherModule`
- Time switch (`masterTimeSwitchModule`) exposed as switches
- Room climate (`masterRoomClimateModule`) exposed as `climate` entities plus actual/target temperature sensors and valve binary sensors
- All entity names, rooms, and channel labels are read live from your own Innoxel controller via SOAP `getIdentity` — nothing is hardcoded
- Config flow for host/port/username/password; digest authentication
