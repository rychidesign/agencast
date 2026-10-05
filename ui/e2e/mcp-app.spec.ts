import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const card = readFileSync(path.resolve(import.meta.dirname, "../../framework/src/agencast/mcp_app/run-card.html"), "utf8");
const pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8AQAAAABJRU5ErkJggg==";
const queued: Record<string, any> = { project: "demo", run_id: "20261005-120000-demo-abcd", scenario: "demo", state: "queued", done: false,
  started_at: null, steps_done: null, steps_total: 3, outputs: null, output_files: {}, warnings: [] };

async function host(page: import("@playwright/test").Page, initial = queued) {
  await page.setContent(`<iframe title="run card"></iframe><script>
    window.run=${JSON.stringify(initial).replaceAll("<", "\\u003c")};window.calls=[];window.sent=[];
    const frame=document.querySelector('iframe');
    window.setRun=value=>window.run=value;window.teardown=()=>frame.contentWindow.postMessage({jsonrpc:'2.0',id:'bye',method:'ui/resource-teardown'},'*');
    window.addEventListener('message',event=>{if(event.source!==frame.contentWindow||event.data?.jsonrpc!=='2.0')return;const m=event.data;window.sent.push(m);
      if(m.method==='ui/initialize')event.source.postMessage({jsonrpc:'2.0',id:m.id,result:{protocolVersion:'2026-01-26',hostInfo:{name:'test',version:'1'},hostContext:{theme:'dark'}}},'*');
      if(m.method==='ui/notifications/initialized')event.source.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:window.run}},'*');
      if(m.method==='tools/call'){window.calls.push(m);const image=m.params.name==='get_run_file';event.source.postMessage({jsonrpc:'2.0',id:m.id,result:image?{content:[{type:'text',text:'{}'},{type:'image',mimeType:'image/png',data:'${pixel}'}],structuredContent:{kind:'image'}}:{content:[{type:'text',text:JSON.stringify(window.run)}],structuredContent:window.run}},'*');}
    });
  </script>`);
  await page.locator("iframe").evaluate((el, html) => { (el as HTMLIFrameElement).srcdoc = html; }, card);
  await page.waitForFunction(() => (window as any).sent.some((m: { method?: string }) => m.method === "ui/notifications/initialized"));
  return page.frames().find((frame) => frame !== page.mainFrame())!;
}

test("follows a run, renders its result, and stops after done", async ({ page }) => {
  const frame = await host(page);
  const running = { ...queued, state: "running", started_at: "2026-10-05T12:00:00Z", steps_done: 1, current_step: "write",
    steps: [{ step: "write", kind: "ask", status: "running", duration_s: null, cost_usd: null, error: null }] };
  await page.evaluate((value) => (window as any).setRun(value), running);
  await expect(frame.locator("#badge")).toHaveText("running");
  await expect(frame.locator("body")).toContainText("1 / 3 · write");
  const almost = { ...running, steps_done: 2, steps: [...running.steps, { step: "review", kind: "ask", status: "queued", duration_s: null, cost_usd: null, error: null }] };
  await page.evaluate((value) => (window as any).setRun(value), almost);
  await expect(frame.locator("body")).toContainText("2 / 3");
  const done = { ...almost, state: "succeeded", done: true, current_step: null, steps_done: 3, outputs: { text: "Hello from the fake", image: "file:///x/image.png" }, output_files: { image: "steps/02-image/image.png" }, warnings: ["one warning"], steps: almost.steps.map((step) => ({ ...step, status: "succeeded" })) };
  await page.evaluate((value) => (window as any).setRun(value), done);
  await expect(frame.locator("#badge")).toHaveText("succeeded");
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
  await page.evaluate((value) => (window as any).setRun(value), { ...queued, state: "failed", done: true,
    error: { class: "provider", step: "write", message: "model failed" } });
  await expect(frame.locator("#badge")).toHaveText("failed");
  await expect(frame.locator("#body")).toContainText("provider · write: model failed");
  const calls = await page.evaluate(() => (window as any).calls.length);
  await page.waitForTimeout(2_500);
  expect(await page.evaluate(() => (window as any).calls.length)).toBe(calls);
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
