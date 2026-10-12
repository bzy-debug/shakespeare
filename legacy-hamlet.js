'use strict';
(() => {
  const rows = window.HAMLET_SCENE;
  const names = { BERNARDO: '勃那陀', FRANCISCO: '弗兰西斯科', HORATIO: '霍拉旭', MARCELLUS: '玛昔勒斯' };
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const esc = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const key = 'shakespeare.hamlet.1.1.v1';
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(key)) || {}; } catch {}
  const state = {
    bookmarks: new Set(Array.isArray(saved.bookmarks) ? saved.bookmarks.filter(id => rows.some(r => r.id === id)) : []),
    selected: rows.some(r => r.id === saved.selected) ? saved.selected : rows[2].id,
    fontSize: Number.isFinite(saved.fontSize) ? Math.min(28, Math.max(16, saved.fontSize)) : 20,
    theme: ['paper','light','night'].includes(saved.theme) ? saved.theme : 'paper',
    spacing: ['1.65','1.9','2.2'].includes(saved.spacing) ? saved.spacing : '1.9',
    mode: ['parallel','en','zh'].includes(saved.mode) ? saved.mode : 'parallel',
    position: typeof saved.position === 'string' ? saved.position : null,
  };
  let toastTimer, saveTimer, ticking = false, restoring = true;
  const persist = () => { try { localStorage.setItem(key, JSON.stringify({...state,bookmarks:[...state.bookmarks]})); } catch {} };
  function toast(message) { $('#toast').textContent=message; $('#toast').classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),2100); }
  $('#dialogue').innerHTML = rows.map((r,i) => `<article class="dialogue-row ${r.type === 'stage' ? 'stage' : ''}" id="${r.id}" tabindex="0" aria-label="${r.type === 'stage' ? '舞台提示' : names[r.speaker]+'的台词'}，第${i+1}段"><span class="row-number" title="${r.line ? '原文第 '+r.line+' 行' : '舞台提示'}">${String(i+1).padStart(2,'0')}</span><div class="passage en" lang="en">${r.speaker ? `<h3 class="speaker">${esc(r.speaker)}</h3>` : ''}<p>${esc(r.en)}</p></div><div class="passage zh" lang="zh-CN">${r.speaker ? `<h3 class="speaker">${names[r.speaker]}</h3>` : ''}<p>${esc(r.zh)}</p></div><button class="row-bookmark" aria-label="收藏第${i+1}段" aria-pressed="false" title="添加书签"><svg><use href="#i-bookmark"/></svg></button></article>`).join('');
  const elements = $$('.dialogue-row');
  const select = (id) => { state.selected=id; elements.forEach(el=>el.classList.toggle('selected',el.id===id)); persist(); };
  function updateBookmarks() {
    elements.forEach((el,i)=>{ const active=state.bookmarks.has(el.id);const b=el.querySelector('.row-bookmark');b.classList.toggle('saved',active);b.setAttribute('aria-pressed',String(active));b.setAttribute('aria-label',`${active?'取消收藏':'收藏'}第${i+1}段`);b.title=active?'移除书签':'添加书签'; });
    $('#bookmark-count').textContent=state.bookmarks.size;$('#bookmark-count').hidden=!state.bookmarks.size;
  }
  elements.forEach((el,i)=>{
    el.addEventListener('click',e=>{if(e.target.closest('.row-bookmark'))return;if(window.getSelection()?.toString())return;select(el.id);});
    el.addEventListener('keydown',e=>{if(e.target!==el)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();select(el.id);}if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const next=elements[i+(e.key==='ArrowDown'?1:-1)];if(next){next.focus();select(next.id);}}});
    el.querySelector('.row-bookmark').addEventListener('click',()=>{if(state.bookmarks.has(el.id)){state.bookmarks.delete(el.id);toast('已移除书签');}else{state.bookmarks.add(el.id);toast('已收藏这段台词');}updateBookmarks();persist();});
  });
  function applySettings() {
    document.documentElement.style.setProperty('--font-size',state.fontSize+'px');
    document.documentElement.style.setProperty('--leading',state.spacing);
    document.body.dataset.theme=state.theme;document.body.dataset.mode=state.mode;
    $('#font-size').value=state.fontSize;$('#font-output').value=state.fontSize+' px';$('#reading-mode').value=state.mode;
    $$('[data-theme-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.themeChoice===state.theme)));
    $$('[data-spacing]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.spacing===state.spacing)));
    requestAnimationFrame(updateProgress);
  }
  function showDialog(id) {const d=$(id);if(!d.open)d.showModal();}
  $$('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
  $$('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));
  $('#type-button').addEventListener('click',()=>showDialog('#type-dialog'));
  $('#font-size').addEventListener('input',e=>{state.fontSize=Number(e.target.value);applySettings();persist();});
  $$('[data-theme-choice]').forEach(b=>b.addEventListener('click',()=>{state.theme=b.dataset.themeChoice;applySettings();persist();}));
  $$('[data-spacing]').forEach(b=>b.addEventListener('click',()=>{state.spacing=b.dataset.spacing;applySettings();persist();}));
  $('#reset-settings').addEventListener('click',()=>{state.fontSize=20;state.spacing='1.9';state.theme='paper';applySettings();persist();});
  $('#reading-mode').addEventListener('change',e=>{const anchor=firstVisible();state.mode=e.target.value;applySettings();if(window.scrollY>250)document.getElementById(anchor)?.scrollIntoView({block:'start'});persist();});
  function jump(id) {const el=document.getElementById(id);if(!el)return;select(id);el.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});el.focus({preventScroll:true});}
  function excerpt(s,max=120){return s.length>max?s.slice(0,max)+'…':s;}
  function highlighted(s,q){if(!q)return esc(excerpt(s));const at=s.toLocaleLowerCase().indexOf(q.toLocaleLowerCase());if(at<0)return esc(excerpt(s));const from=Math.max(0,at-35),to=Math.min(s.length,at+q.length+95);return (from?'…':'')+esc(s.slice(from,at))+'<mark>'+esc(s.slice(at,at+q.length))+'</mark>'+esc(s.slice(at+q.length,to))+(to<s.length?'…':'');}
  function resultHTML(r,q=''){return `<button class="result" data-jump="${r.id}"><strong>${r.speaker?names[r.speaker]+' · '+r.speaker:'舞台提示'} <span> / ${r.line?'原文第 '+r.line+' 行':'第一幕第一场'}</span></strong><p lang="en">${highlighted(r.en,q)}</p><small>${highlighted(r.zh,q)}</small></button>`;}
  function wireResults(container,dialog){container.querySelectorAll('[data-jump]').forEach(b=>b.addEventListener('click',()=>{dialog.close();jump(b.dataset.jump);}));}
  function search(){const q=$('#search-input').value.trim();const result=$('#search-results');if(!q){$('#search-summary').textContent='在第一幕第一场中搜索 · 支持中英文与角色名';result.innerHTML='<div class="empty-state">试试 “Who’s there”、ghost 或「霍拉旭」</div>';return;}const normalized=q.replace(/[’‘]/g,"'").toLocaleLowerCase();const matches=rows.filter(r=>[r.en,r.zh,r.speaker||'',names[r.speaker]||''].some(t=>t.toLocaleLowerCase().includes(normalized)));$('#search-summary').textContent=`找到 ${matches.length} 段台词或舞台提示`;result.innerHTML=matches.length?matches.map(r=>resultHTML(r,q)).join(''):'<div class="empty-state">没有找到匹配内容。<br>试试更短的词句，或换一种语言。</div>';wireResults(result,$('#search-dialog'));}
  function openSearch(){showDialog('#search-dialog');search();$('#search-input').focus();}
  $('#search-button').addEventListener('click',openSearch);$('#search-input').addEventListener('input',search);
  $('#bookmarks-button').addEventListener('click',()=>{const result=$('#bookmark-results');const bookmarks=rows.filter(r=>state.bookmarks.has(r.id));result.innerHTML=bookmarks.length?bookmarks.map(r=>resultHTML(r)).join(''):'<div class="empty-state">还没有书签。<br>点击台词右侧的书签图标，留住喜欢的句子。</div>';wireResults(result,$('#bookmarks-dialog'));showDialog('#bookmarks-dialog');});
  $('#library-button').addEventListener('click',()=>{toggleMenu(false);showDialog('#library-dialog');});
  $('#open-hamlet').addEventListener('click',()=>$('#library-dialog').close());
  function toggleMenu(open){$('#sidebar').inert=window.innerWidth<=900&&!open;$('#sidebar').classList.toggle('open',open);$('#scrim').hidden=!open;$('#menu-button').setAttribute('aria-expanded',String(open));}
  $('#menu-button').addEventListener('click',()=>toggleMenu(!$('#sidebar').classList.contains('open')));$('#scrim').addEventListener('click',()=>toggleMenu(false));
  document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!$$('dialog[open]').length)openSearch();}if(e.key==='Escape')toggleMenu(false);});
  const toTop=()=>{toggleMenu(false);window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});};
  $('#scene-start').addEventListener('click',toTop);$('#back-to-start').addEventListener('click',toTop);
  $('#jump-end').addEventListener('click',()=>jump(rows.at(-1).id));
  function firstVisible(){return elements.find(el=>el.getBoundingClientRect().bottom>150)?.id||rows.at(-1).id;}
  function updateProgress(){const first=elements[0].getBoundingClientRect().top+window.scrollY;const last=elements.at(-1).getBoundingClientRect().bottom+window.scrollY;const max=Math.max(1,last-window.innerHeight+65-first+150);const p=Math.min(100,Math.max(0,Math.round((window.scrollY-first+150)/max*100)));$('#progress-label').textContent=p+'%';$('#progress-fill').style.width=p+'%';$('#progress-slider').value=p;const id=firstVisible();const row=rows.find(r=>r.id===id);$('#current-line').textContent=window.scrollY<100?'开场':(row.line?'原文第 '+row.line+' 行':'舞台提示');if(!restoring){state.position=window.scrollY<100?null:id;clearTimeout(saveTimer);saveTimer=setTimeout(persist,250);}ticking=false;}
  window.addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(updateProgress);}},{passive:true});
  window.addEventListener('resize',()=>{toggleMenu(window.innerWidth<=900&&$('#sidebar').classList.contains('open'));updateProgress();});
  $('#progress-slider').addEventListener('input',e=>{const first=elements[0].getBoundingClientRect().top+window.scrollY;const last=elements.at(-1).getBoundingClientRect().bottom+window.scrollY;const max=Math.max(1,last-window.innerHeight+65-first+150);window.scrollTo({top:first-150+max*Number(e.target.value)/100,behavior:'instant'});});
  toggleMenu(false);select(state.selected);updateBookmarks();applySettings();
  const restore=()=>{if(state.position)document.getElementById(state.position)?.scrollIntoView({block:'start'});restoring=false;updateProgress();};
  Promise.all([document.fonts.ready,new Promise(resolve=>{const img=$('.hero-art img');if(img.complete)resolve();else{img.addEventListener('load',resolve,{once:true});img.addEventListener('error',resolve,{once:true});}})]).then(restore);
  window.addEventListener('pagehide',persist);
})();
