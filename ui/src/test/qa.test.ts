// Vlna D: chyba souboru hlášená v projektu i u agenta se v počtu a seznamu ukáže jednou.
import { describe, expect, it } from "vitest";
import { allErrors } from "../pages/Project";
import type { Project } from "../types";

describe("allErrors", () => {
  it("sloučí stejnou chybu z projektu a ze souboru", () => {
    const e = { file: "agents/a.md", message: "chybí pole version" };
    const p = { errors: [e], scenarios: [], skills: [], agents: [{ errors: [{ ...e }] }] } as unknown as Project;
    expect(allErrors(p)).toEqual([e]);
  });
});
