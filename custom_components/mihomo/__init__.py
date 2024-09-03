from datetime import timedelta
import logging

import aiohttp
import voluptuous as vol

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
DOMAIN = "mihomo"
CONF_SENSOR_NAME = "sensor_name"
CONF_URI = "uri"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: {
            vol.Required(CONF_URI): cv.string,
        }
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    uri = config[DOMAIN][CONF_URI]
    ps_coor = ProxyStatusCoordinator(hass, uri)
    await ps_coor.async_config_entry_first_refresh()
    hass.data[DOMAIN] = {CONF_URI: uri, "ps_coor": ps_coor}
    await hass.helpers.discovery.async_load_platform(Platform.SENSOR, DOMAIN, {}, {})
    hass.helpers.discovery.load_platform(Platform.SELECT, DOMAIN, {}, {})
    return True


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
            return (await response.json(content_type=None))["proxies"]
