// Stand-ins for the HA frontend elements the panel uses, with just the behaviour it
// relies on: a disabled or loading button swallows clicks, and type="submit" submits.

class HaButton extends HTMLElement {
  loading = false;
  type = "button";

  constructor() {
    super();
    this.addEventListener("click", (event) => {
      if (this.disabled || this.loading) {
        event.stopImmediatePropagation();
        return;
      }
      if ((this.getAttribute("type") ?? this.type) === "submit")
        this.closest("form")?.requestSubmit();
    });
  }

  get disabled() {
    return this.hasAttribute("disabled");
  }

  set disabled(value: boolean) {
    this.toggleAttribute("disabled", value);
  }
}

class HaIconButton extends HaButton {
  label = "";
  path = "";

  get selected() {
    return this.hasAttribute("selected");
  }

  set selected(value: boolean) {
    this.toggleAttribute("selected", value);
  }
}

class HaSvgIcon extends HTMLElement {
  path = "";
}

customElements.define("ha-button", HaButton);
customElements.define("ha-icon-button", HaIconButton);
customElements.define("ha-svg-icon", HaSvgIcon);
