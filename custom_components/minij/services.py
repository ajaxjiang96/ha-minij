"""Single-device program actions using HA entity authorization and dispatch."""

import probatio
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform, service

from .const import DOMAIN

_LABEL = probatio.All(str, probatio.Length(min=1))
_START_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_id,
        probatio.Required("program"): _LABEL,
        probatio.Optional("parameters", default=dict): {_LABEL: _LABEL},
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register once; resolve live entities on every call, including after reload."""
    if hass.services.has_service(DOMAIN, "start_program"):
        return

    async def start_program(call: ServiceCall) -> dict | None:
        # Import after platform setup to avoid the config-entry type import cycle.
        from .button import MinijStartProgramButton

        entities = {
            entity.entity_id: entity
            for platform in entity_platform.async_get_platforms(hass, DOMAIN)
            if platform.domain == "button"
            for entity in platform.entities.values()
            if isinstance(entity, MinijStartProgramButton)
        }
        if (
            call.data[ATTR_ENTITY_ID] not in entities
            or not entities[call.data[ATTR_ENTITY_ID]].available
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="program_target_unavailable"
            )
        return await service.entity_service_call(
            hass, entities, "async_start_with_parameters", call
        )

    hass.services.async_register(
        DOMAIN,
        "start_program",
        start_program,
        _START_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
