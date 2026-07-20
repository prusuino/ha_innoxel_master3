from datetime import timedelta
import logging
import re
import time
import unicodedata
from xml.etree import ElementTree as ET

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL, SOAP_NS
from .soap_client import InnoxelSoapClient

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["binary_sensor", "climate", "cover", "light", "sensor", "switch"]
_WEATHER_INTERVAL = 10.0  # seconds between weather/timeswitch updates


def _normalize_tokens(name: str) -> list[str]:
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[^\w\s]", "", name.lower())
    name = re.sub(r"([a-z])(\d)", r"\1 \2", name)
    name = re.sub(r"(\d)([a-z])", r"\1 \2", name)
    return name.split()


def _fuzzy_match(out_base: str, in_base: str) -> float:
    out_tokens = _normalize_tokens(out_base)
    in_tokens = _normalize_tokens(in_base)
    if not out_tokens:
        return 0.0
    in_set = set(in_tokens)
    matched = 0.0
    for ot in out_tokens:
        if ot in in_set:
            matched += 1.0
            continue
        for it in in_tokens:
            if it.startswith(ot) or ot.startswith(it):
                matched += 0.8
                break
    return matched / len(out_tokens)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = InnoxelSoapClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = InnoxelCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].close()
    return unload_ok


class InnoxelCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client: InnoxelSoapClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.client = client
        self.module_info: dict = {}
        self.input_channel_map: dict = {}
        self.time_switch_modules: dict[int, str] = {}
        self.room_climate_modules: dict[int, str] = {}
        self._cached_weather: dict = {}
        self._cached_timeswitch: dict = {}
        self._cached_roomclimate: dict = {}
        self._last_weather_update: float = 0.0

    async def _async_update_data(self) -> dict:
        try:
            if not self.module_info:
                await self._load_identity()
            state = self._parse_state(await self.client.get_state())
            now = time.monotonic()
            if now - self._last_weather_update >= _WEATHER_INTERVAL:
                self._last_weather_update = now
                weather_xml = await self.client.get_weather_state()
                self._cached_weather = self._parse_weather_state(weather_xml)
                ts_xml = await self.client.get_time_switch_state()
                self._cached_timeswitch = self._parse_time_switch_state(ts_xml)
                if self.room_climate_modules:
                    self._cached_roomclimate = await self.client.get_room_climate_state(
                        list(self.room_climate_modules.keys())
                    )
            state["weather"] = self._cached_weather
            state["timeswitch"] = self._cached_timeswitch
            state["roomclimate"] = self._cached_roomclimate
            return state
        except Exception as exc:
            raise UpdateFailed(f"Innoxel update failed: {exc}") from exc

    async def _load_identity(self) -> None:
        xml = await self.client.get_identity()
        root = ET.fromstring(xml)
        ns = {"u": SOAP_NS}

        # Pass 1: collect all module info and raw InModule auf/ab channels
        raw_in: dict = {}
        for mod in root.findall(".//u:module", ns):
            mod_class = mod.get("class")
            mod_idx = int(mod.get("index"))
            key = (mod_class, mod_idx)
            channels = {}
            for ch in mod.findall("u:channel", ns):
                ch_name = ch.get("name")
                if ch_name:
                    ch_idx = int(ch.get("index"))
                    channels[ch_idx] = ch_name
                    if mod_class == "masterInModule":
                        ch_lower = ch_name.lower()
                        for suffix, direction in ((" auf", "up"), (" ab", "down")):
                            if ch_lower.endswith(suffix):
                                base = ch_lower[: -len(suffix)]
                                raw_in.setdefault(base, {})[direction] = (mod_idx, ch_idx)

            if mod_class == "masterTimeSwitchModule":
                name = mod.get("name", f"S{mod_idx + 1}: Zeitschaltuhr")
                if name:
                    self.time_switch_modules[mod_idx] = name
            else:
                self.module_info[key] = {
                    "name": mod.get("name", ""),
                    "description": mod.get("description", ""),
                    "channels": channels,
                }

        # Pass 2: fuzzy-match each OutModule cover to best InModule channel pair
        in_map: dict = {}
        for (mod_class, mod_idx), info in self.module_info.items():
            if mod_class != "masterOutModule" or "Motor" not in info["description"]:
                continue
            ch_names = info.get("channels", {})
            for pair in range(4):
                up_name = ch_names.get(pair * 2, "")
                if not up_name:
                    continue
                cover_base = up_name.lower()
                if cover_base.endswith(" auf"):
                    cover_base = cover_base[: -4]
                best_base, best_score = None, 0.65
                for in_base in raw_in:
                    score = _fuzzy_match(cover_base, in_base)
                    if score > best_score:
                        best_score, best_base = score, in_base
                if best_base:
                    in_map[cover_base] = raw_in[best_base]
                    _LOGGER.debug(
                        "Cover '%s' → InModule '%s' (%.2f)",
                        cover_base, best_base, best_score,
                    )
                else:
                    _LOGGER.debug("Cover '%s': no InModule match", cover_base)

        self.input_channel_map = in_map

        # Pass 3: room climate modules via getState (getIdentity returns HTTP 500 on this firmware)
        try:
            rc_data = await self.client.get_room_climate_state(list(range(9)))
            for idx in rc_data:
                self.room_climate_modules[idx] = f"Raumklima {idx + 1}"
        except Exception as exc:
            _LOGGER.warning("RoomClimate discovery failed: %s", exc)

        _LOGGER.debug(
            "Identity loaded: %d modules, %d timeswitches, %d covers matched, %d roomclimate",
            len(self.module_info), len(self.time_switch_modules), len(in_map),
            len(self.room_climate_modules),
        )

    @staticmethod
    def _parse_weather_state(xml: str) -> dict:
        root = ET.fromstring(xml)
        ns = {"u": SOAP_NS}
        weather: dict = {}
        mod = root.find(".//u:module[@class='masterWeatherModule']", ns)
        if mod is None:
            return weather

        for key, elem_name in (
            ("temperature_air",  "temperatureAir"),
            ("temperature_felt", "temperatureAirFelt"),
            ("wind_ms",          "windSpeed"),
            ("sun_east",         "sunBrightnessEast"),
            ("sun_south",        "sunBrightnessSouth"),
            ("sun_west",         "sunBrightnessWest"),
        ):
            el = mod.find(f"u:{elem_name}", ns)
            if el is not None:
                try:
                    weather[key] = float(el.get("value"))
                except (TypeError, ValueError):
                    pass


        el = mod.find("u:sunTwilight", ns)
        if el is not None:
            try:
                weather["twilight_lux"] = float(el.get("value"))
            except (TypeError, ValueError):
                pass
            # Innoxel reports boolean attributes as "yes"/"no", not "true"/"false"
            weather["civil_twilight"] = el.get("isCivilTwilight", "").lower() in ("yes", "true")

        el = mod.find("u:precipitation", ns)
        if el is not None:
            raw = (el.get("value") or "").strip().lower()
            # Only "dry" has ever been observed live; the wet-side value was
            # never captured. Treat anything else as rain and expose the raw
            # value as a sensor attribute so the real wet-side value shows
            # up the next time it rains.
            weather["rain"] = raw not in ("", "dry")
            weather["rain_raw"] = raw

        el = mod.find("u:state", ns)
        if el is not None:
            err = el.find("u:error", ns)
            if err is not None:
                try:
                    weather["sensor_error"] = int(err.get("value", 0)) != 0
                except (TypeError, ValueError):
                    weather["sensor_error"] = False

        return weather

    @staticmethod
    def _parse_time_switch_state(xml: str) -> dict:
        root = ET.fromstring(xml)
        ns = {"u": SOAP_NS}
        ts: dict = {}
        for mod in root.findall(".//u:module", ns):
            if mod.get("class") != "masterTimeSwitchModule":
                continue
            try:
                idx = int(mod.get("index", -1))
            except (TypeError, ValueError):
                continue
            state_el = mod.find("u:state", ns)
            if state_el is not None:
                ts[idx] = state_el.get("operatingState", "disabled")
        return ts

    @staticmethod
    def _parse_state(xml: str) -> dict:
        root = ET.fromstring(xml)
        ns = {"u": SOAP_NS}
        state: dict = {}
        for mod in root.findall(".//u:module", ns):
            key = (mod.get("class"), int(mod.get("index")))
            channels: dict = {}
            for ch in mod.findall("u:channel", ns):
                out = ch.get("outState")
                if out is not None:
                    channels[int(ch.get("index"))] = out
            state[key] = {"module_state": mod.get("state"), "channels": channels}
        return state
