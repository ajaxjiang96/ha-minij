"""Single-call starts use explicit input, not another caller's UI draft."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import probatio
import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from test_homeassistant import (  # noqa: F401
    api,
    configure,
    entity_ids,
    hass,
    parameter_metadata,
    program_metadata,
)
from test_programs import PARAMETER, PROGRAM_A, PROGRAM_B, parameters
from test_programs import controls as program_controls  # noqa: F401
from test_start_program import start_button  # noqa: F401

from custom_components.minij.api import (
    MinijAuthError,
    MinijClient,
    MinijError,
    MinijRateLimitError,
)


async def test_action_uses_explicit_program_and_zero_without_touching_drafts(
    start_button,  # noqa: F811
):
    controls = start_button.controls
    controls.select_parameter(PARAMETER["code"], "30℃")
    before = controls.data
    result = await start_button.async_start_with_parameters(
        "单脱水", {PARAMETER["code"]: "不加热"}
    )
    assert result == {"status": "accepted", "program": "单脱水"}
    controls.parent.client.async_start_program.assert_awaited_once_with(
        controls.device_id,
        PROGRAM_B["id"],
        [
            {
                "userDeviceModeStatsId": PARAMETER["id"],
                "code": PARAMETER["code"],
                "value": "0",
            }
        ],
    )
    assert controls.data == before
    controls.parent.client.async_power_on.assert_not_awaited()


@pytest.mark.parametrize(
    "program, choices",
    [
        ("不存在", {}),
        ("标准", {"missing": "不加热"}),
        ("标准", {PARAMETER["code"]: "不存在"}),
    ],
)
async def test_invalid_action_choices_never_start(start_button, program, choices):  # noqa: F811
    with pytest.raises(HomeAssistantError):
        await start_button.async_start_with_parameters(program, choices)
    start_button.coordinator.client.async_start_program.assert_not_awaited()


async def test_action_reads_selected_program_fresh_and_ignores_other_program_ids(
    start_button,  # noqa: F811
):
    client = start_button.coordinator.client

    async def read(device, program):
        raw = deepcopy(PARAMETER)
        if program == PROGRAM_B["id"]:
            raw["id"] = "fresh-selected-id"
            raw["optionalValueList"][1]["value"] = 9
        return parameters([raw])

    client.async_get_program_parameters.side_effect = read
    await start_button.async_start_with_parameters("单脱水", {PARAMETER["code"]: "30℃"})
    assert client.async_start_program.await_args.args[2][0] == {
        "userDeviceModeStatsId": "fresh-selected-id",
        "code": PARAMETER["code"],
        "value": "9",
    }


async def test_concurrent_calls_keep_program_and_parameters_together(start_button):  # noqa: F811
    client = start_button.coordinator.client
    entered, release = asyncio.Event(), asyncio.Event()

    async def command(*args):
        if client.async_start_program.await_count == 1:
            entered.set()
            await release.wait()

    client.async_start_program.side_effect = command
    first = asyncio.create_task(
        start_button.async_start_with_parameters("标准", {PARAMETER["code"]: "30℃"})
    )
    await entered.wait()
    second = asyncio.create_task(
        start_button.async_start_with_parameters(
            "单脱水", {PARAMETER["code"]: "不加热"}
        )
    )
    await asyncio.sleep(0)
    assert client.async_start_program.await_count == 1
    release.set()
    await asyncio.gather(first, second)
    assert [
        (c.args[1], c.args[2][0]["value"])
        for c in client.async_start_program.await_args_list
    ] == [(PROGRAM_A["id"], "2"), (PROGRAM_B["id"], "0")]


@pytest.mark.parametrize("condition", ["unloaded", "removed", "catalog_changed"])
async def test_action_rechecks_after_target_parameter_read(start_button, condition):  # noqa: F811
    controls = start_button.controls

    async def read(device, program):
        if program == PROGRAM_B["id"]:
            if condition == "unloaded":
                start_button._active = False
            elif condition == "removed":
                controls.parent.data.clear()
            else:
                from dataclasses import replace

                controls.async_set_updated_data(
                    replace(controls.data, programs=(controls.data.programs[0],))
                )
        return parameters()

    controls.parent.client.async_get_program_parameters.side_effect = read
    with pytest.raises(HomeAssistantError):
        await start_button.async_start_with_parameters("单脱水", {})
    controls.parent.client.async_start_program.assert_not_awaited()


@pytest.mark.parametrize("phase", ["read", "send"])
@pytest.mark.parametrize("kind", ["auth", "rate", "uncertain"])
async def test_action_errors_are_private_and_single_attempt(start_button, phase, kind):  # noqa: F811
    parent = start_button.coordinator
    parent.config_entry = SimpleNamespace(async_start_reauth=Mock())
    error = {
        "auth": MinijAuthError,
        "rate": MinijRateLimitError,
        "uncertain": MinijError,
    }[kind]
    if phase == "read":

        async def read(device, program):
            if program == PROGRAM_B["id"]:
                raise error("private-canary")
            return parameters()

        parent.client.async_get_program_parameters.side_effect = read
    else:
        parent.client.async_start_program.side_effect = error("private-canary")
    with pytest.raises(HomeAssistantError) as caught:
        await start_button.async_start_with_parameters("单脱水", {})
    assert "private-canary" not in str(caught.value)
    assert (
        caught.value.translation_key
        == {
            "auth": "control_auth_failed",
            "rate": "control_rate_limited",
            "uncertain": "control_read_failed"
            if phase == "read"
            else "control_send_uncertain",
        }[kind]
    )
    assert parent.client.async_start_program.await_count == (phase == "send")
    parent.client.async_power_on.assert_not_awaited()


async def prepare_action(hass):  # noqa: F811
    MinijClient.async_get_programs.return_value = program_metadata()
    MinijClient.async_get_program_parameters.side_effect = (
        lambda device_id, program_id: parameter_metadata(program_id)
    )
    entry = await configure(hass)
    return entry, entity_ids(hass)["start_program"]


async def test_real_ha_action_response_draft_isolation_and_reload(hass, api):  # noqa: F811
    entry, entity = await prepare_action(hass)
    ids = entity_ids(hass)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": ids["parameter_washWaterTemperature"], "option": "40℃"},
        blocking=True,
    )
    result = await hass.services.async_call(
        "minij",
        "start_program",
        {
            "entity_id": entity,
            "program": "快洗",
            "parameters": {"washWaterTemperature": "不加热"},
        },
        blocking=True,
        return_response=True,
    )
    assert result == {entity: {"status": "accepted", "program": "快洗"}}
    MinijClient.async_start_program.assert_awaited_once_with(
        "washer-test-device",
        "mode-b",
        [
            {
                "userDeviceModeStatsId": "stat-mode-b",
                "code": "washWaterTemperature",
                "value": "0",
            }
        ],
    )
    assert hass.states.get(ids["parameter_washWaterTemperature"]).state == "40℃"
    assert hass.states.get(ids["current_status_alias"]).state == "resting"
    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "minij",
            "start_program",
            {"entity_id": entity, "program": "标准"},
            blocking=True,
        )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "minij",
        "start_program",
        {"entity_id": entity, "program": "标准"},
        blocking=True,
    )
    assert MinijClient.async_start_program.await_count == 2


@pytest.mark.parametrize(
    "override",
    [
        {"entity_id": ["button.a", "button.b"]},
        {"entity_id": "all"},
        {"program": 1},
        {"parameters": {"washWaterTemperature": 0}},
        {"parameters": {"washWaterTemperature": True}},
        {"parameters": []},
        {"device_id": "some-device"},
        {"unexpected": True},
    ],
)
async def test_action_schema_refuses_ambiguous_or_numeric_input(hass, api, override):  # noqa: F811
    _, entity = await prepare_action(hass)
    with pytest.raises(probatio.Invalid):
        await hass.services.async_call(
            "minij",
            "start_program",
            {"entity_id": entity, "program": "标准", **override},
            blocking=True,
        )
    MinijClient.async_start_program.assert_not_awaited()


async def test_action_rejects_other_button_and_unauthorized_user(hass, api):  # noqa: F811
    _, entity = await prepare_action(hass)
    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            "minij",
            "start_program",
            {"entity_id": entity_ids(hass)["wake"], "program": "标准"},
            blocking=True,
        )
    assert error.value.translation_key == "program_target_unavailable"
    permissions = SimpleNamespace(check_entity=Mock(return_value=False))
    hass.auth = SimpleNamespace(
        async_get_user=AsyncMock(
            return_value=SimpleNamespace(is_admin=False, permissions=permissions)
        )
    )
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "minij",
            "start_program",
            {"entity_id": entity, "program": "标准"},
            blocking=True,
            context=Context(user_id="synthetic-denied-user"),
        )
    MinijClient.async_start_program.assert_not_awaited()


@pytest.mark.parametrize(
    "fixture_name, value", [("v6_xnb_standard", "4"), ("u10_pro_daily", "5")]
)
async def test_action_resolves_drying_options_per_model(
    start_button,  # noqa: F811
    fixture_name,
    value,
):
    from test_programs import DRYING_PARAMETERS

    client = start_button.coordinator.client
    client.async_get_program_parameters.return_value = parameters(
        [DRYING_PARAMETERS[fixture_name]]
    )
    await start_button.async_start_with_parameters(
        "标准", {"dryingCompoundOption": "30分钟"}
    )
    assert client.async_start_program.await_args.args[2][0]["value"] == value


async def test_action_unavailable_target_is_an_error_not_silent_success(hass, api):  # noqa: F811
    entry, entity = await prepare_action(hass)
    entry.runtime_data.last_update_success = False
    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            "minij",
            "start_program",
            {"entity_id": entity, "program": "标准"},
            blocking=True,
        )
    assert error.value.translation_key == "program_target_unavailable"
    MinijClient.async_start_program.assert_not_awaited()


async def test_omitted_parameters_use_cloud_values_not_ui_draft(start_button):  # noqa: F811
    controls = start_button.controls
    controls.select_parameter(PARAMETER["code"], "30℃")
    await start_button.async_start_with_parameters("标准", {})
    assert (
        controls.parent.client.async_start_program.await_args.args[2][0]["value"] == "0"
    )
    assert controls.pending_label(PARAMETER["code"]) == "30℃"


async def test_action_targets_exactly_one_of_multiple_washers(hass, api):  # noqa: F811
    from homeassistant.helpers import entity_registry as er
    from test_homeassistant import DEVICE

    other = deepcopy(DEVICE)
    other["deviceId"] = "synthetic-other-washer"
    api[1].return_value.append(other)
    _, first = await prepare_action(hass)
    registry = er.async_get(hass)
    second = next(
        entry.entity_id
        for entry in registry.entities.values()
        if entry.unique_id == "synthetic-other-washer_start_program"
    )
    for entity, device in [
        (first, "washer-test-device"),
        (second, "synthetic-other-washer"),
    ]:
        MinijClient.async_start_program.reset_mock()
        await hass.services.async_call(
            "minij",
            "start_program",
            {"entity_id": entity, "program": "标准"},
            blocking=True,
        )
        MinijClient.async_start_program.assert_awaited_once()
        assert MinijClient.async_start_program.await_args.args[0] == device
