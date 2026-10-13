import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from '../../ui/node_modules/playwright/index.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const checkOnly = process.argv.includes('--check');
const frames = process.argv.slice(2).find(arg => arg !== '--check') || await mkdtemp(path.join(tmpdir(), 'agencast-camera-'));
const fps = 30;
await mkdir(frames, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [], network = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
  const url = pathToFileURL(path.join(here, 'agent-workflow-camera.html')).href;
  await page.goto(url + '?export=1');
  await page.evaluate(() => document.fonts.ready);
  const seek = time => page.evaluate(value => window.agencastDemo.seek(value), time);
  const state = () => page.evaluate(() => window.agencastDemo.state());
  const snapshot = async (time, name) => {
    await seek(time);
    await page.locator('#stage').screenshot({ path: path.join(frames, name + '.png') });
  };

  await seek(2.9);
  assert.equal((await state()).foreground, 0);
  const frontWidth = (await page.locator('#request-card').boundingBox()).width;
  await seek(3.44);
  assert.ok((await page.locator('#request-card').boundingBox()).width > frontWidth);
  assert.ok(await page.locator('#request-card').evaluate(el => parseFloat(el.style.filter.match(/[\d.]+/)[0]) > 0 && Number(el.style.opacity) < 1));
  await seek(6.6);
  assert.equal((await state()).foreground, 1);
  assert.ok((await page.locator('#scenario-code').textContent()).includes('input.topic'));
  await seek(8.7);
  assert.equal((await state()).foreground, 2);
  assert.equal(await page.locator('#preflight').getAttribute('data-state'), 'error');
  assert.equal(await page.locator('#node-0 .node-label').textContent(), 'waiting');
  await seek(11.1);
  assert.equal((await state()).foreground, 1);
  assert.ok((await page.locator('.code-line.fixed').textContent()).includes('inputs.topic'));
  const declaredCalls = await page.locator('.code-text').evaluateAll(els => els.map(el => el.textContent.trim()).filter(line => line.startsWith('scenario:')).map(line => line.slice(9).trim()).sort());
  const drawnCalls = await page.locator('.wire[data-from="ig-post"]').evaluateAll(els => els.map(el => el.dataset.to).sort());
  assert.deepEqual(declaredCalls, ['ig-caption', 'ig-image']);
  assert.deepEqual(drawnCalls, declaredCalls);
  await seek(14.8);
  assert.equal((await state()).foreground, 2);
  assert.equal(await page.locator('#node-0').getAttribute('data-state'), 'done');
  assert.equal(await page.locator('#node-1').getAttribute('data-state'), 'running');
  await seek(17.5);
  assert.equal(await page.locator('#runtime-status').textContent(), 'Succeeded');
  await seek(18.7);
  assert.equal(await page.locator('#request-card').evaluate(el => getComputedStyle(el).visibility), 'hidden');
  assert.equal(await page.locator('#yaml-card').evaluate(el => getComputedStyle(el).visibility), 'hidden');
  assert.ok(await page.locator('#runtime-card').evaluate(el => !el.style.transform.includes('rotate')));
  await seek(19.2);
  const smallRun = await page.locator('#runtime-card').boundingBox();
  const scenario = await page.locator('#scenario-ig-post').boundingBox();
  for (const key of ['x', 'y', 'width', 'height']) assert.ok(Math.abs(smallRun[key] - scenario[key]) < .5, 'one aligned card during the morph: ' + key);
  await seek(31);
  assert.equal((await state()).foreground, 3);
  assert.equal(await page.locator('.map-node').count(), 9);
  assert.ok(await page.locator('.map-node').evaluateAll(els => els.every(el => Number(el.style.opacity) === 1)));
  assert.ok(await page.locator('.connection').evaluateAll(els => els.every(el => Number(el.style.strokeDashoffset) === 0)));
  assert.equal(await page.locator('#runtime-card').evaluate(el => getComputedStyle(el).visibility), 'hidden');
  const geometry = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.map-node')].map(el => ({ name: el.dataset.scenario, x: Number(el.dataset.x)-el.offsetWidth/2, y: Number(el.dataset.y)-el.offsetHeight/2, width: el.offsetWidth, height: el.offsetHeight, before: getComputedStyle(el, '::before').content }));
    const paths = [...document.querySelectorAll('.connection')].map(el => { const length = el.getTotalLength(); return Array.from({length:201}, (_, i) => { const p=el.getPointAtLength(length*i/200);return {x:p.x,y:p.y}; }); });
    return {cards,paths,ovals:document.querySelectorAll('.orbit').length};
  });
  assert.equal(geometry.ovals, 0);
  assert.ok(geometry.cards.every(card => card.width === 220 && card.height === 112 && card.before === 'none'));
  assert.equal(new Set(geometry.cards.map(card => card.x)).size, 3);
  assert.equal(new Set(geometry.cards.map(card => card.y)).size, 3);
  for (const points of geometry.paths) for (const point of points) for (const card of geometry.cards) {
    assert.ok(!(point.x > card.x+.1 && point.x < card.x+card.width-.1 && point.y > card.y+.1 && point.y < card.y+card.height-.1), 'call line avoids ' + card.name);
  }
  const cross = (a,b,c) => (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  for (let i=0;i<geometry.paths.length;i++) for (let j=i+1;j<geometry.paths.length;j++) {
    const a=geometry.paths[i], b=geometry.paths[j];
    for (let m=1;m<a.length;m++) for (let n=1;n<b.length;n++) assert.ok(!(cross(a[m-1],a[m],b[n-1])*cross(a[m-1],a[m],b[n])<0 && cross(b[n-1],b[n],a[m-1])*cross(b[n-1],b[n],a[m])<0), 'call lines do not cross');
  }
  for (const [before,after,index] of [[20.69,20.83,0],[21.04,21.18,1],[21.09,21.23,2]]) {
    await seek(before); assert.equal(await page.locator('.edge-arrow').nth(index).evaluate(el => Number(el.style.opacity)), 0);
    await seek(after); assert.equal(await page.locator('.edge-arrow').nth(index).evaluate(el => Number(el.style.opacity)), 1);
  }
  await seek(25.5);
  assert.equal(await page.locator('#scenario-ig-post').getAttribute('data-state'), 'running');
  assert.equal(await page.locator('#scenario-ig-caption').getAttribute('data-state'), 'running');
  assert.equal(await page.locator('#scenario-ig-image').getAttribute('data-state'), 'ready');
  await seek(27.5);
  assert.equal(await page.locator('#scenario-ig-caption').getAttribute('data-state'), 'done');
  assert.equal(await page.locator('#scenario-ig-image').getAttribute('data-state'), 'running');
  await seek(31);
  for (const name of ['ig-post','ig-caption','ig-image']) assert.equal(await page.locator('#scenario-'+name).getAttribute('data-state'), 'done');
  for (const boundary of [3.1,3.78,7.1,7.78,9.05,9.75,11.45,12.13]) {
    await seek(boundary - .001); const before = (await state()).camera;
    await seek(boundary + .001); const after = (await state()).camera;
    assert.ok(Math.abs(after - before) < .01, 'camera stays continuous at ' + boundary);
  }

  await page.evaluate(() => document.body.classList.remove('export'));
  await page.getByRole('button', { name: 'Correction', exact: true }).click();
  assert.equal((await state()).time, 11.1);
  assert.equal((await state()).playing, false);
  await page.locator('#play').click(); assert.equal((await state()).playing, true);
  await page.locator('#play').click(); assert.equal((await state()).playing, false);
  await page.locator('#seek').focus(); await page.keyboard.press('Home');
  assert.equal((await state()).time, 0);
  await page.evaluate(() => { document.body.classList.add('export'); scrollTo(0, 0); });

  const reduced = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  await reduced.goto(url);
  assert.equal(await reduced.evaluate(() => window.agencastDemo.state().playing), false);
  assert.equal(await reduced.evaluate(() => window.agencastDemo.state().foreground), 3);
  assert.equal(await reduced.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await reduced.evaluate(() => window.agencastDemo.seek(2.9));
  const mobileCard = await reduced.locator('#request-card').boundingBox();
  assert.ok(mobileCard.x >= 0 && mobileCard.x + mobileCard.width <= 390);
  await reduced.locator('#stage').screenshot({ path: path.join(frames, 'mobile.png') });
  await reduced.close();
  assert.deepEqual(errors, []); assert.deepEqual(network, []);
  for (const [time, name] of [[2.9,'request'],[3.44,'flight'],[6.6,'yaml'],[8.7,'error'],[11.1,'correction'],[14.8,'run'],[17.5,'success'],[18.7,'pullback'],[22.3,'grid'],[25.5,'caption-call'],[27.5,'image-call'],[31,'network']]) await snapshot(time,name);
  if (checkOnly) {
    process.stdout.write(JSON.stringify({ frames, checks: 'camera, validation return, correction, run, connections, controls, reduced motion and mobile passed' }) + '\n');
  } else {
    await seek(31);
    await page.locator('#stage').screenshot({ path: path.join(here, 'agent-workflow-camera.png') });
    const duration = await page.evaluate(() => window.agencastDemo.duration);
    for (let frame = 0; frame < duration * fps; frame++) {
      await seek(frame / fps);
      await page.locator('#stage').screenshot({ path: path.join(frames, String(frame).padStart(5, '0') + '.png') });
      if (frame % (fps * 3) === 0) process.stdout.write('Rendered ' + frame / fps + ' / ' + duration + ' s\n');
    }
    const info = { frames, fps, duration, width: 1440, height: 900, checks: 'camera, repair loop, run, network and playback passed' };
    await writeFile(path.join(frames, 'render.json'), JSON.stringify(info, null, 2) + '\n');
    process.stdout.write(JSON.stringify(info) + '\n');
  }
} finally {
  await browser.close();
}
