import asyncio
from datetime import datetime, timedelta
import json
import logging

import aiohttp
import voluptuous as vol
import websockets

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "mihomo"

CONF_SENSOR_NAME = "sensor_name"
CONF_URI = "uri"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_SENSOR_NAME): cv.string,
        vol.Required(CONF_URI): cv.string,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    sensor_name = config[CONF_SENSOR_NAME]
    uri = config[CONF_URI]

    coordinator = MyCoordinator(hass, uri)
    await coordinator.async_config_entry_first_refresh()
    async_add_entities(
        [
            MyWebSocketSensor(f"{sensor_name}_up", coordinator, "up"),
            MyWebSocketSensor(f"{sensor_name}_down", coordinator, "down"),
        ]
    )

    ps_coor = ProxyStatusCoordinator(hass, uri)
    await ps_coor.async_config_entry_first_refresh()
    for proxy in ps_coor.data:
        async_add_entities(
            [
                LastSpeedTestTimeSensor(proxy, ps_coor),
                DelaySensor(proxy, ps_coor),
            ]
        )


class MyCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, uri):
        super().__init__(hass, _LOGGER, name="Mihomo sensor", always_update=True)
        self.uri = f"ws://{uri}/traffic"
        self.hass = hass

    async def async_config_entry_first_refresh(self):
        websocket = await websockets.connect(self.uri)

        async def handle_message(message):
            try:
                data = json.loads(message)
                self.async_set_updated_data(data)
            except json.JSONDecodeError:
                _LOGGER.error("Invalid JSON message received: %s", message)

        async def websocket_handler():
            nonlocal websocket
            while True:
                try:
                    message = await websocket.recv()
                    await handle_message(message)
                except websockets.ConnectionClosed:
                    _LOGGER.warning(
                        "WebSocket connection closed. Retrying in 3 seconds"
                    )
                    await asyncio.sleep(3)
                    websocket = await websockets.connect(self.uri)

        self.hass.loop.create_task(websocket_handler())


class MyWebSocketSensor(CoordinatorEntity, SensorEntity):
    _attr_native_unit_of_measurement = "B/s"
    _attr_state_class = "measurement"
    _attr_device_class = "data_rate"
    _attr_should_poll = False

    def __init__(self, sensor_name, coordinator, up_down):
        super().__init__(coordinator, context=up_down)
        self._attr_unique_id = sensor_name
        self.up_down = up_down

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self.coordinator.data[self.up_down]
        self.async_write_ha_state()


class ProxyStatusCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, uri):
        super().__init__(
            hass,
            _LOGGER,
            name="Mihomo proxy status",
            always_update=True,
            update_interval=timedelta(seconds=15),
        )
        self.hass = hass
        self.uri = f"http://{uri}/proxies"

    async def _async_update_data(self):
        async with (
            aiohttp.ClientSession() as session,
            session.get(self.uri) as response,
        ):
            return (await response.json())["proxies"]


class LastSpeedTestTimeSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_device_class = "date"
    _attr_has_entity_name = True

    def __init__(self, sensor_name, coordinator):
        super().__init__(coordinator, context=f"{sensor_name}.history")
        self.sensor_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_last_speed_test_time"
        self._attr_name = f"{sensor_name} 上次测速时间"

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self.coordinator.data[self.sensor_name]:
            return self.set_unavailble()
        history = self.coordinator.data[self.sensor_name]["history"]
        if not history:
            return self.set_unavailble()
        item = history[-1]
        self._attr_native_value = datetime.fromisoformat(item["time"])
        self.async_write_ha_state()

    def set_unavailble(self):
        self._attr_available = False
        self.async_write_ha_state()


class DelaySensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_device_class = "duration"
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "ms"
    _attr_suggested_unit_of_measurement = "ms"

    def __init__(self, sensor_name, coordinator):
        super().__init__(coordinator, context=f"{sensor_name}.history")
        self.sensor_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_delay"
        self._attr_name = sensor_name

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self.coordinator.data[self.sensor_name]:
            return self.set_unavailble()
        history = self.coordinator.data[self.sensor_name]["history"]
        if not history:
            return self.set_unavailble()
        item = history[-1]
        if not item["delay"]:
            return self.set_unavailble()
        self._attr_native_value = item["delay"]
        self.async_write_ha_state()

    def set_unavailble(self):
        self._attr_available = False
        self.async_write_ha_state()
