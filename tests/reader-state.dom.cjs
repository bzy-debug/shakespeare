'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, ResourceLoader, VirtualConsole} = require(process.env.JSDOM_MODULE || 'jsdom');
const root = path.resolve(__dirname, '..');
let delayOnce = '', failOnce = '';
class LocalResources extends ResourceLoader {
  fetch(url) {
    const request = new URL(url);
    if (request.origin !== 'http://reader.test') return null;
    const pathname = request.pathname.replace(/^\/shakespeare\//, '/');
    const file = path.resolve(root, '.' + decodeURIComponent(pathname));
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) return null;
    if (pathname === failOnce) { failOnce = ''; return Promise.reject(new Error('Test load failure')); }
    const bytes = fs.readFileSync(file);
    if (pathname === delayOnce) { delayOnce = ''; return new Promise(resolve => setTimeout(() => resolve(bytes), 180)); }
    return Promise.resolve(bytes);
  }
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, label) {
  for (let index = 0; index < 180; index++) { if (check()) return; await pause(20); }
  throw new Error('Timeout: ' + label);
}
function create(hash = '', storage = {}, page = 'index.html') {
  const errors = [], console = new VirtualConsole();
  console.on('jsdomError', error => { if (!error.message.includes('CSS') && !error.message.includes('Could not load script')) errors.push(error.message); });
  const dom = new JSDOM(fs.readFileSync(path.join(root, page), 'utf8'), {
    url: 'http://reader.test/shakespeare/' + page + hash,
    runScripts: 'dangerously', resources: new LocalResources(), pretendToBeVisual: true, virtualConsole: console,
    beforeParse(window) {
      window.scrollTo = () => {};
      window.HTMLElement.prototype.scrollIntoView = function () {};
      window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
      window.HTMLDialogElement.prototype.close = function () { this.open = false; };
      for (const [key, value] of Object.entries(storage)) window.localStorage.setItem(key, value);
      window.addEventListener('error', event => errors.push(event.message));
    }
  });
  return {dom, w: dom.window, d: dom.window.document, errors};
}
const click = (test, selector) => test.d.querySelector(selector).click();
function change(test, selector, value, type = 'change') {
  const element = test.d.querySelector(selector); element.value = value;
  element.dispatchEvent(new test.w.Event(type, {bubbles: true}));
}
async function ready(test, title = '') {
  await until(() => test.d.querySelector('#reading').getAttribute('aria-busy') === 'false' && test.d.querySelector('.english-unit') && test.d.title.includes(title), 'ready ' + title);
}
function finish(test) { assert.deepEqual(test.errors, []); test.dom.window.close(); }
(async () => {
  // Saved split-sentence bookmarks migrate to whole original block IDs. Removed
  // poem routes and stored poem bookmarks cannot leak back into the play shelf.
  const migration = create('#work=part0046', {
    'shakespeare.aligned.v1': JSON.stringify({work: 'part0046', fontSize: 24, theme: 'night', bookmarks: [
      {work: 'part0037', row: 'hamlet:1.1:2@0:12', section: '1.1', text: 'Old bookmark'},
      {work: 'part0046', row: 'removed-poem', section: '1', text: 'Removed poem'}
    ]})
  });
  await ready(migration, '哈姆莱特');
  assert.equal(migration.d.querySelector('#font-size').value, '24');
  assert.equal(migration.d.body.dataset.theme, 'night');
  assert.equal(migration.d.querySelector('#bookmark-count').textContent, '1');
  assert.equal(migration.d.querySelector('[data-bookmark="hamlet:1.1:2"]').getAttribute('aria-pressed'), 'true');
  click(migration, '#bookmarks-button'); click(migration, '[data-bookmark-index="0"]');
  await until(() => migration.d.querySelector('.english-unit.selected'), 'old bookmark destination');
  assert.equal(migration.d.querySelector('.english-unit.selected').dataset.row, 'hamlet:1.1:2');
  assert.ok(migration.w.location.hash.includes('row=hamlet%3A1.1%3A2'));
  const stored = migration.w.localStorage.getItem('shakespeare.reader.v2'); finish(migration);
  const resume = create('', {'shakespeare.reader.v2': stored}); await ready(resume, '哈姆莱特');
  assert.equal(resume.d.querySelector('.english-unit.selected').dataset.row, 'hamlet:1.1:2');
  click(resume, '#type-button'); change(resume, '#font-size', '26', 'input');
  click(resume, '[data-theme-choice="light"]'); click(resume, '[data-spacing="2.2"]');
  click(resume, '#type-dialog [data-close]'); change(resume, '#reading-mode', 'zh');
  assert.equal(resume.d.querySelector('#type-dialog').open, false);
  const settingsState = resume.w.localStorage.getItem('shakespeare.reader.v2'); finish(resume);
  const settings = create('', {'shakespeare.reader.v2': settingsState}); await ready(settings, '哈姆莱特');
  assert.equal(settings.d.body.dataset.theme, 'light'); assert.equal(settings.d.body.dataset.mode, 'zh');
  assert.equal(settings.d.querySelector('#font-size').value, '26');
  assert.equal(settings.d.documentElement.style.getPropertyValue('--leading'), '2.2');
  click(settings, '#type-button'); click(settings, '#reset-settings');
  assert.equal(settings.d.body.dataset.theme, 'paper'); assert.equal(settings.d.querySelector('#font-size').value, '20');
  assert.equal(settings.d.documentElement.style.getPropertyValue('--leading'), '1.9'); finish(settings);
  const corrupt = create('', {'shakespeare.reader.v2': '{invalid', 'shakespeare.aligned.v1': 'null'});
  await ready(corrupt, '哈姆莱特'); finish(corrupt);

  // Exercise default automatic matches, many-to-one groups, and pending blocks
  // with an in-memory fixture. Published source data is never modified.
  const grouped = create(); await ready(grouped, '哈姆莱特');
  const work = grouped.w.SHAKESPEARE_ALIGNED.hamlet;
  const rows = work.sections[0].rows;
  const first = work.groups.find(group => group.id === rows[1].groupId);
  first.status = 'automatically_aligned'; first.rowIds = [rows[1].id, rows[2].id];
  first.chineseText = '合并台词显示测试'; first.chineseHtml = '合并台词显示测试';
  rows[2].groupId = first.id; rows[3].groupId = null; rows[3].status = 'unresolved';
  change(grouped, '#aligned-section', '1.1');
  assert.equal(grouped.d.querySelectorAll('.automatically_aligned .english-unit').length, 2);
  assert.equal(grouped.d.querySelectorAll('.automatically_aligned .aligned-translation').length, 1);
  assert.ok(grouped.d.querySelector('.automatically_aligned .alignment-badge').textContent.includes('角色台词对应 · 合并台词段（2 段）'));
  assert.ok(grouped.d.querySelector('.alignment-pending'));
  change(grouped, '#reading-mode', 'zh');
  click(grouped, '.automatically_aligned .chinese-bookmark');
  assert.equal(grouped.d.querySelector('#bookmark-count').textContent, '1');
  assert.equal(grouped.d.querySelector('.automatically_aligned .chinese-bookmark').getAttribute('aria-pressed'), 'true');
  change(grouped, '#reading-mode', 'en'); click(grouped, '#search-button');
  change(grouped, '#search-input', '合并台词显示测试', 'input');
  assert.equal(grouped.d.querySelectorAll('#search-results .result').length, 1);
  assert.ok(grouped.d.querySelector('#search-results small').textContent.includes('合并台词显示测试'));
  click(grouped, '#search-results .result'); assert.equal(grouped.d.body.dataset.mode, 'parallel');
  grouped.w.innerWidth = 390; grouped.w.dispatchEvent(new grouped.w.Event('resize'));
  assert.equal(grouped.d.querySelector('#sidebar').inert, true); click(grouped, '#menu-button');
  assert.equal(grouped.d.querySelector('#sidebar').inert, false);
  assert.equal(grouped.d.querySelector('#menu-button').getAttribute('aria-expanded'), 'true');
  grouped.d.querySelector('#menu-button').focus();
  grouped.d.dispatchEvent(new grouped.w.KeyboardEvent('keydown', {key: 'Tab', bubbles: true, cancelable: true}));
  assert.equal(grouped.d.activeElement.id, 'library-button');
  grouped.d.dispatchEvent(new grouped.w.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  assert.equal(grouped.d.querySelector('#sidebar').inert, true);
  assert.equal(grouped.d.activeElement.id, 'menu-button'); finish(grouped);

  // Superseded lazy loads do not win over newer navigation; history dismisses
  // overlays and restores a whole-block destination, including old hash links.
  const race = create(); await ready(race, '哈姆莱特');
  delayOnce = '/data/aligned-collection/edwardiii.js';
  click(race, '#library-button'); click(race, '[data-work="part0041"]');
  click(race, '#library-button'); click(race, '[data-work="part0042"]'); await ready(race, '两位贵亲戚');
  await pause(250); assert.ok(race.d.title.includes('两位贵亲戚'));
  click(race, '#search-button'); race.w.history.back(); await ready(race, '哈姆莱特');
  assert.equal(race.d.querySelector('#search-dialog').open, false);
  race.w.history.forward(); await ready(race, '两位贵亲戚');
  race.w.location.hash = 'work=part0037&section=1.1&row=hamlet%3A1.1%3A2%400%3A12';
  await until(() => race.d.querySelector('.english-unit.selected')?.dataset.row === 'hamlet:1.1:2', 'legacy hash');
  assert.ok(!race.w.location.hash.includes('%40')); finish(race);
  failOnce = '/data/aligned-collection/edwardiii.js';
  const retry = create('#work=part0041'); await until(() => retry.d.querySelector('#load-status button'), 'retry');
  click(retry, '#load-status button'); await ready(retry, '爱德华三世'); finish(retry);
  // Source fallback retains authoritative English section and follows a real
  // paired Chinese block; it must not guess matching scene numbers.
  for (const [workId, title, sec] of [['part0010', '仲夏夜之梦', '2.1'], ['part0035', '麦克白', '5.8']]) {
    const main = create('#work=' + workId); await ready(main, title);
    change(main, '#aligned-section', sec);
    const href = new URL(main.d.querySelector('#source-reader-link').href);
    const params = new URLSearchParams(href.hash.slice(1)); assert.equal(params.get('en'), sec);
    assert.equal(new URL(main.d.querySelector('#source-note a[href*="source-reader.html"]').href).hash, href.hash);
    const source = create(href.hash, {}, 'source-reader.html');
    await until(() => source.d.querySelector('#reading').getAttribute('aria-busy') === 'false' && source.d.querySelector('#english-text .source-block'), 'source fallback');
    assert.equal(source.d.querySelector('#en-section').value, sec);
    const sourceWork = source.w.SHAKESPEARE_CHINESE[workId];
    const expected = sourceWork.sections.find(s => s.blocks.some(b => b.id === params.get('zhBlock')));
    assert.ok(expected); assert.equal(source.d.querySelector('#zh-section').value, expected.id);
    if (workId === 'part0035') assert.equal(expected.sceneNumber, 7);
    const back = new URL(source.d.querySelector('#aligned-reader-link').href);
    assert.equal(new URLSearchParams(back.hash.slice(1)).get('section'), sec);
    assert.equal(new URL(source.d.querySelector('#source-note a[href*="index.html"]').href).hash, back.hash);
    const restored = create(back.hash); await ready(restored, title); assert.equal(restored.d.querySelector('#aligned-section').value, sec);
    finish(restored); finish(source); finish(main);
  }
  console.log('PASS: main reader bookmark/settings migration, saved resume, settings persistence/reset, malformed state, automatic merged groups, Chinese-only bookmarks/search, mobile keyboard menu, stale-load race, history/hash destinations, retry, source fallback/return with edition-specific Chinese section mapping.');
})().catch(error => { console.error(error); process.exitCode = 1; });
