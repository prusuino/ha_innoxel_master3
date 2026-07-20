# Changelog

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
