// Image inputs in the run form (api.md Uploads, 0.18.0): upload ids in the request, previews, removal.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FileInput, ValueInput } from "../components/form";
import { runInputs } from "../components/RunPanel";

const img = { upload_id: "up_1", name: "a.png", width: 4, height: 3, format: "png", url: "blob:a" };

afterEach(cleanup);  // the tests find the input by id — a previous render must not linger

/** The owner's side of `onChange` (RunPanel): a list is appended through an updater. */
function owner() {
  const box: { value: unknown } = { value: undefined };
  const onChange = vi.fn((v: unknown) => { box.value = typeof v === "function" ? v(box.value) : v; });
  return { box, onChange };
}

describe("image inputs", () => {
  it("runInputs sends upload ids for file and files, an empty files list means the default", () => {
    const specs = { photo: { type: "file", required: true }, refs: { type: "files", default: [] }, t: { type: "string", default: "x" } };
    expect(runInputs(specs, { photo: img, refs: [img, { ...img, upload_id: "up_2" }] })).toEqual({
      inputs: { photo: { upload_id: "up_1" }, refs: [{ upload_id: "up_1" }, { upload_id: "up_2" }] }, missing: [] });
    expect(runInputs(specs, { refs: [] })).toEqual({ inputs: {}, missing: ["photo"] });
  });

  it("FileInput uploads every picked image at once and reports them", async () => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    const upload = vi.fn(async (f: File) => ({ upload_id: `up_${f.name}`, format: "png", width: 4, height: 3, bytes: 10 }));
    const { box, onChange } = owner();
    render(<FileInput multiple value={undefined} onChange={onChange} upload={upload} a11y={{ id: "refs" }} />);
    const input = document.getElementById("refs") as HTMLInputElement;
    expect(input.accept).toContain("image/avif");
    fireEvent.change(input, { target: { files: [new File(["x"], "a.png", { type: "image/png" }), new File(["y"], "b.png", { type: "image/png" })] } });
    await waitFor(() => expect(onChange).toHaveBeenCalledOnce());
    expect(upload).toHaveBeenCalledTimes(2);
    expect(box.value).toEqual([
      expect.objectContaining({ upload_id: "up_a.png", name: "a.png", url: "blob:preview", width: 4 }),
      expect.objectContaining({ upload_id: "up_b.png" })]);
  });

  it("every failed upload is reported and none changes the value", async () => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    const onChange = vi.fn();
    render(<FileInput multiple value={undefined} onChange={onChange} upload={vi.fn(async (f: File) => { throw new Error(`too big (${f.name})`); })} a11y={{ id: "refs" }} />);
    fireEvent.change(document.getElementById("refs") as HTMLInputElement, { target: { files: [new File(["x"], "a.png"), new File(["y"], "b.png")] } });
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("b.png: upload failed — too big (b.png)"));
    expect(screen.getByRole("alert").textContent).toContain("a.png: upload failed — too big (a.png)");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("overlapping picks keep both files (the list is read when the upload finishes, not when picked)", async () => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    const pending: (() => void)[] = [];
    const upload = vi.fn((f: File) => new Promise<{ upload_id: string; format: string; width: number; height: number }>((resolve) =>
      pending.push(() => resolve({ upload_id: `up_${f.name}`, format: "png", width: 1, height: 1 }))));
    const { box, onChange } = owner();
    render(<FileInput multiple value={undefined} onChange={onChange} upload={upload} a11y={{ id: "refs" }} />);
    const input = document.getElementById("refs") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "a.png")] } });
    fireEvent.change(input, { target: { files: [new File(["y"], "b.png")] } });
    await waitFor(() => expect(pending).toHaveLength(2));
    pending[1]();  // the second pick finishes first
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    pending[0]();
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(2));
    expect((box.value as { name: string }[]).map((x) => x.name)).toEqual(["b.png", "a.png"]);  // nothing lost, never re-rendered
  });

  it("FileInput lists previews, removes one and revokes its preview URL", () => {
    URL.revokeObjectURL = vi.fn();
    const onChange = vi.fn();
    render(<FileInput multiple value={[img]} onChange={onChange} upload={vi.fn()} a11y={{ id: "refs" }} />);
    expect(screen.getByRole("img", { name: "a.png" })).toBeTruthy();
    expect(screen.getByText(/4×3 png/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove a.png" }));
    expect(onChange).toHaveBeenCalledWith(undefined);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:a");
    render(<ValueInput a11y={{ id: "photo" }} type="file" value={undefined} onChange={vi.fn()} upload={vi.fn()} />);
    expect((document.getElementById("photo") as HTMLInputElement).type).toBe("file");
  });
});
