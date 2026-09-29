import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { NameDialog, slugify } from "../components/form";
import { KeyInput } from "../components/StepPanel";

afterEach(cleanup);

describe("jméno podle pravidla při psaní", () => {
  it("odstraní diakritiku, zmenší písmena a ostatní znaky nahradí oddělovačem", () => {
    expect(slugify("Kontrola tónu")).toBe("kontrola-tonu");
    expect(slugify("Příliš žluťoučký kůň")).toBe("prilis-zlutoucky-kun");
    expect(slugify("IG post / Léto 2026")).toBe("ig-post-leto-2026");
    expect(slugify("muj ")).toBe("muj-"); // mezera na konci při psaní zůstane jako oddělovač
    expect(slugify("2. Krok", "_")).toBe("krok");
    expect(slugify("Počet_slov-celkem", "_")).toBe("pocet_slov_celkem");
    expect(slugify("2 větve", "_", false)).toBe("2_vetve");
  });

  it("NameDialog upraví napsané jméno, případ switch nechá", () => {
    render(<NameDialog title="Nový scénář" taken={[]} onSubmit={() => {}} onCancel={() => {}} />);
    const input = screen.getByRole("textbox", { name: /Jméno/ }) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Kontrola Tónu" } });
    expect(input.value).toBe("kontrola-tonu");
    cleanup();
    render(<NameDialog title="Případ" taken={[]} normalize={null} pattern={/^[^\s/][^/]*$/} onSubmit={() => {}} onCancel={() => {}} />);
    const raw = screen.getByRole("textbox", { name: /Jméno/ }) as HTMLInputElement;
    fireEvent.change(raw, { target: { value: "Ano" } });
    expect(raw.value).toBe("Ano");
  });

  it("KeyInput dá podtržítko, alias pomlčku", () => {
    render(<KeyInput name="q_1" taken={[]} onRename={() => {}} />);
    const key = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(key, { target: { value: "Je to česky" } });
    expect(key.value).toBe("je_to_cesky");
    cleanup();
    render(<KeyInput name="gpt" taken={[]} onRename={() => {}} normalize={slugify} />);
    const alias = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(alias, { target: { value: "GPT Image" } });
    expect(alias.value).toBe("gpt-image");
  });
});
