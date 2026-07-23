from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .const import CONF_ENABLE_COOLING, DEFAULT_PORT, DOMAIN
from .soap_client import InnoxelSoapClient


class InnoxelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "InnoxelOptionsFlow":
        return InnoxelOptionsFlow()

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
                vol.Optional(CONF_ENABLE_COOLING, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )


class InnoxelOptionsFlow(config_entries.OptionsFlow):
    """View/change connection settings and toggle cooling controls without re-adding."""

    async def async_step_init(self, user_input=None):
        errors = {}
        entry = self.config_entry

        if user_input is not None:
            connection = {
                CONF_HOST: user_input[CONF_HOST],
                CONF_PORT: user_input[CONF_PORT],
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            client = InnoxelSoapClient(
                connection[CONF_HOST],
                connection[CONF_PORT],
                connection[CONF_USERNAME],
                connection[CONF_PASSWORD],
            )
            try:
                await client.get_identity()
            except Exception:
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

            if not errors:
                if connection != {k: entry.data.get(k) for k in connection}:
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, **connection}
                    )
                return self.async_create_entry(
                    title="",
                    data={CONF_ENABLE_COOLING: user_input[CONF_ENABLE_COOLING]},
                )

        source = user_input or entry.data
        cooling = (
            user_input[CONF_ENABLE_COOLING]
            if user_input is not None
            else entry.options.get(
                CONF_ENABLE_COOLING, entry.data.get(CONF_ENABLE_COOLING, False)
            )
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=source.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PORT, default=source.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Required(CONF_USERNAME, default=source.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD, default=source.get(CONF_PASSWORD, "")): str,
                vol.Optional(CONF_ENABLE_COOLING, default=cooling): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
