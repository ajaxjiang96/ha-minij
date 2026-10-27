import { css, html, svg } from "lit";
export const icons = {
  power: "M12 3v9 M6.3 5.8a8 8 0 1 0 11.4 0",
  play: "M8 5l11 7-11 7Z",
  pause: "M8 5v14 M16 5v14",
  stop: "M6 6h12v12H6Z",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z",
  arrow: "M9 5l7 7-7 7",
  close: "M6 6l12 12 M18 6L6 18",
};
export const icon = (name) =>
  html`<svg
    class="icon"
    viewBox="0 0 24 24"
    aria-hidden="true"
    fill="none"
    stroke="currentColor"
    stroke-width=${name === "pause" ? "3.2" : "1.8"}
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <path
      fill=${name === "stop" ? "currentColor" : "none"}
      d=${icons[name] ?? icons.settings}
    ></path>
  </svg>`;
export function appliance(running) {
  return svg`<svg class="appliance ${running ? "running" : ""}" viewBox="0 0 300 360" role="img" aria-label="MiniJ V6-XNB" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
    <path class="shell" d="M150 10C68 10 6 72 6 150C6 230 91 344 150 344S294 230 294 150C294 72 232 10 150 10Z"/>
    <circle cx="150" cy="149" r="113"/><circle cx="150" cy="149" r="107"/>
    <path d="M150 48a101 101 0 0 1 62 181c-13 10-111 10-124 0A101 101 0 0 1 150 48Z"/>
    <g class="drum"><circle cx="150" cy="149" r="82" opacity=".28"/>
      <path d="M150 67c-6 7-6 29 0 48 6-19 6-41 0-48Zm-71 123c10 2 29-9 43-24-20 4-39 15-43 24Zm142 0c-4-9-23-20-43-24 14 15 33 26 43 24Z" opacity=".38"/>
    </g>
    <text x="150" y="153" text-anchor="middle" stroke="none" fill="currentColor" font-size="12" font-family="system-ui,sans-serif" letter-spacing="1">minij</text>
  </svg>`;
}
export const styles = css`
  :host {
    display: block;
    color: var(--primary-text-color, #181818);
    font-family: var(
      --paper-font-body1_-_font-family,
      Roboto,
      system-ui,
      sans-serif
    );
  }
  * {
    box-sizing: border-box;
  }
  ha-card {
    display: block;
    border-radius: var(--ha-card-border-radius, 20px);
    background: var(--ha-card-background, var(--card-background-color, #fff));
    color: inherit;
    border: 1px solid var(--ha-card-border-color, var(--divider-color, #e5e5e5));
    box-shadow: var(--ha-card-box-shadow, none);
    overflow: hidden;
  }
  .card {
    padding: 24px 22px 0;
  }
  header {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  h2 {
    font-size: 22px;
    line-height: 1.35;
    letter-spacing: -0.5px;
    margin: 0;
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  header .heading {
    flex: 1;
  }
  .subtitle {
    color: var(--secondary-text-color, #777);
    font-size: 14px;
    line-height: 1.5;
    margin: 7px 0 0;
  }
  button,
  select,
  input {
    font: inherit;
    color: inherit;
  }
  button {
    cursor: pointer;
    border: 0;
    background: none;
  }
  button:disabled,
  select:disabled {
    cursor: default;
    opacity: 0.4;
  }
  button:focus-visible,
  select:focus-visible,
  input:focus-visible,
  summary:focus-visible {
    outline: 2px solid var(--primary-color, #03a9f4);
    outline-offset: 3px;
  }
  .icon {
    width: 24px;
    height: 24px;
    flex: none;
  }
  .quiet {
    display: grid;
    place-items: center;
    padding: 6px;
    border-radius: 50%;
    flex: none;
  }
  .quiet:hover {
    background: var(--secondary-background-color, #f5f5f5);
  }
  .hero {
    text-align: center;
    padding-top: 0;
  }
  .appliance {
    display: block;
    width: min(100%, 255px);
    height: 282px;
    margin: 0 auto 8px;
    stroke-width: 1.3;
  }
  .appliance .shell {
    stroke-width: 1.4;
  }
  .drum {
    transform-origin: 150px 149px;
  }
  .animate .running .drum {
    animation: tumble 9s linear infinite;
  }
  @keyframes tumble {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .animate .running .drum {
      animation: none;
    }
  }
  .state {
    font-size: 17px;
    line-height: 1.4;
    overflow-wrap: anywhere;
  }
  .time {
    font-size: 42px;
    line-height: 1.1;
    font-weight: 500;
    letter-spacing: -1px;
    font-variant-numeric: tabular-nums;
    margin-top: 5px;
  }
  .time-label {
    font-size: 13px;
    color: var(--secondary-text-color, #777);
    margin-top: 5px;
  }
  .status-context {
    font-size: 12px;
    line-height: 1.4;
    color: var(--secondary-text-color, #777);
    margin: 8px 0;
  }
  .program-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    width: 100%;
    margin-top: 16px;
    padding: 13px 15px;
    border: 1px solid var(--divider-color, #e5e5e5);
    border-radius: 12px;
    text-align: start;
    font-size: 14px;
  }
  .program-value {
    display: flex;
    align-items: center;
    gap: 7px;
    font-weight: 500;
  }
  .summary {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    margin: 14px 0 18px;
    color: var(--secondary-text-color, #777);
    font-size: 13px;
    min-height: 18px;
  }
  .summary span {
    padding: 0 10px;
    text-align: center;
  }
  .summary span + span {
    border-left: 1px solid var(--divider-color, #ddd);
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .round {
    border: 1px solid var(--divider-color, #e5e5e5);
    width: 48px;
    height: 48px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    flex: none;
  }
  .primary {
    height: 48px;
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    background: var(--primary-text-color, #181818);
    color: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: 30px;
    font-size: 16px;
    font-weight: 500;
  }
  .primary:disabled {
    opacity: 0.35;
  }
  .feedback {
    font-size: 12px;
    line-height: 1.5;
    margin: 14px 0 0;
    overflow-wrap: anywhere;
  }
  .error {
    color: var(--error-color, #db4437);
  }
  .preview-note {
    color: var(--secondary-text-color, #777);
    font-size: 12px;
    margin: 12px 0 0;
    text-align: center;
  }
  details {
    margin-top: 18px;
    border-top: 1px solid var(--divider-color, #e5e5e5);
  }
  summary {
    list-style: none;
    cursor: pointer;
    padding: 15px 0;
    font-size: 14px;
    color: var(--secondary-text-color, #777);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  summary::-webkit-details-marker {
    display: none;
  }
  summary .icon {
    width: 18px;
    height: 18px;
  }
  details[open] summary .icon {
    transform: rotate(90deg);
  }
  .panel {
    padding-bottom: 18px;
  }
  .hint {
    font-size: 12px;
    line-height: 1.6;
    color: var(--secondary-text-color, #777);
    margin: 0 0 12px;
  }
  .field {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 0;
    font-size: 14px;
  }
  .field > span {
    max-width: 48%;
    overflow-wrap: anywhere;
  }
  select,
  input[type="text"] {
    min-width: 0;
    max-width: 55%;
    border: 1px solid var(--divider-color, #ddd);
    padding: 7px 9px;
    background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: 8px;
    font-size: 14px;
  }
  .field select {
    flex: 1;
  }
  input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: var(--primary-text-color, #181818);
  }
  .empty {
    padding: 22px;
    font-size: 14px;
    line-height: 1.6;
  }
  .inline-action {
    border: 1px solid var(--divider-color, #ddd);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
  }
  dialog {
    background: var(--ha-card-background, var(--card-background-color, #fff));
    color: var(--primary-text-color, #181818);
    border: 1px solid var(--divider-color, #ddd);
    border-radius: 18px;
    padding: 24px;
    max-width: min(420px, calc(100vw - 32px));
    box-shadow: 0 14px 50px #0004;
  }
  dialog::backdrop {
    background: #0007;
  }
  dialog h3 {
    font-size: 20px;
    margin: 0 0 12px;
  }
  dialog p {
    font-size: 15px;
    line-height: 1.6;
    margin: 0 0 20px;
  }
  dialog .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }
  dialog button {
    padding: 9px 16px;
    border: 1px solid var(--divider-color, #ddd);
    border-radius: 8px;
  }
  dialog .confirm {
    background: var(--primary-text-color, #181818);
    color: var(--ha-card-background, var(--card-background-color, #fff));
  }
  @media (max-width: 360px) {
    .card {
      padding: 20px 16px 0;
    }
    h2 {
      font-size: 19px;
    }
    .appliance {
      height: 250px;
      width: 220px;
    }
    .summary span {
      padding: 0 7px;
    }
    .controls {
      gap: 10px;
    }
  }
`;
