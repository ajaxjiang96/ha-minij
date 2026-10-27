import { test } from "node:test";
import assert from "node:assert/strict";
import { Window } from "happy-dom";
import { discover, remainingTime, primaryAction } from "../src/model.js";
import { fixture } from "./fixtures.js";
const window = new Window();
for (const key of [
  "window",
  "document",
  "customElements",
  "HTMLElement",
  "Document",
  "ShadowRoot",
  "CSSStyleSheet",
  "Event",
  "CustomEvent",
])
  globalThis[key] = key === "window" ? window : window[key];
await import("../src/minij-card.js");
async function mount(data = fixture(), config = {}) {
  const card = document.createElement("minij-card");
  card.setConfig({ entity: data.entity, ...config });
  card.hass = data.hass;
  document.body.append(card);
  await card.updateComplete;
  await new Promise((r) => setTimeout(r, 0));
  await card.updateComplete;
  return { card, ...data };
}
async function flush(card) {
  await card.updateComplete;
  await new Promise((r) => setTimeout(r, 0));
  await card.updateComplete;
}
function button(card, label) {
  return [...card.shadowRoot.querySelectorAll("button")].find(
    (b) =>
      b.textContent.trim() === label || b.getAttribute("aria-label") === label,
  );
}

test("registry discovery uses exact keys, respects device/platform/disabled and renamed entity IDs", () => {
  const data = fixture();
  data.entries.reverse();
  data.entries.push({
    entity_id: "button.other",
    unique_id: "cloud-test_pause",
    platform: "other",
    device_id: "ha-device-test",
  });
  data.entries.push({
    entity_id: "select.other",
    unique_id: "other_program",
    platform: "minij",
    device_id: "other-device",
  });
  data.entries.find((e) =>
    e.unique_id.endsWith("_parameter_UVCDownlights"),
  ).disabled_by = "user";
  const map = discover(data.entries, data.entity);
  assert.equal(map.roles.program, "select.test_program");
  assert.equal(map.roles.start, "button.test_start_program");
  assert.equal(map.roles.pause, "button.test_pause");
  assert.equal(map.parameters.length, 6);
  assert.throws(() => discover(data.entries, "sensor.not_minij"));
});
test("remaining time is reported minutes only, no idle/pause guess or bogus unit", () => {
  const s = { state: "57", attributes: { unit_of_measurement: "min" } };
  assert.equal(remainingTime("working", s), "00:57");
  assert.equal(remainingTime("working", { ...s, state: "65" }), "01:05");
  for (const state of ["paused", "resting", "unavailable"])
    assert.equal(remainingTime(state, s), null);
  for (const state of ["-1", "1.5", "unknown", "Infinity", "9007199254740992"])
    assert.equal(remainingTime("working", { ...s, state }), null);
  assert.equal(
    remainingTime("working", {
      ...s,
      attributes: { unit_of_measurement: "s" },
    }),
    null,
  );
  assert.equal(primaryAction("unknown"), null);
});
test("fresh buttons with unknown timestamp still pause, ACK does not change machine state", async () => {
  const { card, hass, calls } = await mount();
  const pause = button(card, "暂停");
  assert.equal(pause.disabled, false);
  pause.click();
  await flush(card);
  assert.deepEqual(calls, [
    ["button", "press", { entity_id: "button.test_pause" }],
  ]);
  assert.equal(
    hass.states["sensor.test_current_status_alias"].state,
    "working",
  );
  assert.match(card.shadowRoot.textContent, /请求已接受/);
  hass.states = {
    ...hass.states,
    "sensor.test_current_status_alias": {
      ...hass.states["sensor.test_current_status_alias"],
      state: "paused",
    },
  };
  card.hass = { ...hass };
  await flush(card);
  assert.match(card.shadowRoot.textContent, /设备已上报目标状态/);
  assert.ok(button(card, "继续"));
  assert.equal(card.shadowRoot.querySelector(".time").textContent, "—");
  card.remove();
});
test("service failure sends once, no optimistic switch or retry", async () => {
  const data = fixture();
  data.hass.callService = async (...args) => {
    data.calls.push(args);
    throw new Error("synthetic");
  };
  const { card, calls } = await mount(data);
  await card._request("tone");
  await flush(card);
  assert.equal(calls.length, 1);
  assert.equal(card._state("tone").state, "on");
  assert.match(card.shadowRoot.textContent, /结果不确定/);
  card.remove();
});
test("stop confirmation cancels, start rejects program change while dialog open", async () => {
  const { card, hass, calls } = await mount(fixture("waiting"));
  const stop = card._request("stop");
  await flush(card);
  card._finishConfirmation(false);
  await stop;
  assert.equal(calls.length, 0);
  const start = card._request("start");
  await flush(card);
  hass.states["select.test_program"] = {
    ...hass.states["select.test_program"],
    state: "标准",
  };
  card._finishConfirmation(true);
  await start;
  assert.equal(calls.length, 0);
  assert.match(card._feedback, /changed/);
  const confirmed = card._request("stop");
  await flush(card);
  card._finishConfirmation(true);
  await confirmed;
  assert.deepEqual(calls, [
    ["button", "press", { entity_id: "button.test_power_off" }],
  ]);
  card.remove();
});
test("preview never writes; selectors use current metadata and stale options are refused", async () => {
  const { card, hass, calls } = await mount();
  card.preview = true;
  await flush(card);
  await card._request("pause");
  await card._send("select.test_program", "标准");
  assert.equal(calls.length, 0);
  card.preview = false;
  await card._send("select.test_program", "not-an-option");
  assert.equal(calls.length, 0);
  await card._send("select.test_program", "标准");
  assert.equal(calls.length, 1);
  hass.states = {
    ...hass.states,
    "select.test_parameter_washwatertemperature": {
      ...hass.states["select.test_parameter_washwatertemperature"],
      state: "60℃",
      attributes: { options: ["60℃"] },
    },
  };
  card.hass = { ...hass };
  await flush(card);
  const select = card.shadowRoot.querySelector('select[aria-label="温度"]');
  assert.deepEqual(
    [...select.options].map((o) => o.value),
    ["60℃"],
  );
  assert.equal(select.value, "60℃");
  card.remove();
});
test("registry errors fail closed and disconnected confirmation cannot write", async () => {
  const data = fixture();
  data.hass.callWS = async () => {
    throw new Error("synthetic");
  };
  const { card } = await mount(data);
  assert.match(card.shadowRoot.textContent, /无法读取实体注册表/);
  await card._request("wake");
  assert.equal(data.calls.length, 0);
  card.remove();
  const second = await mount();
  const command = second.card._request("stop");
  await flush(second.card);
  second.card.remove();
  await command;
  assert.equal(second.calls.length, 0);
});
test("visual editor scopes choices to MiniJ and emits config without altering entities", async () => {
  const data = fixture();
  const editor = document.createElement("minij-card-editor");
  editor.hass = data.hass;
  editor.setConfig({ type: "custom:minij-card", entity: data.entity });
  document.body.append(editor);
  await editor.updateComplete;
  let config;
  editor.addEventListener("config-changed", (e) => (config = e.detail.config));
  const name = editor.shadowRoot.querySelector("input[type=text]");
  name.value = "我的洗衣机";
  name.dispatchEvent(new Event("change"));
  await editor.updateComplete;
  assert.equal(config.name, "我的洗衣机");
  assert.equal(config.entity, data.entity);
  assert.equal(editor.shadowRoot.querySelectorAll("option").length, 2);
  editor.hass = { ...data.hass, locale: { language: "en" } };
  await editor.updateComplete;
  assert.match(editor.shadowRoot.textContent, /Washer status entity/);
  editor.remove();
});

test("option replacement keeps the reported value when two new choices arrive", async () => {
  const { card, hass } = await mount();
  const id = "select.test_parameter_dryingcompoundoption";
  hass.states = {
    ...hass.states,
    [id]: {
      ...hass.states[id],
      state: "30分钟",
      attributes: { options: ["30分钟", "60分钟"] },
    },
  };
  card.hass = { ...hass };
  await flush(card);
  const select = card.shadowRoot.querySelector('select[aria-label="烘干"]');
  assert.equal(select.value, "30分钟");
  card.remove();
});

test("registry loads once per connection and repeated dialog requests cannot double send", async () => {
  const data = fixture();
  let reads = 0;
  data.hass.callWS = async () => {
    reads++;
    return data.entries;
  };
  const { card } = await mount(data);
  card.hass = { ...data.hass };
  await flush(card);
  assert.equal(reads, 1);
  const first = card._request("stop");
  const second = card._request("stop");
  await flush(card);
  card._finishConfirmation(true);
  await Promise.all([first, second]);
  assert.equal(data.calls.length, 1);
  card.remove();
});

test("local draft feedback never claims an appliance report", async () => {
  const { card, calls } = await mount();
  await card._send("select.test_program", "标准");
  await flush(card);
  assert.equal(calls.length, 1);
  assert.equal(card._feedback, "draft");
  assert.equal(card._observation, null);
  assert.match(card.shadowRoot.textContent, /本地草稿/);
  card.remove();
});

test("a state change while start confirmation is open invalidates that confirmation", async () => {
  const { card, hass, calls } = await mount(fixture("waiting"));
  const command = card._request("start");
  await flush(card);
  hass.states = {
    ...hass.states,
    "sensor.test_current_status_alias": {
      ...hass.states["sensor.test_current_status_alias"],
      state: "working",
    },
  };
  card.hass = { ...hass };
  await flush(card);
  card._finishConfirmation(true);
  await command;
  assert.equal(calls.length, 0);
  assert.equal(card._feedback, "changed");
  card.remove();
});

test("unknown select values remain writable when current options are valid", async () => {
  const data = fixture("waiting");
  data.hass.states["select.test_program"].state = "unknown";
  data.hass.states["select.test_parameter_washwatertemperature"].state =
    "unknown";
  const { card, calls } = await mount(data);
  const program = card.shadowRoot.querySelector(
    'select[aria-label="待启动程序"]',
  );
  const temperature = card.shadowRoot.querySelector(
    'select[aria-label="温度"]',
  );
  assert.equal(program.disabled, false);
  assert.equal(temperature.disabled, false);
  await card._send("select.test_program", "标准");
  await card._send("select.test_parameter_washwatertemperature", "40℃");
  assert.equal(calls.length, 2);
  await card._send("select.test_program", "not-an-option");
  assert.equal(calls.length, 2);
  data.hass.states["select.test_program"].state = "unavailable";
  await card._send("select.test_program", "标准");
  assert.equal(calls.length, 2);
  card.remove();
});
