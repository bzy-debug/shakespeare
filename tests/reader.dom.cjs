// DOM/state interaction tests; this does not replace real browser/layout QA.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,ResourceLoader,VirtualConsole}=require(process.env.JSDOM_MODULE||'jsdom');
const root=path.resolve(__dirname,'..');
let failOnce=null;let delayOnce=null;
class LocalResources extends ResourceLoader {
  fetch(url){const u=new URL(url);if(u.origin!=='http://reader.test')return null;if(failOnce&&u.pathname===failOnce){failOnce=null;return Promise.reject(Error('simulated load failure'));}const f=path.resolve(root,'.'+decodeURIComponent(u.pathname));if(!f.startsWith(root+path.sep)||!fs.existsSync(f))return null;const data=fs.readFileSync(f);if(delayOnce&&u.pathname===delayOnce){delayOnce=null;return new Promise(r=>setTimeout(()=>r(data),150));}return Promise.resolve(data);}
}
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,label){for(let i=0;i<120;i++){if(fn())return;await pause(25);}throw Error('Timed out: '+label);}
function create(hash='',storage={}){
 const errors=[];const v=new VirtualConsole();v.on('jsdomError',e=>{if(!e.message.includes('CSS'))errors.push(e.message);});
 const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{url:'http://reader.test/index.html'+hash,runScripts:'dangerously',resources:new LocalResources(),pretendToBeVisual:true,virtualConsole:v,beforeParse(w){w.scrollTo=()=>{};w.HTMLElement.prototype.scrollIntoView=function(){};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};for(const [k,v] of Object.entries(storage))w.localStorage.setItem(k,v);w.addEventListener('error',e=>errors.push(e.message));}});
 return {dom,w:dom.window,d:dom.window.document,errors};
}
async function ready(t,title){await until(()=>t.d.querySelector('#reading').getAttribute('aria-busy')==='false'&&t.d.querySelector('#chinese-text .source-block')&&(!title||t.d.title.includes(title)),title||'reader ready');}
function click(t,s){assert.ok(t.d.querySelector(s),s);t.d.querySelector(s).click();}
function change(t,s,value){const e=t.d.querySelector(s);e.value=value;e.dispatchEvent(new t.w.Event('change',{bubbles:true}));}
function input(t,s,value){const e=t.d.querySelector(s);e.value=value;e.dispatchEvent(new t.w.Event('input',{bubbles:true}));}
(async()=>{
 const t=create();await ready(t,'哈姆莱特');assert.equal(t.d.querySelectorAll('#english-text .source-block').length,72);assert.ok(t.d.querySelector('#english-text .speaker').textContent.includes('BERNARDO'));assert.ok(t.d.querySelector('#chinese-text').textContent.includes('吴兴华'));
 click(t,'#search-button');input(t,'#search-input','BERNARDO');assert.ok(t.d.querySelectorAll('#search-results .result').length>5);t.d.querySelector('#search-dialog').close();
 click(t,'#library-button');assert.equal(t.d.querySelectorAll('.shelf-book').length,43);t.d.querySelector('#zhu-only').checked=true;change(t,'#zhu-only','on');assert.equal(t.d.querySelectorAll('.shelf-book').length,30);t.d.querySelector('#zhu-only').checked=false;change(t,'#zhu-only','on');input(t,'#library-query','章益');assert.equal(t.d.querySelectorAll('.shelf-book').length,3);input(t,'#library-query','');
 click(t,'[data-work="part0035"]');await ready(t,'麦克白');assert.ok(t.d.querySelector('#english-text').textContent.includes('thunder'));
 const zhOptions=t.d.querySelector('#zh-section').options;change(t,'#zh-section',zhOptions[2].value);assert.ok(t.d.querySelector('#chinese-text').textContent.length>100);const sectionId=t.d.querySelector('#zh-section').value;
 click(t,'#chinese-text .block-bookmark');assert.equal(t.d.querySelector('#bookmark-count').textContent,'1');assert.equal(t.d.querySelector('#chinese-text .block-bookmark').getAttribute('aria-pressed'),'true');
 click(t,'#search-button');input(t,'#search-input','麦克白');assert.ok(t.d.querySelectorAll('#search-results .result').length>0);click(t,'#search-results .result');assert.equal(t.d.querySelector('#search-dialog').open,false);
 change(t,'#reading-mode','zh');assert.equal(t.d.body.dataset.mode,'zh');click(t,'[data-theme-choice="night"]');assert.equal(t.d.body.dataset.theme,'night');input(t,'#font-size','26');assert.equal(t.d.documentElement.style.getPropertyValue('--font-size'),'26px');
 click(t,'#library-button');click(t,'[data-work="part0046"]');await ready(t,'情女怨');assert.equal(t.d.querySelector('#english-work').options.length,4);assert.equal(t.d.querySelector('#english-work').hidden,false);change(t,'#english-work','phoenix_and_turtle');await until(()=>t.d.querySelector('#english-text').textContent.includes('LET the bird'),'poem switch');assert.ok(t.w.location.hash.includes('phoenix_and_turtle'));
 click(t,'#bookmarks-button');click(t,'[data-bookmark-index="0"]');await ready(t,'麦克白');assert.equal(t.d.querySelector('#zh-section').value,sectionId);assert.ok(t.d.querySelector('#chinese-text .selected'));
 // Footnotes navigate into the dedicated notes section and return to text.
 let sec=t.w.SHAKESPEARE_CHINESE.part0035.sections.find(s=>s.blocks.some(b=>b.html.includes('data-source-anchor')));change(t,'#zh-section',sec.id);const a=t.d.querySelector('#chinese-text [data-source-anchor]');assert.ok(a);a.click();assert.equal(t.d.querySelector('#zh-section').selectedOptions[0].textContent,'注释');assert.ok(t.d.querySelector('#chinese-text [data-source-anchor]'));t.d.querySelector('#chinese-text [data-source-anchor]').click();assert.notEqual(t.d.querySelector('#zh-section').selectedOptions[0].textContent,'注释');
 const storage={'shakespeare.collection.v1':t.w.localStorage.getItem('shakespeare.collection.v1')};assert.deepEqual(t.errors,[]);t.dom.window.close();
 const re=create('',storage);await ready(re,'麦克白');assert.equal(re.d.body.dataset.theme,'night');assert.equal(re.d.querySelector('#bookmark-count').textContent,'1');assert.equal(re.d.querySelector('#font-size').value,'26');re.dom.window.close();
 const corrupt=create('',{'shakespeare.collection.v1':'null'});await ready(corrupt,'哈姆莱特');assert.deepEqual(corrupt.errors,[]);corrupt.dom.window.close();
 // All reader work routes load both languages, including both supplemental plays.
 const all=create();await ready(all);for(const work of all.w.SHAKESPEARE_CHINESE_CATALOG){click(all,'#library-button');click(all,'[data-work="'+work.id+'"]');await ready(all,work.title);assert.ok(all.d.querySelector('#english-text .source-block'),work.title);assert.ok(!all.d.querySelector('#load-status').textContent,work.title);}assert.deepEqual(all.errors,[]);all.dom.window.close();
 // A slower earlier navigation cannot overwrite a newer choice.
 delayOnce='/data/chinese-collection/works/part0041.js';const race=create();await ready(race);click(race,'#library-button');click(race,'[data-work="part0041"]');click(race,'#library-button');click(race,'[data-work="part0042"]');await ready(race,'两位贵亲戚');await pause(200);assert.ok(race.d.title.includes('两位贵亲戚'));assert.ok(race.w.location.hash.includes('part0042'));race.w.history.back();await ready(race,'哈姆莱特');race.w.history.forward();await ready(race,'两位贵亲戚');race.dom.window.close();
 // A missing payload shows a retry and does not poison the lazy-load cache.
 failOnce='/data/chinese-collection/works/part0041.js';const retry=create('#work=part0041');await until(()=>retry.d.querySelector('#load-status button'),'retry button');click(retry,'#load-status button');await ready(retry,'爱德华三世');retry.dom.window.close();
 console.log('PASS: reader DOM integration, 43-work shelf, translator filtering, lazy load, speakers, section navigation, search, bookmarks, 4-poem switch, footnotes, settings persistence, malformed storage, all-work routes, stale-load race, back/forward, retry.');
})().catch(e=>{console.error(e);process.exitCode=1;});
