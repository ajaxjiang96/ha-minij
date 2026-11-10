"""Synthetic device-provided program choices and command context regressions."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from test_homeassistant import hass  # noqa: F401

from custom_components.minij.api import MinijError, MinijRateLimitError
from custom_components.minij.programs import (
    MinijProgramCoordinator,
    parse_parameters,
    parse_programs,
    program_coordinator,
)
from custom_components.minij.select import (
    MinijParameterSelect,
    MinijProgramSelect,
    MinijRunningParameterSelect,
)

PROGRAM_A = {
    "id": "synthetic-program-a",
    "chineseName": "标准",
    "bid": 1,
    "vid": 15,
    "programNum": 8,
}
PROGRAM_B = {
    "id": "synthetic-program-b",
    "chineseName": "单脱水",
    "bid": 1,
    "vid": 15,
    "programNum": 7,
}
PARAMETER = {
    "id": "synthetic-parameter-a",
    "code": "washWaterTemperature",
    "name": "洗涤温度",
    "type": "choose",
    "value": 0,
    "optionalValueList": [
        {"label": "不加热", "value": 0},
        {"label": "30℃", "value": 2},
    ],
    "userId": "private-canary",
    "deviceId": "private-canary",
}
DRYING_PARAMETERS = json.loads(
    (Path(__file__).parent / "fixtures/drying_parameters.json").read_text()
)


def programs(current=PROGRAM_A):
    return {
        "frequentlyDeviceModeVOList": [deepcopy(PROGRAM_A)],
        "otherDeviceModeVOList": [deepcopy(PROGRAM_B)],
        "currentDeviceMode": deepcopy(current),
    }


def parameters(items=None):
    return {
        "userDeviceModeStatsList": deepcopy([PARAMETER] if items is None else items)
    }


@pytest.fixture
async def controls(hass):  # noqa: F811
    client = SimpleNamespace(
        async_get_programs=AsyncMock(return_value=programs()),
        async_get_program_parameters=AsyncMock(return_value=parameters()),
        async_set_running_parameter=AsyncMock(),
        async_get_running_program=AsyncMock(return_value=PROGRAM_A["id"]),
    )
    parent = SimpleNamespace(
        hass=hass,
        config_entry=None,
        client=client,
        data={
            "synthetic-washer": {
                "deviceModel": "future-model",
                "wifiVersion": "future-firmware",
                "deviceCharacterMap": {
                    "current_status_alias": "resting",
                    "cloud_control_authorization": "close",
                },
            }
        },
        last_update_success=True,
        async_refresh=AsyncMock(),
    )
    result = MinijProgramCoordinator(parent, "synthetic-washer")
    await result.async_refresh()
    return result


def entity_for(controls, parameter=False):
    entity = (
        MinijParameterSelect(
            controls.parent, controls.device_id, controls, PARAMETER["code"]
        )
        if parameter
        else MinijProgramSelect(controls.parent, controls.device_id, controls)
    )
    entity.hass = controls.hass
    entity._active = True
    return entity


def test_program_parser_retains_only_select_contract():
    raw = programs()
    raw["frequentlyDeviceModeVOList"][0]["private"] = "private-canary"
    parsed, current = parse_programs(raw)
    assert current == PROGRAM_A["id"]
    assert [p.name for p in parsed] == ["标准", "单脱水"]
    assert (parsed[0].bid, parsed[0].vid, parsed[0].program_num) == (1, 15, 8)
    assert "private-canary" not in repr(parsed)


@pytest.mark.parametrize("bad", [True, -1, 256, "8", None])
async def test_program_invalid_native_u8_is_rejected(bad):
    raw = programs()
    raw["frequentlyDeviceModeVOList"][0]["programNum"] = bad
    with pytest.raises(MinijError):
        parse_programs(raw)


@pytest.mark.parametrize(
    "mutation", ["duplicate_name", "conflicting_id", "missing_lists"]
)
def test_program_ambiguous_or_missing_choices_are_not_guessed(mutation):
    raw = programs()
    if mutation == "duplicate_name":
        raw["otherDeviceModeVOList"][0]["chineseName"] = "标准"
    elif mutation == "conflicting_id":
        raw["otherDeviceModeVOList"][0]["id"] = PROGRAM_A["id"]
    else:
        raw.pop("otherDeviceModeVOList")
    with pytest.raises(MinijError):
        parse_programs(raw)


def test_parameter_metadata_empty_list_alternative_and_privacy():
    assert parse_parameters(parameters([])) == ()
    raw = deepcopy(PARAMETER)
    raw.update(
        type="alternative",
        optionalValueList=[
            {"label": "关闭", "value": 0},
            {"label": "打开", "value": 1},
        ],
    )
    result = parse_parameters(parameters([raw]))
    assert result[0].options == (("关闭", 0), ("打开", 1))
    assert "private-canary" not in repr(result)


@pytest.mark.parametrize(
    "options",
    [
        None,
        [{"label": "不加热", "value": True}],
        [{"label": "不加热", "value": "0"}],
        [{"label": "same", "value": 0}, {"label": "same", "value": 1}],
    ],
)
def test_parameter_malformed_options_are_rejected(options):
    raw = deepcopy(PARAMETER)
    raw["optionalValueList"] = options
    with pytest.raises(MinijError):
        parse_parameters(parameters([raw]))


async def test_program_command_and_parameter_ranges_follow_refreshed_program(controls):
    entity = entity_for(controls)
    parameter = entity_for(controls, True)
    assert entity.unique_id == "synthetic-washer_program"
    assert parameter.unique_id == "synthetic-washer_parameter_washWaterTemperature"
    assert entity.options == ["标准", "单脱水"]
    assert parameter.current_option == "不加热"

    controls.parent.client.async_get_program_parameters.return_value = parameters([])
    await entity.async_select_option("单脱水")
    assert entity.current_option == "单脱水"
    assert parameter.options == []
    assert parameter.current_option is None
    assert not parameter.available
    controls.parent.client.async_set_running_parameter.assert_not_awaited()
    controls.parent.client.async_get_program_parameters.assert_awaited_with(
        "synthetic-washer", PROGRAM_B["id"]
    )
    await controls.async_refresh()
    assert entity.current_option == "单脱水"
    snapshot = controls.diagnostics_snapshot()
    assert snapshot["selection_source"] == "local_draft"
    assert snapshot["cloud_catalog_current"] == "标准"


async def test_parameter_uses_current_metadata_value_and_id_without_operating_gates(
    controls,
):
    entity = await running_entity(controls)

    async def write(device_id, parameter_id, code, value):
        assert (device_id, parameter_id, code, value) == (
            "synthetic-washer",
            PARAMETER["id"],
            PARAMETER["code"],
            2,
        )
        controls.parent.client.async_get_program_parameters.return_value[
            "userDeviceModeStatsList"
        ][0]["value"] = 2

    controls.parent.client.async_set_running_parameter.side_effect = write
    await entity.async_select_option("30℃")
    assert entity.current_option == "30℃"
    controls.parent.client.async_set_running_parameter.assert_awaited_once()
    await entity.async_select_option("30℃")
    assert controls.parent.client.async_set_running_parameter.await_count == 1


@pytest.mark.parametrize("context", ["pending", "running"])
@pytest.mark.parametrize(
    ("fixture_name", "label", "expected_value"),
    [
        ("v6_xnb_standard", "30分钟", 4),
        ("u10_pro_daily", "30分钟", 5),
        ("u10_pro_daily", "特干", 3),
        ("u10_pro_daily", "无烘干", 0),
    ],
)
async def test_drying_select_uses_device_options_including_zero(
    controls, fixture_name, label, expected_value, context
):
    """Community metadata validates mapping, not U10 Pro hardware support."""
    raw = deepcopy(DRYING_PARAMETERS[fixture_name])
    if expected_value == 0:
        raw["value"] = 2
    client = controls.parent.client
    client.async_get_program_parameters.return_value = parameters([raw])
    if context == "running":
        controls.parent.data[controls.device_id]["deviceCharacterMap"][
            "current_status_alias"
        ] = "working"
    await controls.async_refresh()
    entity_type = (
        MinijRunningParameterSelect if context == "running" else MinijParameterSelect
    )
    entity = entity_type(
        controls.parent, controls.device_id, controls, "dryingCompoundOption"
    )
    entity.hass = controls.hass
    entity._active = True

    async def write(device_id, parameter_id, code, value):
        client.async_get_program_parameters.return_value["userDeviceModeStatsList"][0][
            "value"
        ] = value

    client.async_set_running_parameter.side_effect = write
    await entity.async_select_option(label)
    if context == "running":
        client.async_set_running_parameter.assert_awaited_once_with(
            controls.device_id, raw["id"], "dryingCompoundOption", expected_value
        )
    else:
        client.async_set_running_parameter.assert_not_awaited()
        assert controls.start_parameters() == [
            {
                "userDeviceModeStatsId": raw["id"],
                "code": "dryingCompoundOption",
                "value": str(expected_value),
            }
        ]
    assert entity.current_option == label


async def test_drying_mapping_uses_fresh_options_and_parameter_identity(controls):
    """An existing select must not reuse another metadata snapshot's enum."""
    client = controls.parent.client
    client.async_get_program_parameters.return_value = parameters(
        [DRYING_PARAMETERS["v6_xnb_standard"]]
    )
    await controls.async_refresh()
    entity = MinijParameterSelect(
        controls.parent, controls.device_id, controls, "dryingCompoundOption"
    )
    entity.hass = controls.hass
    entity._active = True
    assert "特干" not in entity.options

    # Replace metadata before the command's own fresh read, without recreating UI.
    raw = DRYING_PARAMETERS["u10_pro_daily"]
    client.async_get_program_parameters.return_value = parameters([raw])

    async def write(device_id, parameter_id, code, value):
        client.async_get_program_parameters.return_value["userDeviceModeStatsList"][0][
            "value"
        ] = value

    client.async_set_running_parameter.side_effect = write
    await entity.async_select_option("30分钟")
    client.async_set_running_parameter.assert_not_awaited()
    assert controls.start_parameters()[0]["value"] == "5"
    assert controls.start_parameters()[0]["userDeviceModeStatsId"] == raw["id"]
    assert "特干" in entity.options
    assert entity.current_option == "30分钟"


async def test_changed_program_cannot_receive_cached_parameter_id(controls):
    entity = entity_for(controls, True)
    controls.parent.client.async_get_programs.return_value = programs(PROGRAM_B)
    new = deepcopy(PARAMETER)
    new["id"] = "synthetic-parameter-b"
    controls.parent.client.async_get_program_parameters.return_value = parameters([new])
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_select_option("30℃")
    assert err.value.translation_key == "program_changed"
    controls.parent.client.async_set_running_parameter.assert_not_awaited()


async def test_parameter_options_revalidated_before_any_write(controls):
    entity = entity_for(controls, True)
    controls.parent.client.async_get_program_parameters.return_value[
        "userDeviceModeStatsList"
    ][0]["optionalValueList"] = [{"label": "不加热", "value": 0}]
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_select_option("30℃")
    assert err.value.translation_key == "program_option_unavailable"
    controls.parent.client.async_set_running_parameter.assert_not_awaited()


async def test_program_failure_does_not_hide_parent_and_diagnostics_are_cache_only(
    controls,
):
    entity = entity_for(controls)
    controls.parent.client.async_get_programs.side_effect = MinijRateLimitError(
        "private-canary", 300
    )
    await controls.async_refresh()
    assert not entity.available
    assert entity.options == []
    assert controls.parent.last_update_success
    before = controls.parent.client.async_get_programs.await_count
    summary = controls.diagnostics_snapshot()
    assert summary["program_count"] == 2
    assert "private-canary" not in repr(summary)
    assert "synthetic-program-a" not in repr(summary)
    assert "synthetic-parameter-a" not in repr(summary)
    assert controls.parent.client.async_get_programs.await_count == before


async def test_no_optimistic_parameter_change_and_no_write_retry(controls):
    entity = await running_entity(controls)
    with patch(
        "custom_components.minij.programs.sleep", new_callable=AsyncMock
    ) as pause:
        with pytest.raises(HomeAssistantError) as err:
            await entity.async_select_option("30℃")
    assert err.value.translation_key == "control_not_confirmed"
    assert entity.current_option == "不加热"
    assert pause.await_count == 2
    controls.parent.client.async_set_running_parameter.assert_awaited_once()


async def test_unload_during_refresh_prevents_parameter_write(controls):
    entity = entity_for(controls, True)

    async def unloaded(*args):
        entity._active = False
        return parameters()

    controls.parent.client.async_get_program_parameters.side_effect = unloaded
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_select_option("30℃")
    assert err.value.translation_key == "control_read_failed"
    controls.parent.client.async_set_running_parameter.assert_not_awaited()


def test_numeric_parameter_identifier_is_normalized_for_native_string_payload():
    raw = deepcopy(PARAMETER)
    raw["id"] = 42
    parsed = parse_parameters(parameters([raw]))
    assert parsed[0].id == "42"


async def test_failed_draft_parameter_read_preserves_complete_snapshot(controls):
    original = controls.data
    controls.parent.client.async_get_program_parameters.side_effect = MinijError(
        "failed"
    )
    with pytest.raises(MinijError):
        await controls.async_select_draft(PROGRAM_B["id"])
    assert controls.data is original
    assert controls.data.selection_source == "cloud_catalog"
    controls.parent.client.async_set_running_parameter.assert_not_awaited()


@pytest.mark.parametrize("fail_stale_read", [False, True])
async def test_background_read_cannot_replace_new_draft(controls, fail_stale_read):
    entered, release = asyncio.Event(), asyncio.Event()

    async def read(device_id, program_id):
        if program_id == PROGRAM_A["id"]:
            entered.set()
            await release.wait()
            if fail_stale_read:
                raise MinijError("stale failure")
            return parameters()
        return parameters([])

    controls.parent.client.async_get_program_parameters.side_effect = read
    background = asyncio.create_task(controls.async_refresh())
    await entered.wait()
    await controls.async_select_draft(PROGRAM_B["id"])
    release.set()
    await background
    assert controls.data.current_id == PROGRAM_B["id"]
    assert controls.data.parameters == ()
    assert controls.data.selection_source == "local_draft"
    assert controls.last_update_success


async def test_draft_parameter_write_keeps_selected_program_despite_catalog_current(
    controls,
):
    await controls.async_select_draft(PROGRAM_B["id"])
    entity = entity_for(controls, True)

    async def write(*args):
        controls.parent.client.async_get_program_parameters.return_value[
            "userDeviceModeStatsList"
        ][0]["value"] = 2

    controls.parent.client.async_set_running_parameter.side_effect = write
    await entity.async_select_option("30℃")
    assert controls.data.current_id == PROGRAM_B["id"]
    assert entity.current_option == "30℃"
    assert all(
        call.args[1] == PROGRAM_B["id"]
        for call in controls.parent.client.async_get_program_parameters.await_args_list[
            1:
        ]
    )


async def test_removed_draft_falls_back_to_catalog_with_matching_parameters(controls):
    await controls.async_select_draft(PROGRAM_B["id"])
    catalog = programs()
    catalog["otherDeviceModeVOList"] = []
    controls.parent.client.async_get_programs.return_value = catalog
    await controls.async_refresh()
    assert controls.data.current_id == PROGRAM_A["id"]
    assert controls.data.selection_source == "cloud_catalog"
    controls.parent.client.async_get_program_parameters.assert_awaited_with(
        "synthetic-washer", PROGRAM_A["id"]
    )


async def test_parameter_queued_behind_program_switch_keeps_origin(controls):
    entity = entity_for(controls, True)
    async with controls.command_lock:
        queued = asyncio.create_task(entity.async_select_option("30℃"))
        await asyncio.sleep(0)
        await controls.async_select_draft(PROGRAM_B["id"])
    with pytest.raises(HomeAssistantError) as err:
        await queued
    assert err.value.translation_key == "program_changed"
    controls.parent.client.async_set_running_parameter.assert_not_awaited()


async def test_parameter_unloaded_during_confirmation_does_not_confirm(controls):
    entity = await running_entity(controls)
    client = controls.parent.client

    async def command(*args):
        async def unloaded(*args):
            entity._active = False
            changed = deepcopy(PARAMETER)
            changed["value"] = 2
            return parameters([changed])

        client.async_get_program_parameters.side_effect = unloaded

    client.async_set_running_parameter.side_effect = command
    with pytest.raises(HomeAssistantError) as err:
        await entity.async_select_option("30℃")
    assert err.value.translation_key == "control_not_confirmed"
    client.async_set_running_parameter.assert_awaited_once()


async def test_program_coordinator_reuses_existing_cache_across_platforms(controls):
    controls.parent.program_controls = {controls.device_id: controls}
    assert program_coordinator(controls.parent, controls.device_id) is controls
    assert program_coordinator(controls.parent, controls.device_id) is controls
    assert controls.parent.program_controls == {controls.device_id: controls}


async def running_entity(controls):
    controls.parent.data[controls.device_id]["deviceCharacterMap"][
        "current_status_alias"
    ] = "working"
    await controls.async_refresh()
    entity = MinijRunningParameterSelect(
        controls.parent, controls.device_id, controls, PARAMETER["code"]
    )
    entity.hass = controls.hass
    entity._active = True
    return entity


async def test_explicit_zero_draft_survives_refresh_and_uses_latest_identity(controls):
    entity = entity_for(controls, True)
    await entity.async_select_option("不加热")
    raw = deepcopy(PARAMETER)
    raw.update(id="synthetic-new-id", value=2)
    controls.parent.client.async_get_program_parameters.return_value = parameters([raw])
    await controls.async_refresh()
    assert entity.current_option == "不加热"
    assert controls.start_parameters() == [
        {"userDeviceModeStatsId": raw["id"], "code": raw["code"], "value": "0"}
    ]
    controls.parent.client.async_set_running_parameter.assert_not_awaited()
    await controls.async_select_draft(PROGRAM_B["id"])
    assert controls.data.draft_choices == ()
    assert entity.current_option == "30℃"


async def test_removed_explicit_option_blocks_start_instead_of_silently_dropping(
    controls,
):
    entity = entity_for(controls, True)
    await entity.async_select_option("30℃")
    controls.parent.client.async_get_program_parameters.return_value = parameters([])
    await controls.async_refresh()
    with pytest.raises(HomeAssistantError) as error:
        controls.start_parameters()
    assert error.value.translation_key == "program_parameters_changed"


async def test_running_parameter_is_independent_of_pending_program(controls):
    entity = await running_entity(controls)
    await controls.async_select_draft(PROGRAM_B["id"])

    async def read(device_id, program_id):
        raw = deepcopy(PARAMETER)
        raw["id"] = "running-id" if program_id == PROGRAM_A["id"] else "pending-id"
        raw["value"] = (
            2 if controls.parent.client.async_set_running_parameter.await_count else 0
        )
        return parameters([raw])

    controls.parent.client.async_get_program_parameters.side_effect = read
    await entity.async_select_option("30℃")
    controls.parent.client.async_set_running_parameter.assert_awaited_once_with(
        controls.device_id, "running-id", PARAMETER["code"], 2
    )
    assert controls.data.current_id == PROGRAM_B["id"]
    assert controls.data.running_id == PROGRAM_A["id"]
    controls.parent.data[controls.device_id]["deviceCharacterMap"][
        "current_status_alias"
    ] = "resting"
    await controls.async_refresh()
    assert not entity.available


async def test_device_removed_during_parameter_read_fails_cleanly(controls):
    async def removed(*args):
        controls.parent.data.clear()
        return parameters()

    controls.parent.client.async_get_program_parameters.side_effect = removed
    await controls.async_refresh()
    assert not controls.last_update_success
