import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CodeInput } from "../components/form";

afterEach(cleanup);

function setup(value: string, template = false, candidates = ["inputs.tema"]) {
  const onChange = vi.fn();
  render(<CodeInput a11y={{ id: "prompt" }} value={value} onChange={onChange} candidates={candidates} template={template} />);
  return { field: screen.getByRole("combobox"), button: screen.getByRole("button", { name: "Vložit proměnnou" }), onChange };
}

function select(field: HTMLElement, start: number, end = start) {
  (field as HTMLInputElement).setSelectionRange(start, end);
  fireEvent.select(field);
}

describe("nabídka proměnných v CodeInput", () => {
  it("vkládá šablonu na pozici kurzoru a výraz bez závorek", () => {
    const template = setup("Ahoj světe", true);
    select(template.field, 4);
    fireEvent.click(template.button);
    fireEvent.click(screen.getByRole("menuitem", { name: "inputs.tema" }));
    expect(template.onChange).toHaveBeenCalledWith("Ahoj{{ inputs.tema }} světe");

    cleanup();
    const expr = setup("left right");
    select(expr.field, 4);
    fireEvent.click(expr.button);
    fireEvent.click(screen.getByRole("menuitem", { name: "inputs.tema" }));
    expect(expr.onChange).toHaveBeenCalledWith("leftinputs.tema right");
  });

  it("uvnitř otevřených {{ }} vloží jen název a výběr nahradí", () => {
    const inside = setup("{{  }}", true);
    select(inside.field, 3);
    fireEvent.click(inside.button);
    fireEvent.click(screen.getByRole("menuitem", { name: "inputs.tema" }));
    expect(inside.onChange).toHaveBeenCalledWith("{{ inputs.tema }}");

    cleanup();
    const selected = setup("zaXXkonec");
    select(selected.field, 2, 4);
    fireEvent.click(selected.button);
    fireEvent.click(screen.getByRole("menuitem", { name: "inputs.tema" }));
    expect(selected.onChange).toHaveBeenCalledWith("zainputs.temakonec");
  });

  it("otevře se klávesnicí, šipka a Enter vyberou, Escape vrátí fokus do pole", () => {
    const { field, button, onChange } = setup("x", false, ["inputs.tema", "steps.copy.text"]);
    select(field, 1);
    fireEvent.keyDown(button, { key: "Enter" });
    const menu = screen.getByRole("menu");
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    fireEvent.keyDown(menu, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("xsteps.copy.text");

    button.focus();
    fireEvent.keyDown(button, { key: " " });
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(document.activeElement).toBe(field);
  });

  it("bez kandidátů je tlačítko disabled", () => {
    const { button } = setup("text", false, []);
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.getAttribute("title")).toBe("Žádné dostupné proměnné");
  });
});
