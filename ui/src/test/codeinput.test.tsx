import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CodeInput } from "../components/form";

afterEach(cleanup);

function setup(value: string, template = false, candidates = ["inputs.topic"]) {
  const onChange = vi.fn();
  render(<CodeInput a11y={{ id: "prompt" }} value={value} onChange={onChange} candidates={candidates} template={template} />);
  return { field: screen.getByRole("combobox"), button: screen.getByRole("button", { name: "Insert variable" }), onChange };
}

function select(field: HTMLElement, start: number, end = start) {
  (field as HTMLInputElement).setSelectionRange(start, end);
  fireEvent.select(field);
}

describe("variable menu in CodeInput", () => {
  it("inserts a template at the cursor and an expression without braces", () => {
    const template = setup("Hello world", true);
    select(template.field, 5);
    fireEvent.click(template.button);
    fireEvent.click(screen.getByRole("menuitem", { name: "inputs.topic" }));
    expect(template.onChange).toHaveBeenCalledWith("Hello{{ inputs.topic }} world");

    cleanup();
    const expr = setup("left right");
    select(expr.field, 4);
    fireEvent.click(expr.button);
    fireEvent.click(screen.getByRole("menuitem", { name: "inputs.topic" }));
    expect(expr.onChange).toHaveBeenCalledWith("leftinputs.topic right");
  });

  it("inside open {{ }} inserts only the name and replaces the selection", () => {
    const inside = setup("{{  }}", true);
    select(inside.field, 3);
    fireEvent.click(inside.button);
    fireEvent.click(screen.getByRole("menuitem", { name: "inputs.topic" }));
    expect(inside.onChange).toHaveBeenCalledWith("{{ inputs.topic }}");

    cleanup();
    const selected = setup("toXXend");
    select(selected.field, 2, 4);
    fireEvent.click(selected.button);
    fireEvent.click(screen.getByRole("menuitem", { name: "inputs.topic" }));
    expect(selected.onChange).toHaveBeenCalledWith("toinputs.topicend");
  });

  it("opens from the keyboard, arrow and Enter pick, Escape returns focus to the field", () => {
    const { field, button, onChange } = setup("x", false, ["inputs.topic", "steps.copy.text"]);
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

  it("without candidates the button is disabled", () => {
    const { button } = setup("text", false, []);
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.getAttribute("title")).toBe("No variables available");
  });
});
