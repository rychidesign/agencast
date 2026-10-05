import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const card = readFileSync(path.resolve(import.meta.dirname, "../../framework/src/agencast/mcp_app/run-card.html"), "utf8");
const pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8AQAAAABJRU5ErkJggg==";
const queued: Record<string, any> = { project: "demo", run_id: "20261005-120000-demo-abcd", scenario: "demo", state: "queued", done: false,
  started_at: null, steps_done: null, steps_total: 3, outputs: null, output_files: {}, warnings: [] };

async function host(page: import("@playwright/test").Page, initial = queued, refuse = false, polled?: Record<string, any>) {
  await page.setContent(`<iframe title="run card"></iframe><script>
    window.run=${JSON.stringify(initial).replaceAll("<", "\\u003c")};window.calls=[];window.sent=[];window.polled=${JSON.stringify(polled ?? null)};
    const frame=document.querySelector('iframe');
    window.setRun=value=>window.run=value;window.teardown=()=>frame.contentWindow.postMessage({jsonrpc:'2.0',id:'bye',method:'ui/resource-teardown'},'*');
    window.addEventListener('message',event=>{if(event.source!==frame.contentWindow||event.data?.jsonrpc!=='2.0')return;const m=event.data;window.sent.push(m);
      // as the ext-apps AppBridge: appCapabilities is a required param of ui/initialize
      if(m.method==='ui/initialize')event.source.postMessage(m.params?.appCapabilities&&!${refuse}?{jsonrpc:'2.0',id:m.id,result:{protocolVersion:'2026-01-26',hostInfo:{name:'test',version:'1'},hostContext:{theme:'dark'}}}:{jsonrpc:'2.0',id:m.id,error:{code:-32602,message:'Invalid params: appCapabilities is required'}},'*');
      if(m.method==='ui/notifications/initialized'){event.source.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:window.run}},'*');if(window.polled)window.run=window.polled;}
      if(m.method==='tools/call'){window.calls.push(m);const image=m.params.name==='get_run_file';event.source.postMessage({jsonrpc:'2.0',id:m.id,result:window.fail?{isError:true,content:[{type:'text',text:window.fail}]}:image?{content:[{type:'text',text:'{}'},{type:'image',mimeType:'image/png',data:'${pixel}'}],structuredContent:{kind:'image'}}:{content:[{type:'text',text:JSON.stringify(window.run)}],structuredContent:window.run}},'*');}
    });
  </script>`);
  await page.locator("iframe").evaluate((el, html) => { (el as HTMLIFrameElement).srcdoc = html; }, card);
  await page.waitForFunction((method) => (window as any).sent.some((m: { method?: string }) => m.method === method),
    refuse ? "ui/initialize" : "ui/notifications/initialized");
  return page.frames().find((frame) => frame !== page.mainFrame())!;
}

test("follows a run, renders its result, and stops after done", async ({ page }) => {
  const frame = await host(page);
  const running = { ...queued, state: "running", started_at: "2026-10-05T12:00:00Z", steps_done: 1, current_step: "write",
    steps: [{ step: "write", kind: "ask", status: "running", duration_s: null, cost_usd: null, error: null }] };
  await page.evaluate((value) => (window as any).setRun(value), running);
  await expect(frame.locator("#badge")).toHaveText("running");
  await expect(frame.locator("#progress")).toContainText("1 / 3 steps · write");
  await expect(frame.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  await expect(frame.getByRole("progressbar").locator(".segment")).toHaveCount(3);
  const almost = { ...running, steps_done: 2, steps: [...running.steps, { step: "review", kind: "ask", status: "queued", duration_s: null, cost_usd: null, error: null }] };
  await page.evaluate((value) => (window as any).setRun(value), almost);
  await expect(frame.locator("#progress")).toContainText("2 / 3");
  await expect(frame.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
  // steps_done is null once the run has finished (spec “The run object”): the card counts the steps that ran
  const done = { ...almost, state: "succeeded", done: true, current_step: null, steps_done: null, outputs: { text: "Hello from the fake", image: "file:///x/image.png" }, output_files: { image: "steps/02-image/image.png" }, warnings: ["one warning"], steps: almost.steps.map((step) => ({ ...step, status: "succeeded" })) };
  await page.evaluate((value) => (window as any).setRun(value), done);
  await expect(frame.locator("#badge")).toHaveText("succeeded");
  await expect(frame.getByRole("progressbar")).toHaveAttribute("data-state", "succeeded");
  await expect(frame.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
  await expect(frame.locator("#progress")).toContainText("2 / 3");
  await expect(frame.locator("body")).toContainText("Hello from the fake");
  await expect(frame.locator("body")).toContainText("one warning");
  await expect(frame.locator("img")).toHaveAttribute("src", /^data:image\/png;base64,/);
  expect(await page.evaluate(() => (window as any).sent.some((m: { method?: string }) => m.method === "ui/notifications/size-changed"))).toBe(true);
  const calls = await page.evaluate(() => (window as any).calls.length);
  await page.waitForTimeout(5_000);
  expect(await page.evaluate(() => (window as any).calls.length)).toBe(calls);
});

test("shows a failed run and stops polling", async ({ page }) => {
  const frame = await host(page);
  const step = (step: string, status: string, kind = "ask") => ({ step, kind, status, duration_s: null, cost_usd: null, error: null });
  const started_at = "2026-10-05T12:00:00Z";
  await page.evaluate((value) => (window as any).setRun(value), { ...queued, state: "running", started_at, steps_done: 1, current_step: "review",
    steps: [step("draft", "succeeded"), step("review", "running", "call")] });
  await expect(frame.locator("#progress")).toContainText("1 / 3 steps · review");
  // the run moved on between two polls: the bar follows steps[] (main-scenario steps only), not the last poll's fills
  await page.evaluate((value) => (window as any).setRun(value), { ...queued, state: "failed", done: true, started_at,
    steps: [step("draft", "succeeded"), step("review", "succeeded", "call"), step("review/check", "succeeded"), step("write", "failed")],
    error: { class: "provider", step: "write", message: "model failed" } });
  await expect(frame.locator("#badge")).toHaveText("failed");
  await expect(frame.locator("#body")).toContainText("provider · write: model failed");
  await expect(frame.locator("#progress")).toHaveText("2 / 3 steps");
  await expect(frame.locator(".segment[data-fill=failed]")).toHaveCount(1);
  await expect(frame.locator(".segment").nth(2)).toHaveAttribute("data-fill", "failed");
  const calls = await page.evaluate(() => (window as any).calls.length);
  await page.waitForTimeout(2_500);
  expect(await page.evaluate(() => (window as any).calls.length)).toBe(calls);
});

test("keeps still with reduced motion, and stops moving when a poll fails", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const frame = await host(page);
  const animations = () => frame.evaluate(() => document.getAnimations().length);
  await expect(frame.locator("#badge")).toHaveText("queued");
  // a static queued bar is the empty track, not a block that reads as progress
  expect(await frame.evaluate(() => [...document.querySelectorAll("#bar, #bar *")].every((el) => getComputedStyle(el, "::after").content === "none"))).toBe(true);
  await page.evaluate((value) => (window as any).setRun(value), { ...queued, state: "running", started_at: "2026-10-05T12:00:00Z", steps_done: 1, current_step: "write",
    steps: [{ step: "write", kind: "ask", status: "running", duration_s: null, cost_usd: null, error: null }] });
  await expect(frame.locator("#badge")).toHaveText("running");
  expect(await animations()).toBe(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect.poll(animations).toBeGreaterThan(0);  // the running pulse and the sheen
  await page.evaluate(() => { (window as any).fail = "not_found: gone"; });
  await expect(frame.locator("#problem")).toHaveText("not_found: gone");
  await expect.poll(animations).toBe(0);
});

test("glows once when a queued run has succeeded by the next poll", async ({ page }) => {
  const frame = await host(page);
  await expect(frame.locator("#badge")).toHaveText("queued");
  await frame.evaluate(() => { (window as any).started = []; document.querySelector("#bar")!.addEventListener("animationstart", (e) => (window as any).started.push((e as AnimationEvent).animationName)); });
  await page.evaluate((value) => (window as any).setRun(value), { ...queued, state: "succeeded", done: true, outputs: {} });
  await expect.poll(() => frame.evaluate(() => (window as any).started)).toContain("glow");
});

test("answers teardown and makes no later tool calls", async ({ page }) => {
  await host(page);
  await page.evaluate(() => (window as any).teardown());
  await expect.poll(() => page.evaluate(() => (window as any).sent.some((m: { id?: string; result?: object }) => m.id === "bye" && !!m.result))).toBe(true);
  await page.waitForTimeout(2_500);
  expect(await page.evaluate(() => (window as any).calls.length)).toBe(0);
});

test("renders hostile result text as text", async ({ page }) => {
  const attack = "<img src=x onerror=window.pwned=1>";
  const frame = await host(page, { ...queued, scenario: attack, done: true, state: "succeeded", outputs: {}, output_files: {} });
  await expect(frame.locator("#summary")).toContainText(attack);
  expect(await frame.evaluate(() => (window as Window & { pwned?: number }).pwned)).toBeUndefined();
});

test("shows the host's refusal to initialize", async ({ page }) => {
  const frame = await host(page, queued, true);
  await expect(frame.locator("#problem")).toHaveText("Invalid params: appCapabilities is required");
  expect(await page.evaluate(() => (window as any).sent.some((m: { method?: string }) => m.method === "ui/notifications/initialized"))).toBe(false);
});

test("keeps the AgenCast dark palette for dark and light hosts", async ({ page }) => {
  const frame = await host(page);  // the host says dark, the browser prefers light
  const background = () => frame.evaluate(() => getComputedStyle(document.documentElement).backgroundColor);
  await expect.poll(background).toBe("rgb(23, 36, 54)");
  await page.evaluate(() => document.querySelector("iframe")!.contentWindow!.postMessage(
    { jsonrpc: "2.0", method: "ui/notifications/host-context-changed", params: { theme: "light" } }, "*"));
  await frame.evaluate(() => new Promise<number>((resolve) => requestAnimationFrame(resolve)));
  await expect.poll(background).toBe("rgb(23, 36, 54)");
});

test("shows file outputs when outputs are too large, fetching only the images", async ({ page }) => {
  const frame = await host(page, { ...queued, state: "succeeded", done: true, started_at: "2026-10-05T12:00:00Z", duration_s: 42,
    outputs: null, outputs_file: "callback.json", output_files: { "gallery-1": "steps/01-shots/image-1.png",
      "gallery-2": "steps/01-shots/image-2.png", notes: "steps/02-notes/notes.md" } });
  await expect(frame.locator("img")).toHaveCount(2);
  await expect(frame.locator("#elapsed")).toHaveText("Elapsed: 42s");
  await expect(frame.locator("#body")).toContainText("read callback.json");
  await expect(frame.locator("#body")).toContainText("notes: steps/02-notes/notes.md");
  expect(await page.evaluate(() => (window as any).calls.filter((m: any) => m.params.name === "get_run_file").map((m: any) => m.params.arguments.path)))
    .toEqual(["steps/01-shots/image-1.png", "steps/01-shots/image-2.png"]);
});

test("fetches the steps once for a finished run handed over without detail", async ({ page }) => {
  // run_status without detail: true on a finished run — the card is done at once but has no steps[] yet
  const finished = { ...queued, state: "failed", done: true, started_at: "2026-10-05T12:00:00Z", duration_s: 0.4, cost_usd: 0.0002,
    error: { class: "fail", step: "stop", message: "not on brand" } };
  const detail = { ...finished, steps: [
    { step: "copy", kind: "ask", status: "succeeded", duration_s: 0.1, cost_usd: 0.0001, error: null },
    { step: "tone_check", kind: "jev", status: "succeeded", duration_s: 0.1, cost_usd: 0.0001, error: null },
    { step: "stop", kind: "fail", status: "failed", duration_s: 0, cost_usd: 0, error: { class: "fail", message: "not on brand" } }] };
  const frame = await host(page, finished, false, detail);
  await expect(frame.locator("#progress")).toContainText("2 / 3 steps");
  await expect(frame.locator(".segment[data-fill=failed]")).toHaveCount(1);
  await expect(frame.locator("body")).toContainText("tone_check");
  await page.waitForTimeout(3000);
  const statusCalls = await page.evaluate(() => (window as any).calls.filter((m: any) => m.params.name === "run_status"));
  expect(statusCalls).toHaveLength(1);
  expect(statusCalls[0].params.arguments.detail).toBe(true);
});
