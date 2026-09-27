import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Markdown } from "../components/Markdown";
import { Modal, ValueInput } from "../components/form";
import { CodeBlock, Menu, StatusChip, type Status } from "../components/ui";

afterEach(cleanup);

it("čipy rozlišují všech deset stavů ikonou, textem a tokenovou barvou", () => {
  const colors: Record<Status, string> = {
    succeeded: "text-success", failed: "text-error", warning: "text-warning",
    cancelled: "text-warning", interrupted: "text-warning", running: "text-running",
    queued: "text-neutral", skipped: "text-neutral", "dry-run": "text-neutral", none: "text-neutral",
  };
  for (const [status, color] of Object.entries(colors) as [Status, string][]) {
    const { unmount } = render(<StatusChip status={status}>{status}</StatusChip>);
    const chip = screen.getByText(status).closest(".rounded-full")!;
    expect(chip.className).toContain("bg-nested");
    expect(chip.querySelector("svg")?.getAttribute("class")).toContain(color);
    expect(screen.getByText(status)).toBeTruthy();
    unmount();
  }
});

it("menu označí nebezpečnou položku a přeskočí zakázanou", () => {
  const select = vi.fn();
  render(<Menu label="Akce" items={[
    { label: "Nedostupné", disabled: "Bez oprávnění", onSelect: select },
    { label: "Smazat", danger: true, onSelect: select },
  ]} />);
  const trigger = screen.getByRole("button", { name: "Akce" });
  fireEvent.click(trigger);
  const blocked = screen.getByRole("menuitem", { name: "Nedostupné" });
  const danger = screen.getByRole("menuitem", { name: "Smazat" });
  expect(blocked.getAttribute("title")).toBe("Bez oprávnění");
  expect(blocked.getAttribute("aria-disabled")).toBe("true");
  expect(danger.className).toContain("text-error");
  fireEvent.click(blocked);
  expect(select).not.toHaveBeenCalled();
  fireEvent.keyDown(danger, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it("modál vrací fokus, nebezpečná akce používá danger a souborové pole je zakázané", () => {
  const outside = document.createElement("button");
  document.body.append(outside);
  outside.focus();
  const cancel = vi.fn();
  const { unmount } = render(<Modal title="Smazat" actions={[{ label: "Smazat", danger: true, onSelect: vi.fn() }]} onCancel={cancel} />);
  const dialog = screen.getByRole("dialog");
  const first = screen.getByRole("button", { name: "Smazat" });
  expect(first.className).toContain("text-error");
  expect(document.activeElement).toBe(first);
  fireEvent.keyDown(dialog, { key: "Escape" });
  expect(cancel).toHaveBeenCalledOnce();
  unmount();
  expect(document.activeElement).toBe(outside);
  outside.remove();

  render(<ValueInput a11y={{ id: "soubor" }} type="file" value={undefined} onChange={vi.fn()} />);
  expect((screen.getByRole("textbox") as HTMLInputElement).disabled).toBe(true);
});

it("Markdown vykreslí odkazy a blok kódu bezpečně", () => {
  render(<Markdown text={'# Přehled\n[Web](https://example.com) [nebezpečné](javascript:alert(1))\n```js\nconst x = 1\n```'} />);
  expect(screen.getByRole("link", { name: "Web" }).getAttribute("href")).toBe("https://example.com");
  expect(screen.queryByRole("link", { name: "nebezpečné" })).toBeNull();
  expect(screen.getByRole("region", { name: "js" }).className).toContain("bg-nested");
});

it("blok kódu čísluje řádky a kopíruje původní text", async () => {
  const text = '{"ok": true}\n42';
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<CodeBlock title="output.json" text={text} />);
  expect(screen.getByRole("region", { name: "output.json" }).querySelectorAll("tr")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Kopírovat" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(text));
});
