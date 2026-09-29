import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { NameDialog, slugify } from "../components/form";
import { KeyInput } from "../components/StepPanel";

afterEach(cleanup);

describe("name follows the rule while typing", () => {
  it("strips diacritics, lowercases and replaces other characters with the separator", () => {
    expect(slugify("Café Crème")).toBe("cafe-creme");
    expect(slugify("Crème brûlée à la façon")).toBe("creme-brulee-a-la-facon");
    expect(slugify("IG post / Été 2026")).toBe("ig-post-ete-2026");
    expect(slugify("my ")).toBe("my-"); // a trailing space while typing stays as a separator
    expect(slugify("2. Step", "_")).toBe("step");
    expect(slugify("Résumé_word-count", "_")).toBe("resume_word_count");
    expect(slugify("2 crêpes", "_", false)).toBe("2_crepes");
  });

  it("NameDialog normalizes the typed name, a switch case keeps it", () => {
    render(<NameDialog title="New scenario" taken={[]} onSubmit={() => {}} onCancel={() => {}} />);
    const input = screen.getByRole("textbox", { name: /Name/ }) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Café Crème" } });
    expect(input.value).toBe("cafe-creme");
    cleanup();
    render(<NameDialog title="Case" taken={[]} normalize={null} pattern={/^[^\s/][^/]*$/} onSubmit={() => {}} onCancel={() => {}} />);
    const raw = screen.getByRole("textbox", { name: /Name/ }) as HTMLInputElement;
    fireEvent.change(raw, { target: { value: "Yes" } });
    expect(raw.value).toBe("Yes");
  });

  it("KeyInput uses an underscore, alias a hyphen", () => {
    render(<KeyInput name="q_1" taken={[]} onRename={() => {}} />);
    const key = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(key, { target: { value: "Très Bien Noël" } });
    expect(key.value).toBe("tres_bien_noel");
    cleanup();
    render(<KeyInput name="gpt" taken={[]} onRename={() => {}} normalize={slugify} />);
    const alias = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(alias, { target: { value: "GPT Image" } });
    expect(alias.value).toBe("gpt-image");
  });
});
