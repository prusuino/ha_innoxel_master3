"""Repair notice: a master that has not answered the fast poll for about half
a minute, withdrawn with the next successful poll."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.innoxel import UNREACHABLE_ISSUE_AFTER, InnoxelCoordinator
from custom_components.innoxel.const import DOMAIN

DATA = {CONF_HOST: "192.0.2.20", CONF_PORT: 5001, CONF_USERNAME: "ha", CONF_PASSWORD: "secret"}


async def test_master_unreachable_for_half_a_minute(hass: HomeAssistant, enable_custom_integrations) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="uuid:innoxel-1", title="Innoxel", data=DATA)
    entry.add_to_hass(hass)
    client = MagicMock()
    client.get_state = AsyncMock(side_effect=OSError("no route"))
    coordinator = InnoxelCoordinator(hass, entry, client)
    registry = ir.async_get(hass)
    with (
        patch.object(InnoxelCoordinator, "_load_identity", AsyncMock()),
        patch.object(InnoxelCoordinator, "_parse_state", return_value={"boot_id": "1", "outputs": {}}),
    ):
        coordinator.module_info = {"loaded": True}
        for n in range(UNREACHABLE_ISSUE_AFTER):
            await coordinator.async_refresh()
            issue = registry.async_get_issue(DOMAIN, f"unreachable_{entry.entry_id}")
            assert (issue is not None) is (n == UNREACHABLE_ISSUE_AFTER - 1), f"after poll {n + 1}"
        assert issue.translation_placeholders == {"host": "192.0.2.20"}
        client.get_state = AsyncMock(return_value="<state/>")
        await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert coordinator.data == {"outputs": {}}
    assert registry.async_get_issue(DOMAIN, f"unreachable_{entry.entry_id}") is None
