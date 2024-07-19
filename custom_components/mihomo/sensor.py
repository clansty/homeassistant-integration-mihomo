import asyncio
from datetime import datetime, timedelta
import json
import logging

import aiohttp
import voluptuous as vol
import websockets

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
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
        if ps_coor.data[proxy]["type"] == "Fallback":
            async_add_entities([FallbackCurrentSensor(proxy, ps_coor)])


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

    @property
    def native_value(self):
        return self.coordinator.data[self.up_down]

    @property
    def available(self):
        return bool(self.coordinator.data)


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

    @property
    def native_value(self):
        history = self.coordinator.data[self.sensor_name]["history"]
        item = history[-1]
        return datetime.fromisoformat(item["time"])

    @property
    def available(self):
        if not self.coordinator.data[self.sensor_name]:
            return False
        history = self.coordinator.data[self.sensor_name]["history"]
        if not history:
            return False
        return True


class DelaySensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_device_class = "duration"
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "ms"
    _attr_suggested_unit_of_measurement = "ms"
    _attr_suggested_display_precision = 0

    def __init__(self, sensor_name, coordinator):
        super().__init__(coordinator, context=f"{sensor_name}.history")
        self.sensor_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_delay"
        self._attr_name = sensor_name

    @property
    def native_value(self):
        history = self.coordinator.data[self.sensor_name]["history"]
        item = history[-1]
        return item["delay"]

    @property
    def available(self):
        if not self.coordinator.data[self.sensor_name]:
            return False
        history = self.coordinator.data[self.sensor_name]["history"]
        if not history:
            return False
        item = history[-1]
        return bool(item["delay"])


class FallbackCurrentSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, sensor_name, coordinator):
        super().__init__(coordinator, context=f"{sensor_name}.now")
        self.sensor_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_current"
        self._attr_name = f"{sensor_name} 当前选择"

    @property
    def native_value(self):
        return self.coordinator.data[self.sensor_name]["now"]

    @property
    def available(self):
        if self.coordinator.data[self.sensor_name]:
            return True
        return False
