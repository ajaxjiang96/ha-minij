export function fixture(status = "working") {
  const entries = [],
    states = {},
    entities = {};
  function add(domain, key, state, attributes = {}) {
    const entity_id = `${domain}.test_${key.toLowerCase()}`;
    entries.push({
      entity_id,
      unique_id: `cloud-test_${key}`,
      platform: "minij",
      device_id: "ha-device-test",
      original_name: key,
      disabled_by: null,
    });
    states[entity_id] = {
      entity_id,
      state,
      attributes: { friendly_name: key, ...attributes },
    };
    entities[entity_id] = {
      entity_id,
      platform: "minij",
      device_id: "ha-device-test",
    };
    return entity_id;
  }
  const entity = add("sensor", "current_status_alias", status, {
    device_class: "enum",
  });
  add("sensor", "current_mode", "婴童");
  add("sensor", "current_process", "主洗");
  add("sensor", "program_remain_time", "57", { unit_of_measurement: "min" });
  add("select", "program", "婴童", { options: ["婴童", "标准", "单烘干"] });
  for (const key of [
    "wake",
    "start_program",
    "pause",
    "resume",
    "power_off",
    "start_cleaning",
  ])
    add("button", key, "unknown");
  add("switch", "prompt_tone", "on");
  add("switch", "child_lock_control", "off");
  for (const [code, name, value, options] of [
    ["washWaterTemperature", "温度", "40℃", ["不加热", "30℃", "40℃", "60℃"]],
    ["bleachWashTimes", "漂洗次数", "3次", ["1次", "2次", "3次"]],
    ["dryingCompoundOption", "烘干", "无烘干", ["无烘干", "30分钟"]],
    ["washWaterLevel", "洗涤水位", "低水位", ["低水位", "高水位"]],
    ["dryingStrength", "烘干强度", "无烘干", ["无烘干", "强", "弱"]],
    ["steamSterilization", "蒸汽除菌", "打开", ["关闭", "打开"]],
    ["UVCDownlights", "UVC筒灯", "打开", ["关闭", "打开"]],
  ]) {
    const id = add("select", `parameter_${code}`, value, { options });
    entries.at(-1).original_name = name;
    states[id].attributes.friendly_name = name;
  }
  const calls = [];
  const connection = { subscribeEvents: async () => () => {} };
  const hass = {
    states,
    entities,
    connection,
    locale: { language: "zh-Hans" },
    devices: {
      "ha-device-test": { name: "壁挂洗烘一体机", area_id: "laundry" },
    },
    areas: { laundry: { name: "洗衣房" } },
    callWS: async () => entries,
    callService: async (...args) => {
      calls.push(args);
    },
  };
  return { entries, hass, entity, calls };
}
