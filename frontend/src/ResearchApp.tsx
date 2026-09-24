import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './research.css';
import './control.css';
import './dashboard.css';
import ControlPanel from './ControlPanel';

type Event = {id:number;stage:string;status:string;detail:string;at:number;duration_ms?:number;span_id?:string;service_url?:string;proxy?:string;target?:string};
type Run = {id:string;query:string;mode:string;status:string;created_at:number;cached?:boolean;unique_tools?:boolean;events:Event[];result?:{answer:string;provider?:string;sources:{url:string;title:string;snippet:string}[]}};
type Resource = {id:string;name:string;url:string;description:string;category:string;integration_status:string};
type System = {providers:Record<string,string[]>;quotas:{provider:string;used:number;period:string}[];cases:{id:string;query:string;advice:string}[]};
const API = process.env.REACT_APP_API_URL || '';
async function api<T>(path:string, body?:unknown):Promise<T> {
  const response=await fetch(`${API}/api${path}`,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!response.ok) throw new Error(`Сервер вернул ${response.status}. Попробуйте ещё раз.`);
  return response.json();
}
const names:Record<string,string>={router:'Маршрутизатор',cache:'Кэш',httpx:'HTTPX',jina:'Jina Reader',duckduckgo:'DuckDuckGo',searxng:'SearXNG',tavily:'Tavily',firecrawl:'Firecrawl',recovery:'Агент восстановления',synthesis:'Синтез ответа',result:'Результат',runtime:'Исполнение'};
const statuses:Record<string,string>={running:'В работе',completed:'Готово',success:'Успешно',failed:'Ошибка',error:'Ошибка',skipped:'Пропущено',cancelled:'Остановлен',interrupted:'Прерван'};
function Mark(){return <span className="inet-mark">✳</span>}

export default function ResearchApp(){
  const [page,setPage]=useState('search');
  const [runs,setRuns]=useState<Run[]>([]);
  const [selected,setSelected]=useState<string|null>(null);
  const [query,setQuery]=useState('');
  const [mode,setMode]=useState('auto');
  const [fresh,setFresh]=useState(false);
  const [archive,setArchive]=useState(false);
  const [uniqueTools,setUniqueTools]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [connected,setConnected]=useState(false);
  const [resources,setResources]=useState<Resource[]>([]);
  const [filter,setFilter]=useState('');
  const [category,setCategory]=useState('all');
  const [system,setSystem]=useState<System|null>(null);
  const [event,setEvent]=useState<Event|null>(null);
  const current=runs.find(r=>r.id===selected);
  const currentSources=current?.result?.sources||[];
  const sourceDomains=Array.from(new Set(currentSources.map(source=>{try{return new URL(source.url).hostname.replace(/^www\./,'');}catch{return ''}}).filter(Boolean)));
  const routeTools=Array.from(new Set((current?.events||[]).filter(item=>item.status==='success'&&!['router','cache','synthesis','result'].includes(item.stage)).map(item=>names[item.stage]||item.stage)));
  const attemptedTools=Array.from(new Set((current?.events||[]).filter(item=>item.span_id).map(item=>names[item.stage]||item.stage)));
  const failedAttempts=(current?.events||[]).filter(item=>item.status==='error'&&item.span_id);
  const routeDuration=current?.events?.length?Math.max(0,Math.round(((current.events[current.events.length-1]?.at||0)-(current.events[0]?.at||0)))):0;
  useEffect(()=>{
    let alive=true;
    async function refresh(){
      try{
        const [r,s]=await Promise.all([api<Run[]>('/runs'),api<System>('/system')]);
        if(alive){setRuns(r);setSystem(s);setConnected(true);}
      }catch{if(alive)setConnected(false);}
    }
    refresh();
    api<{resources:Resource[]}>('/resources').then(x=>{if(alive)setResources(x.resources);}).catch(()=>{if(alive)setError('Не удалось загрузить каталог. Проверьте подключение к серверу.');});
    const timer=setInterval(refresh,1200);
    return()=>{alive=false;clearInterval(timer);};
  },[]);
  async function submit(text=query){
    if(!text.trim()||busy)return;
    setBusy(true);setError('');
    try{const run=await api<Run>('/runs',{query:text,mode,fresh,allow_archive:archive,unique_tools:uniqueTools});setRuns(old=>[run,...old.filter(x=>x.id!==run.id)]);setSelected(run.id);setQuery('');setPage('search');setEvent(null);}
    catch(e){setError(e instanceof Error?e.message:'Запрос не отправлен');}
    finally{setBusy(false);}
  }
  async function cancel(){if(!current)return;try{const r=await api<Run>(`/runs/${current.id}/cancel`,{});setRuns(old=>old.map(x=>x.id===r.id?r:x));}catch{setError('Не удалось остановить запрос');}}
  async function resumeRun(){if(!current)return;try{const r=await api<Run>(`/runs/${current.id}/resume`,{});setRuns(old=>old.map(x=>x.id===r.id?r:x));}catch{setError('Нет незавершённой контрольной точки. Отправьте новый запрос.');}}
  function openRun(id:string){setSelected(id);setEvent(null);}
  const shown=resources.filter(r=>(category==='all'||r.category===category)&&`${r.name} ${r.description}`.toLowerCase().includes(filter.toLowerCase()));
  const latestEvents=current?.events.reduce<Event[]>((acc,e)=>{const i=acc.findIndex(x=>(x.span_id||x.stage)===(e.span_id||e.stage));if(i>=0)acc[i]=e;else acc.push(e);return acc;},[])||[];
  const active=current?.status==='running';
  return <div className="research-app">
    <aside className="rail">
      <a href="/" className="wordmark" onClick={e=>{e.preventDefault();setPage('search');setSelected(null);}}><Mark/>inet<span>beta</span></a>
      <button className="new-research" aria-label="Новое исследование" onClick={()=>{setSelected(null);setPage('search');setError('');}}>＋ <span>Новое исследование</span></button>
      <nav aria-label="Основная навигация">
        {[['search','⌕','Поиск'],['map','⌘','Карта запросов'],['catalog','▦','Инструменты'],['system','◷','Система'],['control','⚙','Автоматизация']].map(([id,icon,label])=><button key={id} aria-label={label} className={page===id?'nav-active':''} onClick={()=>setPage(id)}><span aria-hidden="true">{icon}</span>{label}{id==='map'&&runs.some(r=>r.status==='running')&&<i className="live-dot"/>}</button>)}
      </nav>
      <div className="history-label">ИССЛЕДОВАНИЯ <span>{runs.length}</span></div>
      <div className="history">{runs.length?runs.map(r=><button key={r.id} className={selected===r.id?'selected':''} onClick={()=>{openRun(r.id);setPage('search');}}><span className={`tiny-dot ${r.status}`}/><span>{r.query}</span></button>):<p>Здесь появятся ваши запросы</p>}</div>
      <div className="rail-bottom"><span className={connected?'live-dot':'offline-dot'}/><span>{connected?'Сервер подключён':'Нет связи с сервером'}</span><small>v0.2</small></div>
    </aside>
    <main className="workspace">
      <header className="topbar"><span>Рабочее пространство <span className="slash">/</span> <b>{{search:'Исследование',map:'Карта запросов',catalog:'Инструменты',system:'Система',control:'Автоматизация'}[page]}</b></span><span className="private-label">◈ Локальное пространство</span></header>
      {page==='control'&&<ControlPanel/>}
      {error&&<div className="error-banner" role="alert">{error}<button aria-label="Закрыть ошибку" onClick={()=>setError('')}>×</button></div>}
      {page==='search'&&<div className={`search-page ${current?'has-result':''}`}>
        {!current?<div className="welcome-block"><div className="eyebrow"><span className="live-dot"/> АДАПТИВНЫЙ ПОИСК В ИНТЕРНЕТЕ</div><h1>От вопроса<br/>к <em>ясной картине.</em></h1><p>Ищите, исследуйте и читайте страницы.<br/>INET подберёт инструменты и покажет путь к результату.</p></div>:<section className="answer-section research-dashboard">
          <div className="result-hero"><div><div className="eyebrow"><span className={active?'live-dot':'result-check'}>{active?'':'✓'}</span>{current.mode==='fetch'?'ЧТЕНИЕ СТРАНИЦЫ':'ВЕБ-ИССЛЕДОВАНИЕ'} · {statuses[current.status]||current.status}</div><h1>{current.query}</h1></div><button className="route-button" onClick={()=>setPage('map')}>⌘ Показать маршрут <span>{latestEvents.length}</span></button></div>
          <div className="result-metrics"><div><strong>{currentSources.length}</strong><span>источников</span></div><div><strong>{sourceDomains.length}</strong><span>доменов</span></div><div><strong>{attemptedTools.length||routeTools.length}</strong><span>инструментов вызвано</span></div><div className={failedAttempts.length?'metric-warning':''}><strong>{failedAttempts.length}</strong><span>неудачных попыток</span></div><div><strong>{routeDuration||'—'}</strong><span>{routeDuration?'секунд':'в процессе'}</span></div></div>
          {['cancelled','interrupted'].includes(current.status)&&<button className="text-button" onClick={resumeRun}>Продолжить с контрольной точки →</button>}
          {active?<div className="running-box"><span className="spinner"/><div><strong>Исследуем источники</strong><p>{current.events.length?current.events[current.events.length-1].detail:'Запрос принят'}</p></div><button onClick={cancel}>Остановить</button></div>:<div className="result-layout"><section className="answer-pane"><div className="pane-heading"><span>✳</span><div><small>СИНТЕЗ</small><h2>Что удалось установить</h2></div></div>{current.result?<article className="answer answer-scroll"><ReactMarkdown remarkPlugins={[remarkGfm]}>{current.result.answer}</ReactMarkdown></article>:<p className="empty-inline">{statuses[current.status]}. {current.events[current.events.length-1]?.detail}</p>}</section><aside className="evidence-pane"><div className="pane-heading"><span>↗</span><div><small>ДОКАЗАТЕЛЬСТВА</small><h2>Источники и маршрут</h2></div></div><div className="route-strip">{current.unique_tools&&<span className="unique-badge">1× каждый</span>}{routeTools.length?routeTools.map((tool,index)=><React.Fragment key={tool}><span>{tool}</span>{index<routeTools.length-1&&<i>→</i>}</React.Fragment>):<span>Маршрут формируется</span>}</div>{failedAttempts.length>0&&<details className="attempt-details"><summary><span>!</span>{failedAttempts.length} неудачных попыток <b>Подробнее</b></summary><div>{failedAttempts.map(item=><article key={item.id}><strong>{names[item.stage]||item.stage}</strong><p>{item.detail}</p><small>{item.target||current.query}{item.duration_ms!==undefined?` · ${item.duration_ms} мс`:''}</small></article>)}</div></details>}<div className="compact-sources">{currentSources.slice(0,failedAttempts.length?4:6).map((source,index)=><a href={source.url} key={source.url+index} target="_blank" rel="noreferrer"><b>{index+1}</b><div><small>{(()=>{try{return new URL(source.url).hostname}catch{return source.url}})()}</small><strong>{source.title}</strong></div><span>↗</span></a>)}</div>{currentSources.length>(failedAttempts.length?4:6)&&<p className="more-sources">Ещё {currentSources.length-(failedAttempts.length?4:6)} источника доступны в ответе и JSON результата</p>}</aside></div>}
          {current.cached&&<div className="cache-note">↺ Результат из кэша · без повторного обращения к сервисам</div>}
        </section>}
        <form className="research-composer" onSubmit={e=>{e.preventDefault();submit();}}><textarea aria-label="Поисковый запрос или URL" placeholder="Что вы хотите исследовать?" value={query} maxLength={4000} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit();}}}/><div className="composer-bottom"><select aria-label="Режим запроса" value={mode} onChange={e=>setMode(e.target.value)}><option value="auto">◉ Автоматически</option><option value="search">Поиск в интернете</option><option value="fetch">Чтение URL</option></select><label><input type="checkbox" checked={fresh} onChange={e=>setFresh(e.target.checked)}/> Без кэша</label><label title="Запрещает повторно вызывать один и тот же инструмент в рамках исследования"><input type="checkbox" checked={uniqueTools} onChange={e=>setUniqueTools(e.target.checked)}/> Каждый инструмент один раз</label><button type="submit" aria-label="Начать исследование" disabled={!query.trim()||busy}>↑</button></div></form>
        {!current&&<><div className="suggestions">{['Современные агентные системы','https://example.com','Открытые инструменты веб-поиска'].map((s,i)=><button key={s} onClick={()=>submit(s)}><span>{['✧','↗','⌕'][i]}</span>{s}</button>)}</div><div className="explain-row"><div><span>01</span><strong>Умный маршрут</strong><p>Инструменты под вашу задачу</p></div><div><span>02</span><strong>Меньше запросов</strong><p>Кэш и контроль квот</p></div><div><span>03</span><strong>Всё на виду</strong><p>Источники и каждый этап</p></div></div></>}
        <label className="archive-option"><input type="checkbox" checked={archive} onChange={e=>setArchive(e.target.checked)}/> Разрешить архивные снимки Wayback</label>
        <p className="composer-footnote">{active?'Можно открыть карту и следить за выполнением.':'Проверяйте важные выводы по первоисточникам.'}</p>
      </div>}
      {page==='map'&&<div className="wide-page"><div className="page-heading"><div className="eyebrow">OBSERVABILITY</div><h1>Путь к ответу</h1><p>Каждый этап, сервис и резервный переход — в одной карте.</p></div><select className="run-select" aria-label="Запрос для карты" value={selected||''} onChange={e=>openRun(e.target.value)}><option value="">Выберите исследование</option>{runs.map(r=><option key={r.id} value={r.id}>{r.query}</option>)}</select>
        <div className="map-layout"><section className="map-canvas"><div className="map-label"><span className={active?'live-dot':'offline-dot'}/> {current?statuses[current.status]:'Ожидание запроса'}<span>LANGGRAPH</span></div>{current?<div className="flow"><div className="flow-input">↗ {current.query}</div>{latestEvents.map((e,i)=><React.Fragment key={e.span_id||e.stage}><div className={`flow-edge ${e.status}`}><span>{i===0?'вход':latestEvents[i-1].status==='error'?'ошибка → fallback':e.status==='skipped'?'проверка условия':'переход'}</span></div><button onClick={()=>setEvent(e)} className={`flow-node ${e.status} ${event?.stage===e.stage?'node-selected':''}`}><span className="node-symbol">{e.status==='error'?'!':e.status==='running'?'◌':'◇'}</span><div><strong>{names[e.stage]||e.stage}</strong><small>{statuses[e.status]||e.status}</small></div><span>{e.duration_ms!==undefined?`${e.duration_ms} ms`:'↗'}</span></button></React.Fragment>)}</div>:<div className="map-empty"><Mark/><h2>У каждого ответа есть путь</h2><p>Запустите исследование, чтобы увидеть<br/>фактический маршрут запроса.</p><button onClick={()=>setPage('search')}>Начать исследование ↗</button></div>}</section><aside className="event-panel"><h3>{event?'Детали этапа':'Журнал событий'}</h3>{event?<><div className={`event-status ${event.status}`}>{statuses[event.status]}</div><h2>{names[event.stage]||event.stage}</h2><p>{event.detail}</p>{event.service_url&&<p>Сервис: {event.service_url}</p>}{event.proxy&&<p>Прокси: {event.proxy}</p>}<small>{new Date(event.at*1000).toLocaleTimeString()}</small><button className="text-button" onClick={()=>setEvent(null)}>← Все события</button></>:current?.events.length?current.events.map(e=><button className="event-row" key={e.id} onClick={()=>setEvent(e)}><span className={`tiny-dot ${e.status}`}/><div><strong>{names[e.stage]||e.stage}</strong><p>{e.detail}</p><small>{new Date(e.at*1000).toLocaleTimeString()}</small></div></button>):<p className="muted">Здесь появятся события выполнения. Выберите узел, чтобы узнать подробности.</p>}</aside></div>
      </div>}
      {page==='catalog'&&<div className="wide-page"><div className="page-heading"><div className="eyebrow">RESOURCE LIBRARY</div><h1>Инструменты для исследования <sup>{resources.length}</sup></h1><p>Каталог из видения проекта. Кандидаты требуют проверки перед подключением.</p></div><div className="catalog-controls"><input aria-label="Найти инструмент" placeholder="⌕  Поиск по названию и описанию" value={filter} onChange={e=>setFilter(e.target.value)}/><select aria-label="Категория" value={category} onChange={e=>setCategory(e.target.value)}><option value="all">Все категории</option>{['search','fetch','proxy','reference','community'].map(c=><option key={c}>{c}</option>)}</select></div><div className="catalog-grid">{shown.map(r=><article className="resource-card" key={r.id}><div><span className="resource-icon">{r.category==='proxy'?'⇄':r.category==='search'?'⌕':'▧'}</span><span className="tag">{r.category}</span></div><h3>{r.name}</h3><div className="resource-description"><ReactMarkdown>{r.description}</ReactMarkdown></div><a href={r.url} target="_blank" rel="noreferrer">Открыть источник ↗</a><small>{r.integration_status} · сведения из каталога</small><button className="text-button" onClick={async()=>{try{await api('/jobs',{kind:'generate',payload:{candidate:r.id}});setPage('control');}catch{setError('Не удалось запустить разработку');}}}>Разработать адаптер ↗</button></article>)}</div>{!shown.length&&<p className="empty-inline">Инструменты не найдены.</p>}</div>}
      {page==='system'&&<div className="wide-page"><div className="page-heading"><div className="eyebrow">RUNTIME</div><h1>Система под наблюдением</h1><p>Подключённые адаптеры, расход локальных бюджетов и диагностика.</p></div><div className="system-grid">{Object.entries(system?.providers||{}).map(([kind,list])=><section className="system-card" key={kind}><div className="eyebrow">{kind}</div><h2>Доступные адаптеры</h2>{list.map(p=><div className="provider-row" key={p}><span className="live-dot"/>{names[p]||p}<small>Настроен</small></div>)}</section>)}<section className="system-card"><div className="eyebrow">QUOTAS</div><h2>Расход за месяц</h2>{system?.quotas.length?system.quotas.map(q=><div className="provider-row" key={q.provider}>{names[q.provider]}<small>{q.used} запросов · {q.period}</small></div>):<p className="muted">Квотируемые API ещё не использовались.</p>}</section></div><h2 className="section-title">Кейсы восстановления</h2>{system?.cases.length?system.cases.map(c=><section className="case-card" key={c.id}><span className="tag">Требует проверки</span><h3>{c.query}</h3><ReactMarkdown>{c.advice}</ReactMarkdown><button className="text-button" onClick={()=>{openRun(c.id);setPage('map');}}>Открыть трассировку ↗</button></section>):<p className="empty-inline">Пока нет неразрешённых кейсов.</p>}</div>}
    </main>
  </div>;
}
