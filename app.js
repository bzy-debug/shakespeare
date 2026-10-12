'use strict';
(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const catalog = (window.SHAKESPEARE_CHINESE_CATALOG || []).filter(item => item.kind === 'play');
  const englishCatalog = (window.SHAKESPEARE_ENGLISH_CATALOG || []).filter(item => item.kind === 'play');
  const alignedCatalog = window.SHAKESPEARE_ALIGNED_CATALOG || [];
  const storageKey = 'shakespeare.reader.v2';
  const readSaved = key => {
    try {
      const value = JSON.parse(localStorage.getItem(key));
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch { return {}; }
  };
  const legacy = readSaved('shakespeare.collection.v1');
  const saved = {...legacy, ...readSaved('shakespeare.aligned.v1'), ...readSaved(storageKey)};
  const workExists = id => catalog.some(item => item.id === id);
  const state = {
    work: workExists(saved.work) ? saved.work : 'part0037',
    englishWork: '', section: '', row: '',
    mode: ['parallel', 'en', 'zh'].includes(saved.mode) ? saved.mode : 'parallel',
    fontSize: Number.isFinite(Number(saved.fontSize)) ? Math.max(16, Math.min(28, Number(saved.fontSize))) : 20,
    theme: ['paper', 'light', 'night'].includes(saved.theme) ? saved.theme : 'paper',
    spacing: ['1.65', '1.9', '2.2'].includes(String(saved.spacing)) ? String(saved.spacing) : '1.9',
    bookmarks: Array.isArray(saved.bookmarks) ? saved.bookmarks.filter(mark => mark && workExists(mark.work) && typeof mark.row === 'string' && typeof mark.section === 'string').slice(0, 2000) : [],
    positions: saved.positions && typeof saved.positions === 'object' && !Array.isArray(saved.positions) ? saved.positions : {}
  };
  let work = null, meta = null, generation = 0, toastTimer, positionTimer, progressFrame;
  let groupMap = new Map(), rowMap = new Map(), lastRoute = '', restoringPosition = false;
  const scripts = new Map();
  const current = () => work?.sections.find(section => section.id === state.section);
  const englishId = item => item.englishId || item.englishIds?.[0];
  const canDisplay = group => group && ['automatically_aligned', 'semantically_reviewed'].includes(group.status);
  const persist = () => { try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch {} };
  const bookmarkIndex = row => state.bookmarks.findIndex(mark => mark.work === state.work && normalizeRow(mark.row) === row.id);
  const normalizeRow = id => String(id || '').replace(/@\d+:\d+$/, '');
  function toast(message) {
    $('#toast').textContent = message;
    $('#toast').classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 2200);
  }
  function loadScript(path) {
    if (!scripts.has(path)) {
      scripts.set(path, new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = path;
        script.onload = resolve;
        script.onerror = () => {
          scripts.delete(path);
          script.remove();
          reject(new Error('作品数据未能载入，请检查网络后重试'));
        };
        document.head.append(script);
      }));
    }
    return scripts.get(path);
  }
  function applySettings() {
    document.documentElement.style.setProperty('--font-size', state.fontSize + 'px');
    document.documentElement.style.setProperty('--leading', state.spacing);
    document.body.dataset.mode = state.mode;
    document.body.dataset.theme = state.theme;
    $('#font-size').value = state.fontSize;
    $('#font-output').value = state.fontSize + ' px';
    $('#reading-mode').value = state.mode;
    $$('[data-theme-choice]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === state.theme)));
    $$('[data-spacing]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.spacing === state.spacing)));
    requestAnimationFrame(updateProgress);
  }
  function route() {
    const params = new URLSearchParams(location.hash.slice(1));
    return {
      work: params.get('work'), englishWork: params.get('englishWork'),
      section: params.get('section') || params.get('en'),
      row: params.get('row') || (params.get('lang') === 'en' ? params.get('block') : null)
    };
  }
  function setURL(replace = false) {
    const params = new URLSearchParams({work: state.work, englishWork: state.englishWork, section: state.section});
    if (state.row) params.set('row', state.row);
    const hash = '#' + params;
    if (location.hash !== hash) history[replace ? 'replaceState' : 'pushState'](null, '', hash);
    lastRoute = location.hash;
  }
  function rememberPosition(row = state.row) {
    if (!work || !current()) return;
    state.positions[state.englishWork] = {section: state.section, row: row || ''};
    persist();
  }
  function sourceURL(anchor) {
    const params = new URLSearchParams({work: state.work, englishWork: state.englishWork});
    if (anchor) params.set('anchor', anchor);
    return 'source-reader.html#' + params;
  }
  function setMetadata(item, english) {
    $('.book-title h2').textContent = english?.title || item.title;
    $('.book-title p').textContent = item.title;
    $('.book-title .eyebrow').textContent = 'THE PLAYS';
    $('#play-title').textContent = english?.title || item.title;
    $('.hero-copy > .eyebrow').textContent = 'THE COMPLETE PLAYS';
    $('.hero-subtitle > span').textContent = item.title;
    $('.author').textContent = 'William Shakespeare';
    $('.breadcrumb').textContent = '戏剧 / ' + item.title;
    document.title = item.title + ' · 中英台词对照';
    const credit = item.translatorCredit || item.translator || '译者署名待核实';
    $('#edition-note').textContent = '中文：' + credit + ' · 人民文学出版社 2014 纪念版' + (item.attributionStatus === 'source-credit-uncertain' ? '（原书署名待核实）' : '');
    $('#source-reader-link').href = sourceURL();
    const source = work?.source || english || {};
    $('#source-note').innerHTML = '英文：<a href="' + esc(source.sourceUrl || english?.sourceUrl || 'https://shakespeare.mit.edu/') + '" target="_blank" rel="noopener noreferrer">' + esc(source.sourceLabel || english?.sourceLabel || '英文公版来源') + '</a>。中文按原版台词段引用，保留各剧译者署名。<br>角色台词对应为程序匹配，尚未经逐段人工复核；已语义核对另行标示。未确定的对应保留待核标记。<br>中文书前材料与注释可在<a href="' + sourceURL() + '">原始底本参考</a>中查阅。';
  }
  async function openWork(id, options = {}) {
    const item = catalog.find(entry => entry.id === id) || catalog.find(entry => entry.id === 'part0037') || catalog[0];
    if (!item) { $('#load-status').textContent = '戏剧目录未能载入，请刷新重试。'; return; }
    const ticket = ++generation;
    clearTimeout(positionTimer);
    restoringPosition = true;
    work = null; meta = item; groupMap = new Map(); rowMap = new Map();
    state.work = item.id; state.englishWork = englishId(item); state.section = ''; state.row = '';
    const english = englishCatalog.find(entry => entry.id === state.englishWork);
    setMetadata(item, english);
    menu(false);
    $('#reading').setAttribute('aria-busy', 'true');
    $('#load-status').textContent = '正在载入《' + item.title + '》…';
    $('#aligned-text').replaceChildren(); $('#work-toc').replaceChildren(); $('#aligned-section').replaceChildren();
    $('#alignment-counts').textContent = ''; $('#footer-section').textContent = '载入作品'; $('#section-end-label').textContent = '';
    $('#aligned-prev').disabled = true; $('#aligned-next').disabled = true; $('#aligned-section').disabled = true;
    try {
      const summary = alignedCatalog.find(entry => entry.id === state.englishWork);
      if (!summary?.file) throw new Error('这部戏剧的对照数据尚未准备');
      await loadScript(summary.file);
      if (ticket !== generation) return;
      const loaded = window.SHAKESPEARE_ALIGNED?.[state.englishWork];
      if (!loaded?.sections?.length) throw new Error('作品数据没有有效篇章');
      work = loaded;
      groupMap = new Map((work.groups || []).map(group => [group.id, group]));
      for (const section of work.sections) for (const row of section.rows) {
        rowMap.set(row.id, {row, section});
        if (!rowMap.has(row.english.blockId)) rowMap.set(row.english.blockId, {row, section});
      }
      const previous = state.positions[state.englishWork];
      const previousSection = typeof previous === 'string' ? previous : previous?.section;
      const requestedRow = options.row && (rowMap.get(options.row) || rowMap.get(normalizeRow(options.row)));
      state.section = requestedRow?.section.id || (work.sections.some(section => section.id === options.section) ? options.section : work.sections.some(section => section.id === previousSection) ? previousSection : work.sections[0].id);
      const restoreRow = options.row || ((!options.section || options.section === previousSection) ? previous?.row : '');
      setMetadata(item, english);
      $('#load-status').textContent = '';
      render();
      if (restoreRow) selectRow(restoreRow, {reveal: Boolean(options.row)});
      else window.scrollTo({top: 0, behavior: 'instant'});
      setURL(Boolean(options.replace)); rememberPosition();
    } catch (error) {
      if (ticket !== generation) return;
      $('#load-status').textContent = error.message + '。';
      const retry = document.createElement('button'); retry.textContent = '重试';
      retry.onclick = () => openWork(item.id, {...options, replace: true});
      $('#load-status').append(' ', retry);
    } finally {
      if (ticket === generation) {
        $('#reading').setAttribute('aria-busy', 'false');
        requestAnimationFrame(() => { if (ticket === generation) restoringPosition = false; });
      }
    }
  }
  function bookmarkButton(row, extraClass = '') {
    const marked = bookmarkIndex(row) >= 0;
    return '<button class="block-bookmark aligned-bookmark ' + extraClass + '" aria-label="' + (marked ? '取消书签' : '添加书签') + '" title="' + (marked ? '取消书签' : '添加书签') + '" aria-pressed="' + marked + '" data-bookmark="' + esc(row.id) + '">' + (marked ? '◆' : '◇') + '</button>';
  }
  function render() {
    const section = current(); if (!section) return;
    const seen = new Set(); let html = '';
    for (let index = 0; index < section.rows.length;) {
      const first = section.rows[index], group = groupMap.get(first.groupId), visible = canDisplay(group), chunk = [first];
      let next = index + 1;
      if (visible) while (next < section.rows.length && section.rows[next].groupId === first.groupId) chunk.push(section.rows[next++]);
      const used = visible && seen.has(group.id); if (visible) seen.add(group.id);
      const status = visible ? group.status : 'unresolved';
      const count = group?.rowIds?.length || chunk.length;
      html += '<article class="aligned-group ' + status + '"' + (group ? ' data-group="' + esc(group.id) + '"' : '') + '><div class="aligned-en" lang="en">';
      html += chunk.map(row => '<div class="english-unit ' + (row.kind === 'stage' ? 'stage-unit' : '') + '" tabindex="0" data-row="' + esc(row.id) + '">' + (row.speaker ? '<h3 class="speaker">' + esc(row.speaker) + '</h3>' : '') + '<p>' + esc(row.english.text) + '</p>' + bookmarkButton(row) + '</div>').join('');
      html += '</div><div class="aligned-zh" lang="zh-CN" data-translation-row="' + esc(first.id) + '">' + bookmarkButton(first, 'chinese-bookmark');
      if (!visible) html += '<p class="alignment-pending">' + (first.kind === 'stage' ? '舞台提示对应译文待核对' : '对应译文待核对') + '</p>';
      else if (used) html += '<p class="shared-translation"><button data-shared="' + esc(group.rowIds?.[0] || first.id) + '">↥ 查看前面的合并台词段译文</button></p>';
      else html += '<p class="alignment-badge">' + (status === 'semantically_reviewed' ? '已语义核对' : first.kind === 'stage' ? '舞台提示对应' : '角色台词对应') + (count > 1 ? ' · 合并台词段（' + count + ' 段）' : '') + '</p><div class="aligned-translation">' + group.chineseHtml + '</div>';
      html += '</div></article>'; index = next;
    }
    $('#aligned-text').innerHTML = html;
    const reviewed = section.rows.filter(row => groupMap.get(row.groupId)?.status === 'semantically_reviewed').length;
    const automatic = section.rows.filter(row => groupMap.get(row.groupId)?.status === 'automatically_aligned').length;
    $('#alignment-counts').textContent = '本节 ' + section.rows.length + ' 段 · 自动对应 ' + automatic + ' · 已语义核对 ' + reviewed + ' · 待核 ' + (section.rows.length - reviewed - automatic);
    $('#aligned-section').innerHTML = work.sections.map(entry => '<option value="' + esc(entry.id) + '"' + (entry.id === state.section ? ' selected' : '') + '>' + esc(entry.label) + '</option>').join('');
    $('#aligned-section').disabled = false;
    const at = work.sections.indexOf(section);
    $('#aligned-prev').disabled = at === 0; $('#aligned-next').disabled = at === work.sections.length - 1;
    $('#work-toc').innerHTML = work.sections.map(entry => '<button data-section="' + esc(entry.id) + '" class="' + (entry.id === state.section ? 'scene-current' : '') + '"' + (entry.id === state.section ? ' aria-current="page"' : '') + '>' + esc(entry.label) + '</button>').join('');
    $('.breadcrumb').textContent = '戏剧 / ' + meta.title + ' / ' + section.label;
    $('#footer-section').textContent = section.label; $('#section-end-label').textContent = section.label + ' · 本节终';
    updateBookmarks(); applySettings();
  }
  function changeSection(id, options = {}) {
    if (!work?.sections.some(section => section.id === id)) return;
    clearTimeout(positionTimer);
    state.section = id; state.row = '';
    render(); menu(false);
    if (options.row) selectRow(options.row, {reveal: true});
    else { $('#reading').scrollIntoView({block: 'start', behavior: 'instant'}); $('#reading').focus({preventScroll: true}); }
    setURL(Boolean(options.replace)); rememberPosition();
  }
  function selectRow(id, {reveal = false} = {}) {
    const entry = rowMap.get(id) || rowMap.get(normalizeRow(id));
    if (!entry || entry.section.id !== state.section) return false;
    state.row = entry.row.id;
    if (reveal && state.mode === 'zh' && !canDisplay(groupMap.get(entry.row.groupId))) { state.mode = 'parallel'; applySettings(); }
    $$('.english-unit.selected, .aligned-zh.selected').forEach(element => element.classList.remove('selected'));
    let target = $$('[data-row]').find(element => element.dataset.row === entry.row.id);
    if (state.mode === 'zh') {
      const group = groupMap.get(entry.row.groupId);
      const first = current().rows.find(row => row.groupId && row.groupId === group?.id) || entry.row;
      target = $$('[data-translation-row]').find(element => element.dataset.translationRow === first.id);
    }
    if (target) {
      target.classList.add('selected'); target.tabIndex = -1;
      target.scrollIntoView({block: 'center', behavior: 'instant'}); target.focus({preventScroll: true});
    }
    return Boolean(target);
  }
  $('#aligned-section').onchange = event => changeSection(event.target.value);
  for (const [id, offset] of [['aligned-prev', -1], ['aligned-next', 1]]) $('#' + id).onclick = () => {
    const next = work?.sections[work.sections.indexOf(current()) + offset]; if (next) changeSection(next.id);
  };
  $('#work-toc').onclick = event => { const button = event.target.closest('[data-section]'); if (button) changeSection(button.dataset.section); };
  function updateBookmarks() {
    $('#bookmark-count').textContent = state.bookmarks.length; $('#bookmark-count').hidden = !state.bookmarks.length;
    $$('[data-bookmark]').forEach(button => {
      const row = rowMap.get(button.dataset.bookmark)?.row; if (!row) return;
      const marked = bookmarkIndex(row) >= 0;
      button.textContent = marked ? '◆' : '◇'; button.setAttribute('aria-pressed', String(marked));
      button.setAttribute('aria-label', marked ? '取消书签' : '添加书签'); button.title = marked ? '取消书签' : '添加书签';
    });
  }
  $('#aligned-text').onclick = event => {
    const button = event.target.closest('[data-bookmark]');
    if (button) {
      const row = rowMap.get(button.dataset.bookmark)?.row; if (!row) return;
      const index = bookmarkIndex(row);
      if (index >= 0) state.bookmarks.splice(index, 1);
      else state.bookmarks.push({work: state.work, englishWork: state.englishWork, section: state.section, row: row.id, label: current().label, text: row.english.text.slice(0, 180)});
      updateBookmarks(); persist(); toast(index >= 0 ? '已移除书签' : '已添加书签'); return;
    }
    const shared = event.target.closest('[data-shared]');
    if (shared) { const entry = rowMap.get(shared.dataset.shared); if (entry) changeSection(entry.section.id, {row: entry.row.id}); return; }
    const link = event.target.closest('.aligned-translation a');
    if (link) {
      const anchor = link.dataset.sourceAnchor || link.getAttribute('href')?.split('#')[1];
      if (anchor) { event.preventDefault(); location.href = sourceURL(anchor); }
    }
  };
  function showDialog(id) { menu(false); const dialog = $(id); if (!dialog.open) dialog.showModal(); }
  $$('[data-close]').forEach(button => button.onclick = () => button.closest('dialog').close());
  $$('dialog').forEach(dialog => dialog.onclick = event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
  function renderLibrary() {
    const query = $('#library-query').value.trim().toLocaleLowerCase(), zhuOnly = $('#zhu-only').checked;
    const matches = catalog.filter(item => (!zhuOnly || item.translator === '朱生豪') && [item.title, item.translatorCredit, englishCatalog.find(entry => entry.id === englishId(item))?.title].join(' ').toLocaleLowerCase().includes(query));
    $('#library-summary').textContent = catalog.length + ' 部戏剧 · 按各剧原书署名 · 当前显示 ' + matches.length + ' 部';
    $('#library-results').innerHTML = matches.map(item => {
      const summary = alignedCatalog.find(entry => entry.id === englishId(item));
      const matched = (summary?.automaticUnits || 0) + (summary?.reviewedUnits || 0);
      const count = summary?.englishUnits || 0;
      return '<button class="shelf-book" data-work="' + esc(item.id) + '"><strong>' + esc(item.title) + '</strong><em lang="en">' + esc(englishCatalog.find(entry => entry.id === englishId(item))?.title || '') + '</em><small>' + esc(item.translatorCredit || item.translator) + (item.attributionStatus === 'source-credit-uncertain' ? ' · 署名待核实' : '') + '</small><span>' + (count ? '中英对应 ' + matched + ' / ' + count + ' 段' : '英文完整保留 · 对应数据待准备') + '</span></button>';
    }).join('') || '<p class="empty-state">没有匹配作品，试试其他书名或译者。</p>';
  }
  $('#library-button').onclick = () => { renderLibrary(); showDialog('#library-dialog'); };
  $('#library-query').oninput = renderLibrary; $('#zhu-only').onchange = renderLibrary;
  $('#library-results').onclick = event => {
    const button = event.target.closest('[data-work]'); if (!button) return;
    $('#library-dialog').close(); openWork(button.dataset.work);
  };
  function excerpt(text, query) {
    const start = Math.max(0, text.toLocaleLowerCase().indexOf(query) - 35);
    return (start ? '…' : '') + text.slice(start, start + 180) + (text.length > start + 180 ? '…' : '');
  }
  function search() {
    const query = $('#search-input').value.trim().toLocaleLowerCase(), hits = [], chineseGroups = new Set();
    if (query && work) for (const section of work.sections) for (const row of section.rows) {
      const group = groupMap.get(row.groupId), chinese = canDisplay(group) ? group.chineseText || '' : '';
      const englishHit = [row.english.text, row.speaker || ''].some(text => text.toLocaleLowerCase().includes(query));
      const chineseHit = chinese.toLocaleLowerCase().includes(query) && !chineseGroups.has(group?.id);
      if (chineseHit) chineseGroups.add(group.id);
      if (englishHit || chineseHit) hits.push({section, row, chinese: chineseHit ? chinese : '', language: englishHit ? 'en' : 'zh'});
    }
    $('#search-summary').textContent = query ? '找到 ' + hits.length + ' 段台词或舞台提示' + (hits.length > 100 ? '，显示前 100 段，请缩小搜索范围' : '') : '搜索当前戏剧的完整英文、角色名与已对应中文';
    $('#search-results').innerHTML = hits.slice(0, 100).map(({section, row, chinese, language}) => '<button class="result" data-result-language="' + language + '" data-result-section="' + esc(section.id) + '" data-result-row="' + esc(row.id) + '"><strong>' + esc(section.label) + (row.speaker ? ' · ' + esc(row.speaker) : '') + '</strong><p lang="en">' + esc(excerpt(row.english.text, query)) + '</p>' + (chinese ? '<small lang="zh-CN">' + esc(excerpt(chinese, query)) + '</small>' : '') + '</button>').join('') || '<p class="empty-state">' + (query ? '没有找到匹配内容' : '输入词句，直接跳到对应台词段') + '</p>';
  }
  function openSearch() { showDialog('#search-dialog'); search(); $('#search-input').focus(); }
  $('#search-button').onclick = openSearch; $('#search-input').oninput = search;
  $('#search-results').onclick = event => {
    const button = event.target.closest('[data-result-row]'); if (!button) return;
    $('#search-dialog').close();
    if (state.mode !== 'parallel' && state.mode !== button.dataset.resultLanguage) { state.mode = 'parallel'; applySettings(); }
    changeSection(button.dataset.resultSection, {row: button.dataset.resultRow});
  };
  $('#bookmarks-button').onclick = () => {
    $('#bookmark-results').innerHTML = state.bookmarks.map((mark, index) => '<button class="result" data-bookmark-index="' + index + '"><strong>' + esc(catalog.find(item => item.id === mark.work)?.title || '') + ' · ' + esc(mark.label || mark.section) + '</strong><p lang="en">' + esc(mark.text) + '</p></button>').join('') || '<p class="empty-state">点击正文旁的 ◇ 收藏台词段。书签保存在此浏览器。<br>原始底本中的旧书签仍可在底本阅读器中查看。</p>';
    showDialog('#bookmarks-dialog');
  };
  $('#bookmark-results').onclick = event => {
    const button = event.target.closest('[data-bookmark-index]'); if (!button) return;
    const mark = state.bookmarks[Number(button.dataset.bookmarkIndex)]; if (!mark) return;
    $('#bookmarks-dialog').close(); openWork(mark.work, mark);
  };
  $('#type-button').onclick = () => showDialog('#type-dialog');
  $('#font-size').oninput = event => { state.fontSize = Math.max(16, Math.min(28, Number(event.target.value) || 20)); applySettings(); persist(); };
  $$('[data-theme-choice]').forEach(button => button.onclick = () => { state.theme = button.dataset.themeChoice; applySettings(); persist(); });
  $$('[data-spacing]').forEach(button => button.onclick = () => { state.spacing = button.dataset.spacing; applySettings(); persist(); });
  $('#reset-settings').onclick = () => { state.fontSize = 20; state.spacing = '1.9'; state.theme = 'paper'; applySettings(); persist(); };
  $('#reading-mode').onchange = event => { state.mode = event.target.value; applySettings(); persist(); };
  function menu(open) {
    const mobile = innerWidth <= 900, expanded = mobile && open;
    $('#sidebar').inert = mobile && !expanded; $('#sidebar').classList.toggle('open', expanded);
    $('#scrim').hidden = !expanded; $('#menu-button').setAttribute('aria-expanded', String(expanded));
    $('#menu-button').setAttribute('aria-label', expanded ? '关闭目录' : '打开目录');
    document.body.classList.toggle('menu-open', expanded);
  }
  $('#menu-button').onclick = () => menu(!$('#sidebar').classList.contains('open'));
  $('#scrim').onclick = () => menu(false);
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); if (!$$('dialog[open]').length) openSearch(); }
    if (event.key === 'Escape') { const wasOpen = $('#sidebar').classList.contains('open'); menu(false); if (wasOpen) $('#menu-button').focus(); }
    if (event.key === 'Tab' && innerWidth <= 900 && $('#sidebar').classList.contains('open')) {
      const focusable = [$('#menu-button'), ...$('#sidebar').querySelectorAll('button:not([disabled]), a[href]')];
      const index = focusable.indexOf(document.activeElement);
      event.preventDefault();
      const next = index < 0 ? 0 : (index + (event.shiftKey ? -1 : 1) + focusable.length) % focusable.length;
      focusable[next].focus();
    }
  });
  function updateProgress() {
    const rect = $('#reading').getBoundingClientRect();
    const percent = Math.max(0, Math.min(100, Math.round((140 - rect.top) / Math.max(1, rect.height - innerHeight + 190) * 100)));
    $('#progress-label').textContent = percent + '%'; $('#progress-fill').style.width = percent + '%'; $('#progress-slider').value = percent;
  }
  function capturePosition() {
    if (restoringPosition || !work || !current()) return;
    const elements = state.mode === 'zh' ? $$('[data-translation-row]') : $$('[data-row]');
    let closest = null, distance = Infinity;
    for (const element of elements) {
      const rect = element.getBoundingClientRect();
      if (!rect.height) continue;
      const delta = Math.abs(rect.top - 150);
      if (delta < distance) { closest = element; distance = delta; }
    }
    if (closest) rememberPosition(closest.dataset.row || closest.dataset.translationRow);
  }
  window.addEventListener('scroll', () => {
    cancelAnimationFrame(progressFrame); progressFrame = requestAnimationFrame(updateProgress);
    clearTimeout(positionTimer); if (!restoringPosition) positionTimer = setTimeout(capturePosition, 180);
  }, {passive: true});
  window.addEventListener('resize', () => { menu($('#sidebar').classList.contains('open')); updateProgress(); });
  $('#progress-slider').oninput = event => {
    const rect = $('#reading').getBoundingClientRect();
    scrollTo({top: Math.max(0, scrollY + rect.top - 140 + Math.max(1, rect.height - innerHeight + 190) * Number(event.target.value) / 100)});
  };
  $('#back-to-start').onclick = () => $('#reading').scrollIntoView({block: 'start'});
  $('#jump-end').onclick = () => $('.scene-end').scrollIntoView({block: 'center'});
  function navigateHistory() {
    if (location.hash === lastRoute) return;
    lastRoute = location.hash;
    $$('dialog[open]').forEach(dialog => dialog.close()); menu(false);
    const requested = route(); openWork(requested.work || 'part0037', {...requested, replace: true});
  }
  window.addEventListener('popstate', navigateHistory); window.addEventListener('hashchange', navigateHistory);
  window.addEventListener('pagehide', () => { capturePosition(); persist(); });
  applySettings(); updateBookmarks(); menu(false);
  const requested = route(); lastRoute = location.hash;
  openWork(requested.work || state.work, {...requested, replace: true});
})();
