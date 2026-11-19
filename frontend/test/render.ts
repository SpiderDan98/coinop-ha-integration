// Mounts the panel the way Home Assistant does and reads what it renders.
import { afterEach } from "vitest";
import "../src/wattbill-panel";
import type { WattbillPanel } from "../src/wattbill-panel";
import type { FakeBackend } from "./fake-hass";

const PREFIX = "/wattbill";
const cleanups: (() => void)[] = [];

afterEach(() => {
  while (cleanups.length) cleanups.pop()?.();
});

/** Shadow-piercing `querySelectorAll`. */
export function queryAll(root: Element | ShadowRoot, selector: string): HTMLElement[] {
  const found = [...root.querySelectorAll<HTMLElement>(selector)];
  for (const element of root.querySelectorAll("*")) {
    if (element.shadowRoot) found.push(...queryAll(element.shadowRoot, selector));
  }
  if (root instanceof Element && root.shadowRoot)
    found.push(...queryAll(root.shadowRoot, selector));
  return found;
}

export function query(root: Element | ShadowRoot, selector: string) {
  const [first] = queryAll(root, selector);
  if (!first) throw new Error(`nothing matches ${selector}`);
  return first;
}

/** An `ha-icon-button`'s label, which HA takes as a property, not an attribute. */
export const label = (button: HTMLElement) => (button as HTMLElement & { label: string }).label;

export function iconButton(root: Element | ShadowRoot, name: string) {
  const found = queryAll(root, "ha-icon-button").find((candidate) => label(candidate) === name);
  if (!found) throw new Error(`no icon button "${name}"`);
  return found;
}

/** Rendered text, shadow roots included, with whitespace collapsed. */
export function text(node: Node): string {
  const parts: string[] = [];
  const walk = (current: Node) => {
    if (current.nodeType === Node.TEXT_NODE) parts.push(current.textContent ?? "");
    if (current instanceof Element && current.shadowRoot) walk(current.shadowRoot);
    current.childNodes.forEach(walk);
  };
  walk(node);
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

/** Let pending websocket replies arrive and every element finish rendering. */
export async function settle(root: Element) {
  for (let round = 0; round < 5; round++) {
    await new Promise((resolve) => setTimeout(resolve));
    const elements = [root, ...queryAll(root, "*")] as Partial<WattbillPanel>[];
    await Promise.all(elements.map((element) => element.updateComplete));
  }
}

export async function mountPanel(backend: FakeBackend, { path = "", narrow = false } = {}) {
  history.replaceState(null, "", PREFIX + path);
  const panel = document.createElement("wattbill-panel") as WattbillPanel;
  panel.hass = backend.hass;
  panel.narrow = narrow;
  panel.route = { prefix: PREFIX, path };
  panel.panel = { url_path: "wattbill", config: null };
  // HA's router: a `location-changed` event becomes a new `route`.
  const followNavigation = () => {
    panel.route = { prefix: PREFIX, path: location.pathname.slice(PREFIX.length) };
  };
  window.addEventListener("location-changed", followNavigation);
  document.body.append(panel);
  cleanups.push(() => {
    window.removeEventListener("location-changed", followNavigation);
    panel.remove();
  });
  await settle(panel);
  return panel;
}

export async function click(panel: Element, element: HTMLElement) {
  element.click();
  await settle(panel);
}

/** What the user does to a field: enter a value, then leave it. */
export async function change(panel: Element, element: HTMLElement, value: string) {
  (element as HTMLInputElement).value = value;
  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  await settle(panel);
}

/** Type into an input or pick an option, the way a user changes a field. */
export async function fill(panel: Element, field: HTMLElement, value: string) {
  const control = field as HTMLInputElement;
  if (control.type === "checkbox") control.checked = value === "on";
  else control.value = value;
  control.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  control.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  await settle(panel);
}
