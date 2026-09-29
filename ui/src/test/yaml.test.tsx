import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CodeInput } from "../components/form";
import { CodeBlock } from "../components/ui";
import { lineContexts, Line } from "../components/yaml";
import { DiffModal, YamlEditor } from "../components/YamlEditor";

afterEach(cleanup);

function check(text: string, variables: string[], operators: string[], expression = false) {
  const { container } = render(<Line text={text} expression={expression} />);
  expect(container.textContent).toBe(text);
  expect([...container.querySelectorAll(".text-variable")].map((el) => el.textContent)).toEqual(variables);
  expect([...container.querySelectorAll(".text-success")].map((el) => el.textContent)).toEqual(operators);
  return container;
}

describe("YAML zvýraznění", () => {
  it("barví proměnné v šabloně, i v uvozovkách a v řádku bloku", () => {
    const line = 'prompt: "Téma: {{ inputs.tema }} a {{ steps.copy.hashtags[0] }}"';
    const container = check(line, ["inputs.tema", "steps.copy.hashtags[0]"], []);
    expect([...container.querySelectorAll(".text-fg-muted")].map((el) => el.textContent)).toEqual(["{{", "}}", "{{", "}}"]);
    check("  {{ params.jazyk }}", ["params.jazyk"], []);
  });

  it("barví proměnné a operátory v when, ale ne textové literály a komentář", () => {
    check('when: steps.a.x > 0.5 or steps.b.y >= 0.5 and inputs.jazyk not in ["or", "in"] # +',
      ["steps.a.x", "steps.b.y", "inputs.jazyk"], [">", "or", ">=", "and", "not in"]);
    check("when: 'steps.kontrola.on_brand < 0.7'", ["steps.kontrola.on_brand"], ["<"]);
    check('when: steps.kontrola.details["on_brand"] == true and not false',
      ['steps.kontrola.details["on_brand"]'], ["==", "and", "not"]);
    check("when: inputs.jazyk in notebook", ["inputs.jazyk"], ["in"]);
  });

  it("nebarví odrážku, komentář ani operátory mimo výraz", () => {
    check("  - id: copy", [], []);
    check("  # steps.copy.x > 0", [], []);
    check('fail: "on_brand = {{ steps.kontrola.on_brand }}"', ["steps.kontrola.on_brand"], []);
    check("description: kroky - copy = hotovo and dál", [], []);
  });

  it("rozliší switch.value a hodnoty set od ostatních polí value", () => {
    const lines = [
      "  - id: s", "    switch:", "      value: steps.copy.caption", "      cases:",
      "        cs:", "          - id: x", "            set:", "              delka: len(steps.copy.caption) + 1",
      "    value: inputs.jazyk - 1", "  value: inputs.jazyk - 1",
    ];
    const flags = lineContexts(lines).map((context) => context.expression);
    expect(flags).toEqual([false, false, true, false, false, false, false, true, false, false]);
    check(lines[2], ["steps.copy.caption"], [], flags[2]);
    check(lines[7], ["steps.copy.caption"], ["+"], flags[7]);
    check(lines[8], [], [], flags[8]);
    check('x: \'"and" + str(steps.copy.caption)\'', ["steps.copy.caption"], ["+"], true);
  });

  it("zachová šablonu v blokovém textu i na řádku s # nebo when:", () => {
    const text = "prompt: >-\n  # {{ inputs.tema }}\n  when: {{ steps.copy.caption }}";
    const { container } = render(<CodeBlock text={text} yaml />);
    expect([...container.querySelectorAll(".text-variable")].map((el) => el.textContent)).toEqual(["inputs.tema", "steps.copy.caption"]);
    expect(container.querySelector(".text-success")).toBeNull();
    expect([...container.querySelectorAll("td.whitespace-pre-wrap")].map((el) => el.textContent)).toEqual(text.split("\n"));
  });

  it("předá stejné zvýraznění do bloku kódu, editoru i rozdílu", () => {
    const text = "set:\n  x: steps.copy.hashtags[0] + 1";
    for (const ui of [<CodeBlock text={text} yaml />, <YamlEditor text={text} file="test.yaml" errors={[]} onChange={() => {}} />,
      <DiffModal title="rozdíl" before="set:\n  x: 1" after={text} onClose={() => {}} />]) {
      const view = render(ui);
      expect(document.querySelector(".text-variable")?.textContent).toBe("steps.copy.hashtags[0]");
      expect([...document.querySelectorAll(".text-success")].map((el) => el.textContent)).toContain("+");
      view.unmount();
    }
    const editor = render(<YamlEditor text={text} file="test.yaml" errors={[]} onChange={() => {}} />);
    expect([...editor.container.querySelectorAll("pre > div")].map((el) => el.textContent)).toEqual(text.split("\n"));
  });

  it("v Markdownu zvýrazní jen frontmatter", () => {
    const text = "---\nname: copy\ndescription: steps.a.x + 1\n---\n# Nadpis\nSlovo: {{ inputs.tema }}";
    const { container } = render(<YamlEditor text={text} file="agents/copy.md" errors={[]} onChange={() => {}} />);
    expect([...container.querySelectorAll("pre .text-fg")].map((el) => el.textContent)).toEqual(["name:", "description:"]);
    expect(container.querySelector("pre .text-variable")).toBeNull();
    expect(container.querySelector("pre .text-fg-muted")).toBeNull();
  });

  it("CodeBlock bez yaml text nebarví", () => {
    const { container } = render(<CodeBlock text="when: steps.a.x > 1" />);
    expect(container.querySelector(".text-variable")).toBeNull();
  });

  it("barví hodnotu výrazu i šablony v poli formuláře", () => {
    const expr = render(<CodeInput a11y={{ id: "w" }} value="steps.a.x > 0.5" candidates={[]} onChange={() => {}} />);
    const overlay = expr.container.querySelector("[aria-hidden] .text-variable")!.closest("[aria-hidden]")!;
    expect(overlay.textContent).toBe("steps.a.x > 0.5");
    expect([...overlay.querySelectorAll(".text-success")].map((el) => el.textContent)).toEqual([">"]);
    expr.unmount();
    const tpl = render(<CodeInput a11y={{ id: "t" }} template multiline value="a > b {{ inputs.tema }}" candidates={[]} onChange={() => {}} />);
    expect([...tpl.container.querySelectorAll("[aria-hidden] .text-variable")].map((el) => el.textContent)).toEqual(["inputs.tema"]);
    expect(tpl.container.querySelector("[aria-hidden] .text-success")).toBeNull();
  });
});
