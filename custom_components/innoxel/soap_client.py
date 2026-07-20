import asyncio
import functools
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SOAP_NS = "urn:innoxel-ch:service:noxnetRemote:1"

_executor = ThreadPoolExecutor(max_workers=2)
_LOGGER = logging.getLogger(__name__)


def _sync_soap_call(url: str, username: str, password: str, action: str, body: str) -> str:
    soap = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        f'<u:{action} xmlns:u="{SOAP_NS}">{body}</u:{action}>'
        "</s:Body></s:Envelope>"
    ).encode("utf-8")

    pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    base = url.rsplit("/", 1)[0] + "/"
    pm.add_password(None, base, username, password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(pm))
    req = urllib.request.Request(url, data=soap, method="POST")
    req.add_header("Content-Type", 'text/xml; charset="utf-8"')
    req.add_header("soapaction", f"{SOAP_NS}#{action}")
    _LOGGER.debug("SOAP %s user=%s", action, username)
    try:
        with opener.open(req, timeout=10) as r:
            result = r.read().decode("utf-8", errors="replace")
            _LOGGER.debug("SOAP %s -> HTTP %s, body=%s", action, r.status, result[:80])
            return result
    except urllib.error.HTTPError as exc:
        _LOGGER.error("SOAP %s HTTP error %s: %s", action, exc.code, exc.read(200))
        raise
    except Exception as exc:
        _LOGGER.error("SOAP %s error: %s", action, exc)
        raise


class InnoxelSoapClient:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self._url = f"http://{host}:{port}/control"
        self._username = username
        self._password = password

    async def _post(self, action: str, body: str) -> str:
        loop = asyncio.get_running_loop()
        fn = functools.partial(
            _sync_soap_call, self._url, self._username, self._password, action, body
        )
        return await loop.run_in_executor(_executor, fn)

    async def get_identity(self) -> str:
        body = (
            "<u:moduleList>"
            '<u:module class="masterOutModule" index="-1"><u:channel index="-1"/></u:module>'
            '<u:module class="masterDimModule" index="-1"><u:channel index="-1"/></u:module>'
            '<u:module class="masterInModule" index="-1"><u:channel index="-1"/></u:module>'
            '<u:module class="masterTimeSwitchModule" index="-1"/>'
            "</u:moduleList>"
        )
        return await self._post("getIdentity", body)

    async def get_state(self) -> str:
        body = (
            "<u:moduleList>"
            '<u:module class="masterOutModule" index="-1"><u:channel index="-1"/></u:module>'
            '<u:module class="masterDimModule" index="-1"><u:channel index="-1"/></u:module>'
            "</u:moduleList>"
        )
        return await self._post("getState", body)

    async def get_weather_state(self) -> str:
        body = (
            "<u:moduleList>"
            '<u:module class="masterWeatherModule" index="-1"/>'
            "</u:moduleList>"
        )
        return await self._post("getState", body)

    async def get_room_climate_state(self, indices: list[int]) -> dict:
        """Query each module individually — batch requests cause HTTP 500."""
        import asyncio
        from xml.etree import ElementTree as ET
        result: dict = {}
        ns = {"u": SOAP_NS}
        for i in indices:
            await asyncio.sleep(0.15)
            body = (
                f'<u:moduleList>'
                f'<u:module class="masterRoomClimateModule" index="{i}">'
                "<u:thermostat>"
                "<u:actualTemperatureMean/>"
                "<u:setTemperatureHeating/>"
                "<u:nightSetbackTemperatureHeating/>"
                "</u:thermostat>"
                "</u:module>"
                "</u:moduleList>"
            )
            try:
                xml = await self._post("getState", body)
                root = ET.fromstring(xml)
                thermo = root.find(".//u:thermostat", ns)
                if thermo is None:
                    continue
                data: dict = {}
                for key, elem in (("actual_temp", "actualTemperatureMean"), ("set_temp", "setTemperatureHeating")):
                    el = thermo.find(f"u:{elem}", ns)
                    if el is not None:
                        try:
                            data[key] = float(el.get("value"))
                        except (TypeError, ValueError):
                            pass
                valve = thermo.get("valveState", "")
                data["valve_open"] = valve.lower() not in ("", "closed", "0", "false")
                result[i] = data
            except Exception:
                pass
        return result

    async def get_device_state(self) -> str:
        """Master hardware diagnostics (voltages, CPU temps, bus supply states)."""
        return await self._post("getDeviceStateList", "")

    async def get_time_switch_state(self) -> str:
        body = (
            "<u:moduleList>"
            '<u:module class="masterTimeSwitchModule" index="-1"/>'
            "</u:moduleList>"
        )
        return await self._post("getState", body)

    async def set_room_climate_temperature(self, index: int, temperature: float) -> None:
        body = (
            "<u:moduleList>"
            f'<u:module class="masterRoomClimateModule" index="{index}">'
            "<u:thermostat>"
            f'<u:setTemperatureHeating value="{temperature:.1f}"/>'
            "</u:thermostat>"
            "</u:module>"
            "</u:moduleList>"
        )
        await self._post("setState", body)

    async def set_time_switch_state(self, index: int, enabled: bool) -> None:
        state = "enabled" if enabled else "disabled"
        body = (
            "<u:moduleList>"
            f'<u:module class="masterTimeSwitchModule" index="{index}">'
            f'<u:state operatingState="{state}"/>'
            "</u:module>"
            "</u:moduleList>"
        )
        await self._post("setState", body)

    async def trigger_out_module(
        self, module_index: int, channel_index: int, event: str = "toggle"
    ) -> None:
        body = (
            "<u:moduleList>"
            f'<u:module class="masterOutModule" index="{module_index}">'
            f'<u:channel index="{channel_index}" perform="{event}"/>'
            "</u:module></u:moduleList>"
        )
        await self._post("setState", body)

    async def trigger_in_module(
        self, module_index: int, channel_index: int, event: str = "autoImpulse"
    ) -> None:
        body = (
            "<u:moduleList>"
            f'<u:module class="masterInModule" index="{module_index}">'
            f'<u:channel index="{channel_index}" perform="{event}"/>'
            "</u:module></u:moduleList>"
        )
        await self._post("setState", body)

    async def set_dim_value(self, module_index: int, channel_index: int, value: int) -> None:
        body = (
            "<u:moduleList>"
            f'<u:module class="masterDimModule" index="{module_index}">'
            f'<u:channel index="{channel_index}" dimValue="{value}" dimSpeed="0"/>'
            "</u:module></u:moduleList>"
        )
        await self._post("setState", body)

    async def close(self) -> None:
        pass
