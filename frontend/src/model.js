// Entity identity comes from MiniJ's registry keys, never user-visible names.
const ROLES = {
  current_status_alias: "status",
  current_mode: "reportedProgram",
  current_process: "process",
  program_remain_time: "remaining",
  program: "program",
  wake: "wake",
  start_program: "start",
  pause: "pause",
  resume: "resume",
  power_off: "stop",
  prompt_tone: "tone",
  child_lock_control: "lock",
  start_cleaning: "clean",
  cleaning_reminder: "reminder",
  cleaning_threshold: "threshold",
  cleaning_trusteeship: "trusteeship",
};
export function discover(entries, entity) {
  const source = entries.find(
    (e) => e.entity_id === entity && e.platform === "minij",
  );
  if (
    !source?.device_id ||
    source.disabled_by ||
    !source.unique_id.endsWith("_current_status_alias") ||
    !entity.startsWith("sensor.")
  ) {
    throw new Error("invalid_device");
  }
  const prefix =
    source.unique_id.slice(0, -"_current_status_alias".length) + "_";
  const roles = {},
    parameters = [];
  for (const entry of entries) {
    if (
      entry.device_id !== source.device_id ||
      entry.platform !== "minij" ||
      entry.disabled_by
    )
      continue;
    if (!entry.unique_id.startsWith(prefix)) continue;
    const key = entry.unique_id.slice(prefix.length);
    if (ROLES[key]) roles[ROLES[key]] = entry.entity_id;
    if (
      /^parameter_[a-zA-Z0-9]+$/.test(key) &&
      entry.entity_id.startsWith("select.")
    )
      parameters.push(entry);
  }
  return { roles, parameters, deviceId: source.device_id };
}
export function available(state) {
  return !!state && !["unknown", "unavailable"].includes(state.state);
}
export function selectable(state) {
  return (
    !!state &&
    state.state !== "unavailable" &&
    Array.isArray(state.attributes.options) &&
    state.attributes.options.length > 0
  );
}
export function remainingTime(status, state) {
  if (
    status !== "working" ||
    !available(state) ||
    state.attributes.unit_of_measurement !== "min" ||
    !/^\d+$/.test(state.state)
  )
    return null;
  const minutes = Number(state.state);
  if (!Number.isSafeInteger(minutes)) return null;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}
export function primaryAction(status) {
  return (
    { resting: "wake", waiting: "start", working: "pause", paused: "resume" }[
      status
    ] ?? null
  );
}
export function statusLabel(hass, state, chinese) {
  if (!state) return chinese ? "找不到状态实体" : "Status entity not found";
  if (hass.formatEntityState) return hass.formatEntityState(state);
  return ({
    resting: ["待机", "Standby"],
    waiting: ["已唤醒", "Ready"],
    working: ["工作中", "Working"],
    paused: ["已暂停", "Paused"],
    unavailable: ["不可用", "Unavailable"],
    unknown: ["未知", "Unknown"],
    device_exception: ["设备上报异常", "Reported exception"],
  }[state.state] ?? [state.state, state.state])[chinese ? 0 : 1];
}
export const isChinese = (hass) =>
  (hass?.locale?.language ?? hass?.language ?? "en").startsWith("zh");
