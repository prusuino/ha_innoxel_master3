from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .const import DEFAULT_PORT, DOMAIN
from .soap_client import InnoxelSoapClient


class InnoxelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo):
        host = urlparse(discovery_info.ssdp_location or "").hostname
        if not host:
            return self.async_abort(reason="cannot_connect")

        udn = discovery_info.upnp.get("UDN")
        if udn:
            await self.async_set_unique_id(udn)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        # Entries created before unique IDs existed match on host only
        self._async_abort_entries_match({CONF_HOST: host})

        # The SOAP endpoint lives on the web server port (presentationURL),
        # not on the UPnP description port from ssdp_location.
        presentation = discovery_info.upnp.get("presentationURL", "")
        port = urlparse(presentation).port or DEFAULT_PORT

        self._discovered_host = host
        self._discovered_port = port
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            client = InnoxelSoapClient(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.get_identity()
                self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(
                    title=f"Innoxel {user_input[CONF_HOST]}",
                    data=user_input,
                )
            except AbortFlow:
                raise
            except Exception:
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=self._discovered_host or vol.UNDEFINED): str,
                vol.Optional(CONF_PORT, default=self._discovered_port): int,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
