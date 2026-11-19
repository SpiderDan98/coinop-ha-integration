// The part of Home Assistant's documented custom panel contract the panel uses.

export type Message = { type: string } & Record<string, unknown>;

export interface HomeAssistant {
  language: string;
  config: { currency: string; time_zone: string };
  callWS<T>(msg: Message): Promise<T>;
  fetchWithAuth(path: string, init?: RequestInit): Promise<Response>;
  connection: {
    subscribeMessage<T>(callback: (event: T) => void, msg: Message): Promise<() => Promise<void>>;
  };
}

export interface PanelRoute {
  prefix: string;
  path: string;
}

export interface PanelInfo {
  url_path: string;
  config: unknown;
}

/** In-app navigation the way HA's own `navigate()` does it. */
export function navigate(path: string) {
  history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}

/** Download a file the way HA's frontend does: a plain link, so the path must be signed. */
export function download(path: string) {
  const link = document.createElement("a");
  link.href = path;
  link.download = "";
  link.style.display = "none";
  document.body.append(link);
  link.click();
  link.remove();
}

/** Follow a link inside HA unless the user wants it in a new tab or window. */
export function followLink(event: MouseEvent) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
    return;
  event.preventDefault();
  navigate((event.currentTarget as HTMLAnchorElement).getAttribute("href") ?? "");
}
