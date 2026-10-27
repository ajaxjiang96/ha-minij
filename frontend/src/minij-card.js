import { LitElement, html, nothing } from "lit";
import { live } from "lit/directives/live.js";
import {
  discover,
  available,
  remainingTime,
  primaryAction,
  statusLabel,
  isChinese,
} from "./model.js";
import { appliance, icon, styles } from "./visual.js";

const TEXT = {
  configure: [
    "请在卡片编辑器选择小吉状态实体。",
    "Choose a MiniJ status entity in the card editor.",
  ],
  invalid_device: [
    "请选择 MiniJ 的状态实体。",
    "Select a MiniJ status entity.",
  ],
  registry: [
    "无法读取实体注册表，请重新加载卡片。",
    "Unable to load entity registry. Reload the card.",
  ],
  loading: ["正在读取洗衣机实体…", "Loading washer entities…"],
  name: ["小吉洗衣机", "MiniJ washer"],
  remaining: ["云端剩余时间", "Cloud remaining time"],
  pending: ["待启动程序", "Pending program"],
  parameters: ["程序与参数", "Program & parameters"],
  settings: ["设备设置", "Device settings"],
  unknown: ["未知", "Unknown"],
  wake: ["唤醒", "Wake"],
  start: ["启动", "Start"],
  pause: ["暂停", "Pause"],
  resume: ["继续", "Resume"],
  stop: ["停止／关机", "Stop / power off"],
  clean: ["筒清洁", "Drum cleaning"],
  tone: ["提示音", "Prompt tone"],
  lock: ["童锁（实验）", "Child lock (experimental)"],
  reminder: ["清洁提醒", "Cleaning reminder"],
  threshold: ["提醒运行次数", "Reminder interval"],
  trusteeship: ["自动筒清洁", "Automatic drum cleaning"],
  cancel: ["取消", "Cancel"],
  confirm: ["确认", "Confirm"],
  sending: ["正在发送…", "Sending…"],
  draft: [
    "待启动程序已选定（本地草稿），尚未启动。",
    "Pending program selected as a local draft. The washer has not been started.",
  ],
  rinse: ["漂洗", "Rinse"],
  accepted: [
    "请求已接受，等待设备回报。",
    "Request accepted. Waiting for device report.",
  ],
  reported: ["设备已上报目标状态。", "Device reported the target state."],
  failed: [
    "请求失败或结果不确定，请查看机器及 App；未自动重试。",
    "Request failed or its result is uncertain. Check the appliance and App; no automatic retry.",
  ],
  changed: [
    "设备或程序已变化，请重新确认。",
    "Device or program changed. Review it again.",
  ],
  preview: ["编辑预览：控制已停用", "Editor preview: controls disabled"],
  hint: [
    "程序选择是本地草稿；参数修改会立即提交云端。状态通常每 60 秒更新，请勿因延迟重复点击。",
    "Program selection is a local draft; parameter changes are sent immediately. Cloud status normally refreshes every 60 seconds. Avoid repeated taps while waiting.",
  ],
  idle: [
    "待机时程序与阶段可能保留上次值。",
    "Program and stage may retain the previous report while idle.",
  ],
  confirm_start: [
    "启动所选程序？请先核对参数并确认机器已准备好。",
    "Start the selected program? Check its parameters and prepare the appliance first.",
  ],
  confirm_stop: [
    "停止当前程序并关机？此操作可能中断洗涤。",
    "Stop the current program and power off? This may interrupt the wash.",
  ],
  confirm_clean: [
    "启动筒清洁？请先确认空筒并按机器要求准备。",
    "Start drum cleaning? Empty the drum and prepare it as instructed by the appliance.",
  ],
  entity: ["洗衣机状态实体", "Washer status entity"],
  title: ["卡片名称（可选）", "Card name (optional)"],
  subtitle: ["副标题／区域（可选）", "Subtitle / area (optional)"],
  animation: ["滚筒动画", "Drum animation"],
  show_remaining: ["显示剩余时间", "Show remaining time"],
  show_settings: ["显示设备设置", "Show device settings"],
};

export class MinijCard extends LitElement {
  static styles = styles;
  static properties = {
    hass: { attribute: false },
    preview: { type: Boolean },
    _config: { state: true },
    _map: { state: true },
    _error: { state: true },
    _busy: { state: true },
    _feedback: { state: true },
    _dialog: { state: true },
  };
  constructor() {
    super();
    this._epoch = 0;
    this._feedback = "";
    this._busy = false;
    this._registry = [];
  }
  t(key) {
    return TEXT[key]?.[isChinese(this.hass) ? 0 : 1] ?? key;
  }
  setConfig(config) {
    if (
      config.entity &&
      (typeof config.entity !== "string" ||
        !config.entity.startsWith("sensor."))
    )
      throw new Error("MiniJ card requires a sensor entity");
    if (config.name != null && typeof config.name !== "string")
      throw new Error("name must be a string");
    if (config.subtitle != null && typeof config.subtitle !== "string")
      throw new Error("subtitle must be a string");
    for (const key of ["animation", "show_remaining", "show_settings"]) {
      if (config[key] != null && typeof config[key] !== "boolean")
        throw new Error(`${key} must be a boolean`);
    }
    this._config = {
      animation: true,
      show_remaining: true,
      show_settings: true,
      ...config,
    };
    this._epoch++;
    this._busy = false;
    this._feedback = "";
    this._observation = null;
    this._resolveConfirmation?.(false);
    this._resolveConfirmation = null;
    this._dialog = null;
    this._map = null;
    this._error = null;
    if (this.hass) this._resolveMap();
  }
  connectedCallback() {
    super.connectedCallback();
    this._ensureRegistry();
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._epoch++;
    this._unsubscribe?.();
    this._unsubscribe = null;
    this._connection = null;
    this._loading = false;
    this._busy = false;
    this._resolveConfirmation?.(false);
    this._resolveConfirmation = null;
    this._dialog = null;
  }
  willUpdate(changed) {
    if (changed.has("hass")) {
      this._ensureRegistry();
      const watch = this._observation;
      const state = watch && this.hass?.states[watch.entity];
      if (state && state !== watch.before && state.state === watch.expected) {
        this._feedback = "reported";
        this._observation = null;
      }
    }
  }
  updated() {
    // Set native selection after Lit commits new option children. Setting value
    // before replacement options can make the browser pick a different option.
    for (const select of this.renderRoot.querySelectorAll(
      "select[data-entity]",
    )) {
      const state = this.hass?.states[select.dataset.entity];
      const value = state?.attributes.options?.includes(state.state)
        ? state.state
        : "";
      if (select.value !== value) select.value = value;
    }
  }
  _ensureRegistry() {
    if (
      !this.isConnected ||
      !this.hass?.connection ||
      this._connection === this.hass.connection
    )
      return;
    this._unsubscribe?.();
    this._unsubscribe = null;
    this._connection = this.hass.connection;
    this._map = null;
    this._registry = [];
    this._loadRegistry();
    const connection = this._connection;
    connection
      .subscribeEvents(() => this._loadRegistry(), "entity_registry_updated")
      .then((unsubscribe) => {
        if (this.isConnected && this._connection === connection)
          this._unsubscribe = unsubscribe;
        else unsubscribe();
      })
      .catch(() => {
        /* State updates still work; a reload retries registry subscription. */
      });
  }
  async _loadRegistry() {
    const connection = this._connection;
    const sequence = (this._loadSequence ?? 0) + 1;
    this._loadSequence = sequence;
    this._loading = true;
    try {
      const entries = await this.hass.callWS({
        type: "config/entity_registry/list",
      });
      if (
        !this.isConnected ||
        this._connection !== connection ||
        sequence !== this._loadSequence
      )
        return;
      this._registry = entries;
      this._resolveMap();
    } catch {
      if (
        this.isConnected &&
        this._connection === connection &&
        sequence === this._loadSequence
      ) {
        this._error = "registry";
        this._map = null;
      }
    } finally {
      if (sequence === this._loadSequence) {
        this._loading = false;
        this.requestUpdate();
      }
    }
  }
  _resolveMap() {
    if (!this._config?.entity) return;
    if (!this._registry.length && this._loading) return;
    try {
      this._map = discover(this._registry, this._config.entity);
      this._error = null;
    } catch {
      this._map = null;
      this._error = "invalid_device";
    }
  }
  _state(role) {
    return this.hass?.states[this._map?.roles[role]];
  }
  _disabled(role) {
    return (
      this._busy ||
      this.preview ||
      !this.isConnected ||
      !available(this._state("status")) ||
      !(this._map?.roles[role]?.startsWith("button.")
        ? this._state(role) && this._state(role).state !== "unavailable"
        : available(this._state(role)))
    );
  }
  _name() {
    if (this._config.name) return this._config.name;
    const device = this.hass?.devices?.[this._map?.deviceId];
    return device?.name_by_user || device?.name || this.t("name");
  }
  _subtitle() {
    if (this._config.subtitle !== undefined) return this._config.subtitle;
    const device = this.hass?.devices?.[this._map?.deviceId];
    return this.hass?.areas?.[device?.area_id]?.name ?? "";
  }
  _display(state) {
    return state
      ? (this.hass.formatEntityState?.(state) ?? state.state)
      : this.t("unknown");
  }
  _label(entry) {
    return (
      entry.name ||
      entry.original_name ||
      this.hass?.states[entry.entity_id]?.attributes.friendly_name ||
      this.t("unknown")
    );
  }
  _showPanel() {
    const details = this.renderRoot.querySelector("details");
    if (details) {
      details.open = true;
      details.querySelector("select")?.focus();
    }
  }
  async _confirmation(role) {
    this._dialog = role;
    const result = new Promise((resolve) => {
      this._resolveConfirmation = resolve;
    });
    await this.updateComplete;
    if (!this.isConnected || this._dialog !== role) return result;
    const dialog = this.renderRoot.querySelector("dialog");
    dialog?.showModal();
    return result;
  }
  _finishConfirmation(value) {
    this.renderRoot.querySelector("dialog")?.close();
    this._dialog = null;
    this._resolveConfirmation?.(value);
    this._resolveConfirmation = null;
  }
  async _request(role, option) {
    if (this._dialog || this._disabled(role)) return;
    const epoch = this._epoch,
      entity = this._map.roles[role],
      program = this._state("program")?.state,
      status = this._state("status")?.state;
    if (
      ["start", "stop", "clean"].includes(role) &&
      !(await this._confirmation(role))
    )
      return;
    if (
      epoch !== this._epoch ||
      this._disabled(role) ||
      this._map.roles[role] !== entity ||
      this._state("status")?.state !== status ||
      (role === "start" && this._state("program")?.state !== program)
    ) {
      this._feedback = "changed";
      return;
    }
    await this._send(entity, option, epoch);
  }
  async _send(entity, option, epoch = this._epoch) {
    if (this._busy || this.preview || !this.isConnected) return;
    const state = this.hass.states[entity],
      domain = entity.split(".")[0];
    if (
      !this._map ||
      ![
        ...Object.values(this._map.roles),
        ...this._map.parameters.map((p) => p.entity_id),
      ].includes(entity)
    )
      return;
    if (
      !(domain === "button"
        ? state && state.state !== "unavailable"
        : available(state)) ||
      !available(this._state("status"))
    )
      return;
    if (domain === "select" && !state.attributes.options?.includes(option)) {
      this._feedback = "changed";
      return;
    }
    const service =
      domain === "select"
        ? "select_option"
        : domain === "switch"
          ? state.state === "on"
            ? "turn_off"
            : "turn_on"
          : "press";
    const data =
      domain === "select"
        ? { entity_id: entity, option }
        : { entity_id: entity };
    const status = this._state("status");
    const role = Object.keys(this._map.roles).find(
      (key) => this._map.roles[key] === entity,
    );
    const expected =
      domain === "select"
        ? option
        : domain === "switch"
          ? state.state === "on"
            ? "off"
            : "on"
          : {
              wake: "waiting",
              start: "working",
              pause: "paused",
              resume: "working",
              stop: "resting",
            }[role];
    this._busy = true;
    this._feedback = "sending";
    this._observation = null;
    try {
      await this.hass.callService(domain, service, data);
      if (epoch !== this._epoch || !this.isConnected) return;
      this._feedback = role === "program" ? "draft" : "accepted";
      if (expected && role !== "program") {
        const observedEntity =
          domain === "button" ? this._map.roles.status : entity;
        const before = domain === "button" ? status : state;
        this._observation = { entity: observedEntity, expected, before };
        const current = this.hass.states[observedEntity];
        if (current && current !== before && current.state === expected) {
          this._feedback = "reported";
          this._observation = null;
        }
      }
    } catch {
      if (epoch === this._epoch && this.isConnected) this._feedback = "failed";
    } finally {
      if (epoch === this._epoch) this._busy = false;
    }
  }
  _select(entity, label) {
    const state = this.hass.states[entity];
    return html`<label class="field"
      ><span>${label}</span
      ><select
        aria-label=${label}
        data-entity=${entity}
        ?disabled=${this._busy || this.preview || !available(state) || !available(this._state("status"))}
        @change=${(e) => this._send(entity, e.target.value)}
      >
        ${!state?.attributes.options?.includes(state.state) ? html`<option value="">${this.t("unknown")}</option>` : nothing}
        ${(state?.attributes.options ?? []).map((option) => html`<option value=${option} ?selected=${state.state === option}>${option}</option>`)}
      </select></label
    >`;
  }
  render() {
    if (!this.hass || !this._config) return nothing;
    if (!this._config.entity)
      return html`<ha-card class="empty">${this.t("configure")}</ha-card>`;
    if (!this._map)
      return html`<ha-card class="empty" role="status"
        >${this.t(this._error ?? "loading")}</ha-card
      >`;
    const status = this._state("status"),
      value = status?.state,
      primary = primaryAction(value);
    const running = value === "working" && available(status);
    const time = remainingTime(value, this._state("remaining"));
    const summary = [
      "washWaterTemperature",
      "bleachWashTimes",
      "dryingCompoundOption",
    ]
      .map((code) =>
        this._map.parameters.find((e) =>
          e.unique_id.endsWith(`_parameter_${code}`),
        ),
      )
      .filter(Boolean);
    return html`<ha-card
        ><div class="card ${this._config.animation ? "animate" : ""}">
          <header>
            <div class="heading">
              <h2>${this._name()}</h2>
              ${this._subtitle() ? html`<p class="subtitle">${this._subtitle()}</p>` : nothing}
            </div>
            <button
              class="quiet"
              aria-label=${this.t("parameters")}
              @click=${this._showPanel}
            >
              ${icon("settings")}
            </button>
          </header>
          <section class="hero">
            ${appliance(running)}
            <div class="state">
              ${statusLabel(this.hass, status, isChinese(this.hass))}${["working", "paused"].includes(value) && available(this._state("process")) ? html` · ${this._state("process").state}` : nothing}
            </div>
            ${
              this._config.show_remaining
                ? html`<div class="time">${time ?? "—"}</div>
                    <div class="time-label">${this.t("remaining")}</div>`
                : nothing
            }
            ${["resting", "waiting"].includes(value) ? html`<p class="status-context">${this.t("idle")}</p>` : nothing}
          </section>
          <button class="program-row" @click=${this._showPanel}>
            <span>${this.t("pending")}</span
            ><span class="program-value"
              >${this._display(this._state("program"))}${icon("arrow")}</span
            >
          </button>
          <div class="summary">
            ${summary.slice(0, 3).map((entry) => html`<span>${entry.unique_id.endsWith("_parameter_bleachWashTimes") ? this.t("rinse") + " " : ""}${this._display(this.hass.states[entry.entity_id])}</span>`)}
          </div>
          <div class="controls">
            ${primary !== "wake" ? html`<button class="round" aria-label=${this.t("wake")} ?disabled=${this._disabled("wake")} @click=${() => this._request("wake")}>${icon("power")}</button>` : nothing}
            <button
              class="primary"
              ?disabled=${!primary || this._disabled(primary)}
              @click=${() => this._request(primary)}
            >
              ${icon(primary === "pause" ? "pause" : primary === "wake" ? "power" : "play")}${this._busy ? this.t("sending") : primary ? this.t(primary) : this.t("unknown")}
            </button>
            <button
              class="round"
              aria-label=${this.t("stop")}
              ?disabled=${this._disabled("stop")}
              @click=${() => this._request("stop")}
            >
              ${icon("stop")}
            </button>
          </div>
          ${this._feedback ? html`<p class="feedback ${["failed", "changed"].includes(this._feedback) ? "error" : ""}" role="status" aria-live="polite">${this.t(this._feedback)}</p>` : nothing}
          ${this.preview ? html`<p class="preview-note">${this.t("preview")}</p>` : nothing}
          <details>
            <summary>${this.t("parameters")}${icon("arrow")}</summary>
            <div class="panel">
              <p class="hint">${this.t("hint")}</p>
              ${this._map.roles.program ? this._select(this._map.roles.program, this.t("pending")) : nothing}
              ${this._map.parameters.map((entry) => this._select(entry.entity_id, this._label(entry)))}
              ${
                this._config.show_settings
                  ? html`<h3>${this.t("settings")}</h3>
                      ${["tone", "lock", "reminder", "trusteeship"].filter((role) => this._map.roles[role]).map((role) => html`<label class="field"><span>${this.t(role)}</span><input type="checkbox" aria-label=${this.t(role)} .checked=${live(this._state(role)?.state === "on")} ?disabled=${this._disabled(role)} @change=${() => this._request(role)} /></label>`)}
                      ${this._map.roles.threshold ? this._select(this._map.roles.threshold, this.t("threshold")) : nothing}
                      ${this._map.roles.clean ? html`<button class="inline-action" ?disabled=${this._disabled("clean")} @click=${() => this._request("clean")}>${this.t("clean")}</button>` : nothing}`
                  : nothing
              }
            </div>
          </details>
        </div></ha-card
      >
      ${
        this._dialog
          ? html`<dialog
              @cancel=${(e) => {
                e.preventDefault();
                this._finishConfirmation(false);
              }}
            >
              <h3>${this.t(this._dialog)}</h3>
              <p>
                ${this._dialog === "start" ? html`${this._display(this._state("program"))} · ` : nothing}${this.t(`confirm_${this._dialog}`)}
              </p>
              <div class="buttons">
                <button @click=${() => this._finishConfirmation(false)}>
                  ${this.t("cancel")}</button
                ><button
                  class="confirm"
                  @click=${() => this._finishConfirmation(true)}
                >
                  ${this.t("confirm")}
                </button>
              </div>
            </dialog>`
          : nothing
      }`;
  }
  getCardSize() {
    return 13;
  }
  getGridOptions() {
    return { columns: 12, rows: "auto", min_columns: 6 };
  }
  static getConfigElement() {
    return document.createElement("minij-card-editor");
  }
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) =>
        hass.entities?.[id]?.platform === "minij" &&
        hass.states[id].attributes.device_class === "enum" &&
        id.startsWith("sensor."),
    );
    return { entity };
  }
}

export class MinijCardEditor extends LitElement {
  static styles = styles;
  static properties = { hass: { attribute: false }, _config: { state: true } };
  setConfig(config) {
    this._config = { ...config };
  }
  _changed(key, value) {
    this._config = { ...this._config, [key]: value };
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      }),
    );
  }
  render() {
    if (!this.hass || !this._config) return nothing;
    const t = (key) => TEXT[key][isChinese(this.hass) ? 0 : 1];
    const candidates = Object.values(this.hass.states).filter(
      (s) =>
        s.entity_id.startsWith("sensor.") &&
        s.attributes.device_class === "enum" &&
        this.hass.entities?.[s.entity_id]?.platform === "minij",
    );
    return html`<div class="panel">
      <label class="field"
        ><span>${t("entity")}</span
        ><select
          aria-label=${t("entity")}
          @change=${(e) => this._changed("entity", e.target.value)}
        >
          <option value="">—</option>
          ${candidates.map((s) => html`<option value=${s.entity_id} ?selected=${s.entity_id === this._config.entity}>${s.attributes.friendly_name ?? s.entity_id}</option>`)}
        </select></label
      >
      ${["name", "subtitle"].map((key) => html`<label class="field"><span>${t(key === "name" ? "title" : key)}</span><input type="text" aria-label=${t(key === "name" ? "title" : key)} .value=${this._config[key] ?? ""} @change=${(e) => this._changed(key, e.target.value)} /></label>`)}
      ${["animation", "show_remaining", "show_settings"].map((key) => html`<label class="field"><span>${t(key)}</span><input type="checkbox" aria-label=${t(key)} .checked=${this._config[key] !== false} @change=${(e) => this._changed(key, e.target.checked)} /></label>`)}
    </div>`;
  }
}
customElements.define("minij-card", MinijCard);
customElements.define("minij-card-editor", MinijCardEditor);
window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "minij-card",
  name: "MiniJ",
  description: "小吉洗衣机 · 程序与控制 / MiniJ washer controls",
  preview: true,
  documentationURL:
    "https://github.com/ajaxjiang96/ha-minij/blob/main/docs/dashboard.md",
});
