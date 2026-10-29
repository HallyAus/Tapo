"""Tests for the cloud coordinator (Tapo #1)."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.tapo_cloud.coordinator import TapoCloudCoordinator


async def test_offline_device_skip_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """A device the cloud reports with status 0 is skipped with a DEBUG line."""
    bridge = MagicMock()
    bridge.async_get_devices = AsyncMock(
        return_value=[
            {"deviceId": "dev1", "alias": "Lounge", "deviceModel": "L510E", "status": 0}
        ]
    )
    bridge.async_device_request = AsyncMock()

    coordinator = MagicMock()
    coordinator.entry.options = {"local_probe": False}
    coordinator.bridge = bridge

    caplog.set_level(logging.DEBUG, logger="custom_components.tapo_cloud.coordinator")
    devices = await TapoCloudCoordinator._async_update_data(coordinator)

    assert not devices["dev1"].online
    bridge.async_device_request.assert_not_called()
    assert "Skipping Lounge (L510E): cloud reports status 0, not online" in caplog.text
