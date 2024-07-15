import asyncio
import json
import logging
import voluptuous as vol
from homeassistant.components.sensor import (PLATFORM_SCHEMA, SensorEntity)
import homeassistant.helpers.config_validation as cv
import websockets
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity, DataUpdateCoordinator)
from homeassistant.core import callback

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
    async_add_entities([MyWebSocketSensor(f"{sensor_name}_up", coordinator, "up"), MyWebSocketSensor(
        f"{sensor_name}_down", coordinator, "down")])


class MyCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, uri):
        super().__init__(
            hass,
            _LOGGER,
            name="Mihomo sensor",
            always_update=True
        )
        self.uri = uri
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
                        "WebSocket connection closed. Retrying in 3 seconds.")
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
