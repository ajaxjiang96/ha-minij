"""Read MiniJ appliance status through the MiniJ cloud."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MinijClient
from .const import CONF_TOKEN, DOMAIN, PLATFORMS
from .coordinator import MinijCoordinator

type MinijConfigEntry = ConfigEntry[MinijCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: MinijConfigEntry) -> bool:
    """Set up one MiniJ account."""
    client = MinijClient(async_get_clientsession(hass), entry.data[CONF_TOKEN])
    coordinator = MinijCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MinijConfigEntry) -> bool:
    """Unload MiniJ entities and their shared polling listener."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
