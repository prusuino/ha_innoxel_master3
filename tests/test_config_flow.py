"""Config flow tests: setup with a credential check against the master,
rejected credentials, an unreachable master, a duplicate host, SSDP discovery
and re-authentication. The SOAP client is faked."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.innoxel.const import CONF_ENABLE_COOLING, DOMAIN
from custom_components.innoxel.soap_client import InnoxelAuthError

FLOW = "custom_components.innoxel.config_flow."
INPUT = {CONF_HOST: "192.0.2.20", CONF_PORT: 5001, CONF_USERNAME: "ha", CONF_PASSWORD: "secret", CONF_ENABLE_COOLING: False}


@pytest.fixture
def fake_master():
    """The flow's credential check talks to a faked client, and a created
    entry is not set up (that would start the SOAP worker threads)."""
    with (
        patch(FLOW + "InnoxelSoapClient") as client,
        patch("custom_components.innoxel.async_setup_entry", return_value=True),
    ):
        client.return_value.get_identity = AsyncMock(return_value="<identity/>")
        client.return_value.close = AsyncMock()
        yield client


async def test_setup_checks_the_credentials(hass: HomeAssistant, enable_custom_integrations, fake_master) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Innoxel 192.0.2.20"
    assert result["data"] == INPUT
    fake_master.assert_called_once_with("192.0.2.20", 5001, "ha", "secret")
    fake_master.return_value.close.assert_awaited()


async def test_rejected_credentials_and_unreachable_master(hass: HomeAssistant, enable_custom_integrations, fake_master) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    fake_master.return_value.get_identity.side_effect = InnoxelAuthError("401")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    fake_master.return_value.get_identity.side_effect = OSError("no route")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_same_host_twice_is_refused(hass: HomeAssistant, enable_custom_integrations, fake_master) -> None:
    MockConfigEntry(domain=DOMAIN, title="Innoxel", data=INPUT).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_ssdp_discovery_prefills_host_and_port(hass: HomeAssistant, enable_custom_integrations, fake_master) -> None:
    info = SsdpServiceInfo(
        ssdp_usn="uuid:innoxel-1", ssdp_st="urn:schemas-upnp-org:device:InnoxelMaster:1",
        ssdp_location="http://192.0.2.20:49152/description.xml",
        upnp={"UDN": "uuid:innoxel-1", "presentationURL": "http://192.0.2.20:5001/"},
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=info)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    defaults = result["data_schema"]({CONF_USERNAME: "ha", CONF_PASSWORD: "x"})
    assert defaults[CONF_HOST] == "192.0.2.20" and defaults[CONF_PORT] == 5001
    result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "uuid:innoxel-1"
    # a second discovery of the same master is ignored
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=info)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_stores_the_new_credentials(hass: HomeAssistant, enable_custom_integrations, fake_master) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Innoxel", data=INPUT)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["host"] == "192.0.2.20"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_USERNAME: "ha", CONF_PASSWORD: "new-secret"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"
    assert entry.data[CONF_HOST] == "192.0.2.20"
    fake_master.assert_called_with("192.0.2.20", 5001, "ha", "new-secret")
