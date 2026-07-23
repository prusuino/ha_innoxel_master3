from __future__ import annotations
import asyncio
import logging
import time

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_CLOSED, STATE_OPEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Max seconds after a move command during which stop is allowed via last_direction fallback.
# Innoxel Vollfahrt is typically 20-60 s; 90 s leaves margin for slow stores.
_MOVE_TIMEOUT = 65.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    in_map = coordinator.input_channel_map

    entities = []
    for (mod_class, mod_index), info in coordinator.module_info.items():
        if mod_class != "masterOutModule" or "Motor" not in info["description"]:
            continue
        ch_names = info.get("channels", {})
        for pair in range(4):
            ch_up = pair * 2
            ch_down = pair * 2 + 1
            up_name = ch_names.get(ch_up, "")
            if not up_name:
                continue
            cover_base = up_name
            for suffix in (" auf", " Auf", " AUF"):
                if cover_base.endswith(suffix):
                    cover_base = cover_base[: -len(suffix)]
                    break
            in_entry = in_map.get(cover_base.lower(), {})
            in_up = in_entry.get("up")
            in_down = in_entry.get("down")
            entities.append(
                InnoxelCover(
                    coordinator, client, entry.entry_id,
                    mod_index, pair, ch_up, ch_down,
                    cover_base, in_up, in_down,
                )
            )

    # Motor G2 blind modules (masterBlindModule): native position/tilt support.
    # EXPERIMENTAL — implemented from the Innoxel WebApp SOAP protocol without
    # G2 hardware available; scale direction assumptions need field feedback.
    for mod_index, info in sorted(coordinator.blind_modules.items()):
        for ch_idx, ch_name in sorted(info["channels"].items()):
            entities.append(
                InnoxelBlindCover(
                    coordinator, client, entry.entry_id, mod_index, ch_idx, ch_name
                )
            )
    async_add_entities(entities)


class InnoxelCover(CoordinatorEntity, CoverEntity, RestoreEntity):
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
    )

    def __init__(self, coordinator, client, entry_id,
                 mod_index, pair, ch_up, ch_down, description, in_up, in_down):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._client = client
        self._mod_index = mod_index
        self._ch_up = ch_up
        self._ch_down = ch_down
        self._in_up = in_up
        self._in_down = in_down
        self._description = description
        self._attr_name = f"[o{mod_index:02d}-k{pair}] {description}"
        self._attr_unique_id = f"innoxel_{entry_id}_cover_{mod_index}_{pair}"
        # Optimistic state: None=unknown, True=closed, False=open
        self._assumed_closed: bool | None = None
        # Last direction commanded by HA ("up"/"down"), with its start timestamp.
        # Used as fallback in stop when the Innoxel SOAP API returns no relay state.
        # The Innoxel masterOutModule.outState is ALWAYS "off" for motor channels —
        # the API does not expose running relay state for CAN-bus motor modules.
        self._last_direction: str | None = None
        self._last_move_ts: float = 0.0

    @property
    def extra_state_attributes(self) -> dict:
        return {"bezeichnung": self._description} if self._description else {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state == STATE_CLOSED:
                self._assumed_closed = True
            elif last_state.state == STATE_OPEN:
                self._assumed_closed = False

    @property
    def is_closed(self) -> bool | None:
        if self._within_move_timeout():
            return None  # unknown while moving → both buttons stay active in the UI
        return self._assumed_closed

    def _within_move_timeout(self) -> bool:
        return (
            self._last_direction is not None
            and (time.monotonic() - self._last_move_ts) <= _MOVE_TIMEOUT
        )

    async def _pulse_up(self) -> None:
        if self._in_up:
            await self._client.trigger_in_module(*self._in_up)
        else:
            await self._client.trigger_out_module(self._mod_index, self._ch_up, "set")
            await asyncio.sleep(0.15)
            await self._client.trigger_out_module(self._mod_index, self._ch_up, "clear")

    async def _pulse_down(self) -> None:
        if self._in_down:
            await self._client.trigger_in_module(*self._in_down)
        else:
            await self._client.trigger_out_module(self._mod_index, self._ch_down, "set")
            await asyncio.sleep(0.15)
            await self._client.trigger_out_module(self._mod_index, self._ch_down, "clear")

    async def async_open_cover(self, **kwargs) -> None:
        if self._within_move_timeout() and self._last_direction == "up":
            # Second press in same direction while moving → stop
            await self._pulse_up()
            self._last_direction = None
            self._last_move_ts = 0.0
            self._assumed_closed = None  # unknown after stop → both buttons stay active
        else:
            await self._pulse_up()
            self._assumed_closed = False
            self._last_direction = "up"
            self._last_move_ts = time.monotonic()
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs) -> None:
        if self._within_move_timeout() and self._last_direction == "down":
            # Second press in same direction while moving → stop
            await self._pulse_down()
            self._last_direction = None
            self._last_move_ts = 0.0
            self._assumed_closed = None  # unknown after stop → both buttons stay active
        else:
            await self._pulse_down()
            self._assumed_closed = True
            self._last_direction = "down"
            self._last_move_ts = time.monotonic()
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs) -> None:
        # Determine which direction signal to send.
        # outState is always "off" for Innoxel motor modules — use _last_direction
        # as fallback, but only if the move was started recently (within _MOVE_TIMEOUT).
        direction = self._last_direction
        if direction and (time.monotonic() - self._last_move_ts) > _MOVE_TIMEOUT:
            _LOGGER.debug("Cover '%s': move timeout expired, discarding last_direction", self.name)
            direction = None

        if direction == "up":
            if self._in_up:
                await self._client.trigger_in_module(*self._in_up)
            else:
                await self._client.trigger_out_module(self._mod_index, self._ch_up)
        elif direction == "down":
            if self._in_down:
                await self._client.trigger_in_module(*self._in_down)
            else:
                await self._client.trigger_out_module(self._mod_index, self._ch_down)
        else:
            _LOGGER.debug("Cover '%s': stop called with no active direction — nothing sent", self.name)

        self._last_direction = None
        self._last_move_ts = 0.0

    def _channels(self) -> dict:
        state = self.coordinator.data or {}
        return state.get(("masterOutModule", self._mod_index), {}).get("channels", {})


class InnoxelBlindCover(CoordinatorEntity, CoverEntity):
    """Motor G2 blind channel (masterBlindModule) with real position feedback.

    Innoxel raw scale is 0-1000 for both position and tilt, -1 = position
    unknown (e.g. after manual override, before the position tracker resynced).
    Assumed direction (needs confirmation from G2 hardware): raw position 0 =
    fully open (top end position), raw 1000 = fully closed. Tilt is mapped the
    way the Innoxel WebApp displays it (raw 1000 = slider 0%).
    """

    _attr_device_class = CoverDeviceClass.BLIND
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.STOP_TILT
        | CoverEntityFeature.SET_TILT_POSITION
    )

    def __init__(self, coordinator, client, entry_id, mod_index, channel, name):
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._client = client
        self._mod_index = mod_index
        self._channel = channel
        self._attr_name = f"[b{mod_index:02d}-{channel}] {name}"
        self._attr_unique_id = f"innoxel_{entry_id}_blind_{mod_index}_{channel}"
        self.entity_id = f"cover.innoxel_b{mod_index:02d}_{channel}"

    def _raw(self) -> dict:
        state = self.coordinator.data or {}
        channels = state.get(("masterBlindModule", self._mod_index), {}).get("channels", {})
        val = channels.get(self._channel)
        return val if isinstance(val, dict) else {}

    @property
    def current_cover_position(self) -> int | None:
        pos = self._raw().get("position", -1)
        if pos < 0:
            return None
        return max(0, min(100, 100 - round(pos / 10)))

    @property
    def current_cover_tilt_position(self) -> int | None:
        tilt = self._raw().get("tilt", -1)
        if tilt < 0:
            return None
        return max(0, min(100, 100 - round(tilt / 10)))

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    @property
    def extra_state_attributes(self) -> dict:
        raw = self._raw()
        return {
            "raw_position": raw.get("position"),
            "raw_tilt": raw.get("tilt"),
        }

    async def async_open_cover(self, **kwargs) -> None:
        await self._client.set_blind_position(self._mod_index, self._channel, position=0)

    async def async_close_cover(self, **kwargs) -> None:
        await self._client.set_blind_position(self._mod_index, self._channel, position=1000)

    async def async_set_cover_position(self, **kwargs) -> None:
        ha_pos = kwargs["position"]
        await self._client.set_blind_position(
            self._mod_index, self._channel, position=(100 - ha_pos) * 10
        )

    async def async_open_cover_tilt(self, **kwargs) -> None:
        await self._client.set_blind_position(self._mod_index, self._channel, tilt=0)

    async def async_close_cover_tilt(self, **kwargs) -> None:
        await self._client.set_blind_position(self._mod_index, self._channel, tilt=1000)

    async def async_set_cover_tilt_position(self, **kwargs) -> None:
        ha_tilt = kwargs["tilt_position"]
        await self._client.set_blind_position(
            self._mod_index, self._channel, tilt=(100 - ha_tilt) * 10
        )

    async def async_stop_cover(self, **kwargs) -> None:
        await self._client.halt_blind(self._mod_index, self._channel)

    async def async_stop_cover_tilt(self, **kwargs) -> None:
        await self._client.halt_blind(self._mod_index, self._channel)
