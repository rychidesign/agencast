// Wave D: a file error reported both on the project and on the agent shows once in the count and the list.
import { describe, expect, it } from "vitest";
import { allErrors } from "../pages/Project";
import type { Project } from "../types";

describe("allErrors", () => {
  it("merges the same error from the project and from the file", () => {
    const e = { file: "agents/a.md", message: "missing field version" };
    const p = { errors: [e], scenarios: [], skills: [], agents: [{ errors: [{ ...e }] }] } as unknown as Project;
    expect(allErrors(p)).toEqual([e]);
  });
});
