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

describe("YAML highlighting", () => {
  it("colors variables in a template, also inside quotes and in a block line", () => {
    const line = 'prompt: "Topic: {{ inputs.topic }} and {{ steps.copy.hashtags[0] }}"';
    const container = check(line, ["inputs.topic", "steps.copy.hashtags[0]"], []);
    expect([...container.querySelectorAll(".text-fg-muted")].map((el) => el.textContent)).toEqual(["{{", "}}", "{{", "}}"]);
    check("  {{ params.language }}", ["params.language"], []);
  });

  it("colors variables and operators in when, but not string literals and the comment", () => {
    check('when: steps.a.x > 0.5 or steps.b.y >= 0.5 and inputs.language not in ["or", "in"] # +',
      ["steps.a.x", "steps.b.y", "inputs.language"], [">", "or", ">=", "and", "not in"]);
    check("when: 'steps.check.on_brand < 0.7'", ["steps.check.on_brand"], ["<"]);
    check('when: steps.check.details["on_brand"] == true and not false',
      ['steps.check.details["on_brand"]'], ["==", "and", "not"]);
    check("when: inputs.language in notebook", ["inputs.language"], ["in"]);
  });

  it("does not color the list dash, a comment or operators outside an expression", () => {
    check("  - id: copy", [], []);
    check("  # steps.copy.x > 0", [], []);
    check('fail: "on_brand = {{ steps.check.on_brand }}"', ["steps.check.on_brand"], []);
    check("description: steps - copy = done and more", [], []);
  });

  it("tells switch.value and set values apart from other value fields", () => {
    const lines = [
      "  - id: s", "    switch:", "      value: steps.copy.caption", "      cases:",
      "        en:", "          - id: x", "            set:", "              length: len(steps.copy.caption) + 1",
      "    value: inputs.language - 1", "  value: inputs.language - 1",
    ];
    const flags = lineContexts(lines).map((context) => context.expression);
    expect(flags).toEqual([false, false, true, false, false, false, false, true, false, false]);
    check(lines[2], ["steps.copy.caption"], [], flags[2]);
    check(lines[7], ["steps.copy.caption"], ["+"], flags[7]);
    check(lines[8], [], [], flags[8]);
    check('x: \'"and" + str(steps.copy.caption)\'', ["steps.copy.caption"], ["+"], true);
  });

  it("keeps a template in block text, also on a line with # or when:", () => {
    const text = "prompt: >-\n  # {{ inputs.topic }}\n  when: {{ steps.copy.caption }}";
    const { container } = render(<CodeBlock text={text} yaml />);
    expect([...container.querySelectorAll(".text-variable")].map((el) => el.textContent)).toEqual(["inputs.topic", "steps.copy.caption"]);
    expect(container.querySelector(".text-success")).toBeNull();
    expect([...container.querySelectorAll("td.whitespace-pre-wrap")].map((el) => el.textContent)).toEqual(text.split("\n"));
  });

  it("passes the same highlighting to the code block, editor and diff", () => {
    const text = "set:\n  x: steps.copy.hashtags[0] + 1";
    for (const ui of [<CodeBlock text={text} yaml />, <YamlEditor text={text} file="test.yaml" errors={[]} onChange={() => {}} />,
      <DiffModal title="diff" before="set:\n  x: 1" after={text} onClose={() => {}} />]) {
      const view = render(ui);
      expect(document.querySelector(".text-variable")?.textContent).toBe("steps.copy.hashtags[0]");
      expect([...document.querySelectorAll(".text-success")].map((el) => el.textContent)).toContain("+");
      view.unmount();
    }
    const editor = render(<YamlEditor text={text} file="test.yaml" errors={[]} onChange={() => {}} />);
    expect([...editor.container.querySelectorAll("pre > div")].map((el) => el.textContent)).toEqual(text.split("\n"));
  });

  it("in Markdown highlights only the frontmatter", () => {
    const text = "---\nname: copy\ndescription: steps.a.x + 1\n---\n# Heading\nWord: {{ inputs.topic }}";
    const { container } = render(<YamlEditor text={text} file="agents/copy.md" errors={[]} onChange={() => {}} />);
    expect([...container.querySelectorAll("pre .text-fg")].map((el) => el.textContent)).toEqual(["name:", "description:"]);
    expect(container.querySelector("pre .text-variable")).toBeNull();
    expect(container.querySelector("pre .text-fg-muted")).toBeNull();
  });

  it("CodeBlock without yaml does not color text", () => {
    const { container } = render(<CodeBlock text="when: steps.a.x > 1" />);
    expect(container.querySelector(".text-variable")).toBeNull();
  });

  it("colors expression and template values in a form field", () => {
    const expr = render(<CodeInput a11y={{ id: "w" }} value="steps.a.x > 0.5" candidates={[]} onChange={() => {}} />);
    const overlay = expr.container.querySelector("[aria-hidden] .text-variable")!.closest("[aria-hidden]")!;
    expect(overlay.textContent).toBe("steps.a.x > 0.5");
    expect([...overlay.querySelectorAll(".text-success")].map((el) => el.textContent)).toEqual([">"]);
    expr.unmount();
    const tpl = render(<CodeInput a11y={{ id: "t" }} template multiline value="a > b {{ inputs.topic }}" candidates={[]} onChange={() => {}} />);
    expect([...tpl.container.querySelectorAll("[aria-hidden] .text-variable")].map((el) => el.textContent)).toEqual(["inputs.topic"]);
    expect(tpl.container.querySelector("[aria-hidden] .text-success")).toBeNull();
  });
});
