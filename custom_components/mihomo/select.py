import json
import logging

import aiohttp

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CONF_URI, DOMAIN

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, async_add_entities, discovery_info=None):
    if discovery_info is None:
        _LOGGER.warning("No discovery info")
        return

    uri = hass.data[DOMAIN][CONF_URI]
    ps_coor = hass.data[DOMAIN]["ps_coor"]

    for proxy in ps_coor.data:
        if ps_coor.data[proxy]["type"] == "Selector":
            async_add_entities([Selector(proxy, ps_coor, uri)])


class Selector(CoordinatorEntity, SelectEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, sensor_name, coordinator, uri):
        super().__init__(coordinator, context=f"{sensor_name}.now")
        self.sensor_name = sensor_name
        self.uri = uri
        self._attr_unique_id = f"{sensor_name}_select"
        self._attr_name = f"{sensor_name} 当前选择"

    async def async_select_option(self, option: str) -> None:
        body = json.dumps({"name": option})
        async with aiohttp.ClientSession() as session:
            await session.put(
                f"http://{self.uri}/proxies/{self.sensor_name}", data=body
            )
        await self.coordinator.async_request_refresh()

    @property
    def current_option(self):
        return self.coordinator.data[self.sensor_name]["now"]

    @property
    def options(self):
        return self.coordinator.data[self.sensor_name]["all"]

    @property
    def available(self):
        if self.coordinator.data[self.sensor_name]:
            return True
        return False
