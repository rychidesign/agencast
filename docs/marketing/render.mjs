import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from '../../ui/node_modules/playwright/index.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const checkOnly = process.argv.includes('--check');
const frames = process.argv.slice(2).find(arg => arg !== '--check') || await mkdtemp(path.join(tmpdir(), 'agencast-animation-'));
const fps = 20;
await mkdir(frames, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.join(here, 'agent-workflow.html')).href + '?export=1');
  await page.evaluate(() => document.fonts.ready);
  const seek = time => page.evaluate(value => window.agencastDemo.seek(value), time);
  await seek(6.9);
  assert.equal(await page.locator('#gate-validate').getAttribute('data-state'), 'error');
  await seek(8.6);
  assert.equal(await page.locator('#template-text').textContent(), '"{{ inputs.notes }}"');
  assert.equal(await page.locator('#gate-validate').getAttribute('data-state'), 'done');
  await seek(11.6);
  assert.equal(await page.locator('#gate-fake').getAttribute('data-state'), 'done');
  await seek(18.5);
  assert.equal(await page.locator('#runtime-status').textContent(), 'Succeeded');
  assert.equal(await page.locator('#brief-title').textContent(), 'Product release');
  await seek(24);
  assert.equal(await page.locator('#brief-title').textContent(), 'Customer onboarding');
  assert.equal(await page.locator('.file-head h2').textContent(), 'brief.yaml');
  await page.evaluate(() => document.body.classList.remove('export'));
  await page.locator('#play').click();
  assert.equal(await page.evaluate(() => window.agencastDemo.state().playing), true);
  await page.locator('#play').click();
  assert.equal(await page.evaluate(() => window.agencastDemo.state().playing), false);
  await page.locator('#seek').focus();
  await page.keyboard.press('Home');
  assert.equal(await page.evaluate(() => window.agencastDemo.state().time), 0);
  await page.evaluate(() => { document.body.classList.add('export'); scrollTo(0, 0); });

  const reduced = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  await reduced.goto(pathToFileURL(path.join(here, 'agent-workflow.html')).href);
  assert.equal(await reduced.evaluate(() => window.agencastDemo.state().playing), false);
  assert.equal(await reduced.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await reduced.close();
  assert.deepEqual(errors, []);
  if (checkOnly) {
    process.stdout.write(JSON.stringify({ frames, checks: 'validation, correction, reuse, controls and reduced motion passed' }) + '\n');
  } else {
    await seek(24);
    await page.locator('#stage').screenshot({ path: path.join(here, 'agent-workflow.png') });
    await page.screenshot({ path: path.join(frames, 'preview.png') });
    const duration = await page.evaluate(() => window.agencastDemo.duration);
    for (let frame = 0; frame < duration * fps; frame++) {
      await seek(frame / fps);
      await page.locator('#stage').screenshot({ path: path.join(frames, String(frame).padStart(5, '0') + '.png') });
      if (frame % (fps * 5) === 0) process.stdout.write('Rendered ' + frame / fps + ' / ' + duration + ' s\n');
    }
    const info = { frames, fps, duration, width: 1440, height: 900, checks: 'validation, correction, reuse, controls and reduced motion passed' };
    await writeFile(path.join(frames, 'render.json'), JSON.stringify(info, null, 2) + '\n');
    process.stdout.write(JSON.stringify(info) + '\n');
  }
} finally {
  await browser.close();
}
