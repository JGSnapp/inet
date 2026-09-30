import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './research.css';
import './control.css';
import './dashboard.css';
import './route.css';
import './modern.css';
import ControlPanel from './ControlPanel';
import { lang, tr } from './i18n';

type Event = {
  id: number;
  stage: string;
  status: string;
  detail: string;
  at: number;
  duration_ms?: number;
  span_id?: string;
  service_url?: string;
  proxy?: string;
  target?: string;
};
type ReflectionEvent = {
  id: number;
  status: string;
  detail: string;
  at: number;
  stage?: string;
  target?: string;
  pipeline?: string;
};
type Reflection = {
  status: string;
  level: number;
  events: ReflectionEvent[];
  has_recovered?: boolean;
  recovered_sources?: { url: string; pipeline: string; snippet?: string }[];
  improvements?: Record<string, unknown>[];
  summary?: {
    events_analyzed: number;
    failures: number;
    unread_sites: number;
    experiments: number;
    recovered?: number;
    alternatives?: number;
    failed_experiments?: number;
  };
};
type Run = {
  id: string;
  query: string;
  mode: string;
  status: string;
  created_at: number;
  parent_id?: string;
  thread_id?: string;
  rerun_of?: string;
  llm_available?: boolean;
  cached?: boolean;
  unique_tools?: boolean;
  deep?: boolean;
  persistence_level?: number;
  call_budget?: { scope?: string; limit: number; used: number; by_kind: Record<string, number> };
  tool_budget?: { scope?: string; limit: number; used: number; by_kind: Record<string, number> };
  reflection?: Reflection;
  events: Event[];
  result?: {
    answer: string;
    synthesis_status?: string;
    synthesis_error?: string;
    provider?: string;
    research_plan?: { objective: string; tasks: { query: string; purpose: string; priority: number }[] };
    research_stats?: {
      subqueries: number;
      discovered_sources: number;
      sites_attempted: number;
      sites_read: number;
      sites_unread?: number;
      domains_read: number;
      importance?: Record<string, number>;
      persistence_level?: number;
      site_attempt_budget?: number;
      agent_messages_used?: number;
      agent_message_limit?: number;
      tool_calls_used?: number;
      tool_call_limit?: number;
      calls_used?: number;
      call_limit?: number;
    };
    sources: { url: string; title: string; snippet: string }[];
  };
};
type ResearchSettings = { persistence_level: number; reflection_enabled: boolean; reflection_level: number };
type Resource = {
  id: string;
  name: string;
  url: string;
  description: string;
  category: string;
  integration_status: string;
};
type System = {
  providers: Record<string, string[]>;
  quotas: { provider: string; used: number; period: string }[];
  cases: { id: string; query: string; advice: string }[];
};
const API = import.meta.env.VITE_API_URL || '';
async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    `${API}/api${path}`,
    body === undefined
      ? undefined
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
  );
  if (!response.ok)
    throw new Error(
      tr(
        `Сервер вернул ${response.status}. Попробуйте ещё раз.`,
        `Server returned ${response.status}. Please try again.`,
      ),
    );
  return response.json();
}
const names: Record<string, string> = {
  router: tr('Маршрутизатор', 'Router'),
  cache: tr('Кэш', 'Cache'),
  httpx: 'HTTPX',
  httpx_mobile: 'Mobile HTTPX',
  trafilatura: 'Trafilatura',
  readability: 'Readability',
  jina: 'Jina Reader',
  duckduckgo: 'DuckDuckGo',
  ddgs: 'DDGS metasearch',
  wikipedia: 'Wikipedia',
  searxng: 'SearXNG',
  tavily: 'Tavily',
  firecrawl: 'Firecrawl',
  deep_strategy: tr('Стратегия доступа', 'Access strategy'),
  recovery: tr('Агент восстановления', 'Recovery agent'),
  synthesis: tr('Синтез ответа', 'Answer synthesis'),
  result: tr('Результат', 'Result'),
  runtime: tr('Исполнение', 'Runtime'),
};
const statuses: Record<string, string> = {
  queued: tr('В очереди', 'Queued'),
  running: tr('В работе', 'Running'),
  completed: tr('Готово', 'Done'),
  success: tr('Успешно', 'Success'),
  failed: tr('Ошибка', 'Error'),
  error: tr('Ошибка', 'Error'),
  skipped: tr('Пропущено', 'Skipped'),
  cancelled: tr('Остановлен', 'Stopped'),
  interrupted: tr('Прерван', 'Interrupted'),
};
function toolName(stage: string) {
  const raw = stage
    .replace(/^deep:/, '')
    .replace(/^managed:/, '')
    .replace(/^agent_search:/, '')
    .replace(/^agent_fetch:/, '');
  return (
    names[raw] ||
    (
      {
        deep_search: tr('Расширенный поиск', 'Extended search'),
        deep_research: tr('Оркестратор исследования', 'Research orchestrator'),
        agent_plan: tr('Агент-планировщик', 'Planner agent'),
        agent_decision: tr('Отбор источников', 'Source selection'),
        agentic_research: tr('Автономный исследователь', 'Autonomous researcher'),
        agent_link_choice: tr('Выбор маршрута ссылки', 'Link route choice'),
        adaptive_pipeline: tr('Конструктор pipeline', 'Pipeline builder'),
      } as Record<string, string>
    )[raw] ||
    raw.replaceAll('_', ' ')
  );
}
function activityVerb(event?: Event) {
  if (!event) return tr('Ожидает следующего действия', 'Waiting for the next step');
  const stage = event.stage;
  if (stage === 'agent_plan') return tr('Продумывает план исследования', 'Planning the research');
  if (stage === 'agent_decision' || stage === 'agent_link_choice')
    return tr('Решает, какие ссылки исследовать', 'Choosing which links to read');
  if (stage.includes('workspace') || stage.includes('repair'))
    return tr('Исправляет код или маршрут', 'Repairing code or route');
  if (stage.includes('development') || stage.includes('generate') || stage.includes('discover'))
    return tr('Разрабатывает или подключает инструмент', 'Building or connecting a tool');
  if (stage.includes('pipeline'))
    return tr('Проектирует и проверяет pipeline', 'Designing and testing a pipeline');
  if (
    stage === 'deep_search' ||
    stage.includes('search') ||
    stage.includes('searxng') ||
    ['duckduckgo', 'ddgs', 'wikipedia'].includes(stage)
  )
    return tr('Ищет источники', 'Searching for sources');
  if (stage === 'synthesis') return tr('Собирает аналитический обзор', 'Writing the analysis');
  if (
    stage.startsWith('deep:') ||
    stage.startsWith('agent_fetch:') ||
    ['httpx', 'curl_cffi', 'jina', 'official', 'playwright', 'playwright_wait', 'browser_agent'].includes(
      stage,
    )
  )
    return tr('Читает выбранный сайт', 'Reading a selected site');
  return event.detail || tr('Выполняет этап', 'Running a step');
}
type NavIconName =
  'menu' | 'close' | 'plus' | 'chat' | 'library' | 'tools' | 'traces' | 'system' | 'automation';
function NavIcon({ name }: { name: NavIconName }) {
  const paths: Record<NavIconName, React.ReactNode> = {
    menu: (
      <>
        <path d="M4 7h16M4 12h16M4 17h16" />
      </>
    ),
    close: (
      <>
        <path d="m6 6 12 12M18 6 6 18" />
      </>
    ),
    plus: (
      <>
        <path d="M12 5v14M5 12h14" />
      </>
    ),
    chat: (
      <>
        <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
      </>
    ),
    library: (
      <>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5z" />
        <path d="M8 7h8M8 11h7" />
      </>
    ),
    tools: (
      <>
        <path d="M14.7 6.3a4 4 0 0 0-5-5L7.4 3.6l3 3L8 9 5 6 2.7 8.3a4 4 0 0 0 5 5L16.4 22l5.6-5.6-8.7-8.7a4 4 0 0 0 1.4-1.4z" />
      </>
    ),
    traces: (
      <>
        <path d="M4 5v5a2 2 0 0 0 2 2h12M14 8l4 4-4 4M8 19h8" />
      </>
    ),
    system: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M8 12h2l1.5-4 2 8 1.5-4h2" />
      </>
    ),
    automation: (
      <>
        <rect x="3" y="3" width="6" height="6" rx="1" />
        <rect x="15" y="3" width="6" height="6" rx="1" />
        <rect x="9" y="15" width="6" height="6" rx="1" />
        <path d="M6 9v3h12V9M12 12v3" />
      </>
    ),
  };
  return (
    <span className="nav-icon" aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {paths[name]}
      </svg>
    </span>
  );
}
function Mark() {
  return <img className="empty-logo" src="/icon.svg" alt="" />;
}
function SettingsPopover({
  settings,
  onChange,
  instruction,
  setInstruction,
  archive,
  setArchive,
  theme,
  setTheme,
  fresh,
  setFresh,
  uniqueTools,
  setUniqueTools,
  mode,
}: {
  settings: ResearchSettings;
  onChange: (next: ResearchSettings) => void;
  instruction: string;
  setInstruction: (value: string) => void;
  archive: boolean;
  setArchive: (value: boolean) => void;
  theme: 'dark' | 'light';
  setTheme: (value: 'dark' | 'light') => void;
  fresh: boolean;
  setFresh: (value: boolean) => void;
  uniqueTools: boolean;
  setUniqueTools: (value: boolean) => void;
  mode: string;
}) {
  return (
    <details className="composer-settings">
      <summary
        aria-label={tr('Настройки исследования', tr('Настройки исследования', 'Research settings'))}
        title={tr('Настройки исследования', tr('Настройки исследования', 'Research settings'))}
      >
        ⚙
      </summary>
      <div className="composer-settings-popover">
        <header>
          <strong>{tr('Настройки исследования', tr('Настройки исследования', 'Research settings'))}</strong>
          <small>
            {tr(
              'Применяются к новым исследованиям',
              tr('Применяются к новым исследованиям', 'Applied to new research'),
            )}
          </small>
        </header>
        <label className="settings-check">
          <span>{tr('Тёмная тема', tr('Тёмная тема', 'Dark theme'))}</span>
          <input
            type="checkbox"
            checked={theme === 'dark'}
            onChange={(e) => setTheme(e.target.checked ? 'dark' : 'light')}
          />
        </label>
        <label className="settings-check">
          <span>{tr('Свежие результаты', tr('Свежие результаты', 'Fresh results'))}</span>
          <input type="checkbox" checked={fresh} onChange={(e) => setFresh(e.target.checked)} />
        </label>
        <label
          className={`settings-check ${mode === 'deep' ? 'setting-disabled' : ''}`}
          title={tr(
            'Не вызывать один инструмент повторно',
            tr('Не вызывать один инструмент повторно', 'Do not call the same tool more than once'),
          )}
        >
          <span>
            {tr('Без повторных инструментов', tr('Без повторных инструментов', 'No repeated tools'))}
          </span>
          <input
            type="checkbox"
            disabled={mode === 'deep'}
            checked={uniqueTools}
            onChange={(e) => setUniqueTools(e.target.checked)}
          />
        </label>
        <label>
          <span>
            {tr('Настойчивость', tr('Настойчивость', 'Persistence'))} <b>{settings.persistence_level}/4</b>
          </span>
          <input
            type="range"
            min="1"
            max="4"
            step="1"
            value={settings.persistence_level}
            onChange={(e) => onChange({ ...settings, persistence_level: Number(e.target.value) })}
          />
        </label>
        <label className="settings-check">
          <span>{tr('Рефлексия после ответа', tr('Рефлексия после ответа', 'Reflect after answer'))}</span>
          <input
            type="checkbox"
            checked={settings.reflection_enabled}
            onChange={(e) => onChange({ ...settings, reflection_enabled: e.target.checked })}
          />
        </label>
        <label className={!settings.reflection_enabled ? 'setting-disabled' : ''}>
          <span>
            {tr('Глубина рефлексии', tr('Глубина рефлексии', 'Reflection depth'))}{' '}
            <b>{settings.reflection_level}/4</b>
          </span>
          <input
            disabled={!settings.reflection_enabled}
            type="range"
            min="1"
            max="4"
            step="1"
            value={settings.reflection_level}
            onChange={(e) => onChange({ ...settings, reflection_level: Number(e.target.value) })}
          />
        </label>
        <label className="settings-check">
          <span>
            {tr('Разрешить снимки Wayback', tr('Разрешить снимки Wayback', 'Allow Wayback snapshots'))}
          </span>
          <input type="checkbox" checked={archive} onChange={(e) => setArchive(e.target.checked)} />
        </label>
        <label className="settings-instruction">
          <span>{tr('Инструкции агенту', tr('Инструкции агенту', 'Agent instructions'))}</span>
          <textarea
            maxLength={2000}
            placeholder={tr(
              'Цели, ограничения, предпочтительные источники…',
              tr('Цели, ограничения, предпочтительные источники…', 'Goals, constraints, preferred sources…'),
            )}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
        </label>
      </div>
    </details>
  );
}

export default function ResearchApp() {
  const [page, setPage] = useState('search');
  const [theme, setTheme] = useState<'dark' | 'light'>(
    () => (localStorage.getItem('inet-theme') as 'dark' | 'light') || 'dark',
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [progressOpen, setProgressOpen] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('search');
  const [fresh, setFresh] = useState(false);
  const [archive, setArchive] = useState(false);
  const [uniqueTools, setUniqueTools] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);
  const [resources, setResources] = useState<Resource[]>([]);
  const [filter, setFilter] = useState('');
  const [category, setCategory] = useState('all');
  const [system, setSystem] = useState<System | null>(null);
  const [event, setEvent] = useState<Event | null>(null);
  const [settings, setSettings] = useState<ResearchSettings>({
    persistence_level: 2,
    reflection_enabled: true,
    reflection_level: 2,
  });
  const current = runs.find((r) => r.id === selected);
  const threadId = current?.thread_id || current?.id;
  const threadRuns = runs
    .filter((r) => (r.thread_id || r.id) === threadId)
    .sort((a, b) => a.created_at - b.created_at);
  const currentSources = current?.result?.sources || [];
  const routeTools = Array.from(
    new Set(
      (current?.events || [])
        .filter(
          (item) =>
            item.status === 'success' && !['router', 'cache', 'synthesis', 'result'].includes(item.stage),
        )
        .map((item) => names[item.stage] || item.stage),
    ),
  );
  const attemptedTools = Array.from(
    new Set(
      (current?.events || []).filter((item) => item.span_id).map((item) => names[item.stage] || item.stage),
    ),
  );
  const failedAttempts = (current?.events || []).filter((item) => item.status === 'error' && item.span_id);
  const activityEvents = (current?.events || []).filter(
    (item) => !['router', 'cache', 'result'].includes(item.stage),
  );
  const liveActivityEvents = activityEvents.reduce<Event[]>((acc, item) => {
    const i = acc.findIndex((x) => (x.span_id || x.stage) === (item.span_id || item.stage));
    if (i >= 0) acc[i] = item;
    else acc.push(item);
    return acc;
  }, []);
  const currentActivity =
    [...liveActivityEvents].reverse().find((item) => item.status === 'running') || activityEvents.at(-1);
  const routeDuration = current?.events?.length
    ? Math.max(
        0,
        Math.round((current.events[current.events.length - 1]?.at || 0) - (current.events[0]?.at || 0)),
      )
    : 0;
  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const [r, s] = await Promise.all([api<Run[]>('/runs'), api<System>('/system')]);
        if (alive) {
          setRuns(r);
          setSystem(s);
          setConnected(true);
        }
      } catch {
        if (alive) setConnected(false);
      }
    }
    refresh();
    api<{ resources: Resource[] }>('/resources')
      .then((x) => {
        if (alive) setResources(x.resources);
      })
      .catch(() => {
        if (alive)
          setError(
            tr(
              'Не удалось загрузить каталог. Проверьте подключение к серверу.',
              'Could not load the catalog. Check the server connection.',
            ),
          );
      });
    api<ResearchSettings>('/research-settings')
      .then((x) => {
        if (alive) setSettings(x);
      })
      .catch(() => {});
    const timer = setInterval(refresh, 1200);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('inet-theme', theme);
  }, [theme]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setProgressOpen(false);
        setSidebarOpen(false);
      }
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, []);
  async function submit(text = query) {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const run = await api<Run>('/runs', {
        query: text,
        mode: mode === 'deep' ? 'search' : mode,
        deep: mode === 'deep',
        fresh,
        allow_archive: archive,
        unique_tools: mode === 'deep' ? false : uniqueTools,
        instruction,
        ...settings,
        lang,
      });
      setRuns((old) => [run, ...old.filter((x) => x.id !== run.id)]);
      setSelected(run.id);
      setQuery('');
      setPage('search');
      setEvent(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : tr('Запрос не отправлен', 'Request was not sent'));
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    if (!current) return;
    try {
      const r = await api<Run>(`/runs/${current.id}/cancel`, {});
      setRuns((old) => old.map((x) => (x.id === r.id ? r : x)));
    } catch {
      setError(tr('Не удалось остановить запрос', 'Could not stop the request'));
    }
  }
  async function resumeRun() {
    if (!current) return;
    try {
      const r = await api<Run>(`/runs/${current.id}/resume`, {});
      setRuns((old) => old.map((x) => (x.id === r.id ? r : x)));
    } catch {
      setError(
        tr(
          'Нет незавершённой контрольной точки. Отправьте новый запрос.',
          'No unfinished checkpoint. Send a new request.',
        ),
      );
    }
  }
  async function saveSettings(next: ResearchSettings) {
    setSettings(next);
    try {
      await api('/research-settings', next);
    } catch {
      setError(tr('Не удалось сохранить настройки исследования', 'Could not save research settings'));
    }
  }
  async function reflect() {
    if (!current) return;
    try {
      const r = await api<Run>(`/runs/${current.id}/reflect`, { level: settings.reflection_level });
      setRuns((old) => old.map((x) => (x.id === r.id ? r : x)));
    } catch {
      setError(tr('Не удалось запустить рефлексию', 'Could not start reflection'));
    }
  }
  async function stopReflection() {
    if (!current) return;
    try {
      const r = await api<Run>(`/runs/${current.id}/reflection/cancel`, {});
      setRuns((old) => old.map((x) => (x.id === r.id ? r : x)));
    } catch {
      setError(tr('Не удалось остановить рефлексию', 'Could not stop reflection'));
    }
  }
  async function askFollowUp() {
    if (!current || !followUp.trim() || busy) return;
    setBusy(true);
    try {
      const r = await api<Run>(`/runs/${current.id}/follow-up`, { question: followUp });
      setRuns((old) => [r, ...old.filter((x) => x.id !== r.id)]);
      setSelected(r.id);
      setFollowUp('');
    } catch {
      setError(tr('Не удалось поставить продолжение в очередь', 'Could not queue the follow-up'));
    } finally {
      setBusy(false);
    }
  }
  async function rerunWithRecovery() {
    if (!current) return;
    try {
      const r = await api<Run>(`/runs/${current.id}/rerun`, {});
      setRuns((old) => [r, ...old.filter((x) => x.id !== r.id)]);
      setSelected(r.id);
    } catch {
      setError(tr('Не удалось перезапустить исследование', 'Could not restart the research'));
    }
  }
  async function retrySynthesis() {
    if (!current || busy) return;
    setBusy(true);
    try {
      const r = await api<Run>(`/runs/${current.id}/synthesize`, {});
      setRuns((old) => old.map((x) => (x.id === r.id ? r : x)));
    } catch {
      setError(
        tr(
          'Модель снова не завершила синтез. Собранные источники сохранены.',
          'The model did not finish the synthesis again. Collected sources are kept.',
        ),
      );
    } finally {
      setBusy(false);
    }
  }
  function openRun(id: string) {
    setSelected(id);
    setEvent(null);
    setProgressOpen(false);
  }
  const shown = resources.filter(
    (r) =>
      (category === 'all' || r.category === category) &&
      `${r.name} ${r.description}`.toLowerCase().includes(filter.toLowerCase()),
  );
  const routeGroups = Object.values(
    (current?.events || [])
      .filter((e) => e.target && e.span_id)
      .reduce<Record<string, { target: string; events: Event[] }>>((groups, item) => {
        const key = item.target!;
        const group = groups[key] || (groups[key] = { target: key, events: [] });
        const index = group.events.findIndex((e) => e.span_id === item.span_id);
        if (index >= 0) group.events[index] = item;
        else group.events.push(item);
        return groups;
      }, {}),
  );
  const active = current?.status === 'running' || current?.status === 'queued';
  return (
    <div className={`research-app ${sidebarOpen ? 'rail-expanded' : 'rail-collapsed'}`}>
      <aside className="rail" aria-hidden={!sidebarOpen}>
        <div className="rail-head">
          <a
            href="/"
            className="wordmark"
            onClick={(e) => {
              e.preventDefault();
              setPage('search');
              setSelected(null);
              setSidebarOpen(false);
            }}
          >
            <img src="/icon.svg" alt="INET" />
            <span>beta</span>
          </a>
          <button
            className="rail-close"
            onClick={() => setSidebarOpen(false)}
            aria-label={tr('Закрыть навигацию', tr('Закрыть навигацию', 'Close navigation'))}
          >
            <NavIcon name="close" />
          </button>
        </div>
        <button
          className="new-research"
          aria-label={tr('Новый чат', tr('Новый чат', 'New chat'))}
          title={tr('Новый чат', tr('Новый чат', 'New chat'))}
          onClick={() => {
            setSelected(null);
            setPage('search');
            setError('');
            setSidebarOpen(false);
          }}
        >
          <NavIcon name="plus" />
          <span>{tr('Новый чат', tr('Новый чат', 'New chat'))}</span>
        </button>
        <nav aria-label={tr('Основная навигация', tr('Основная навигация', 'Main navigation'))}>
          {[
            ['search', 'chat', tr('Чат', 'Chat')],
            ['catalog', 'library', tr('Библиотека', 'Library')],
          ].map(([id, icon, label]) => (
            <button
              key={id}
              title={label}
              aria-label={label}
              className={page === id ? 'nav-active' : ''}
              onClick={() => {
                setPage(id);
                setSidebarOpen(false);
              }}
            >
              <NavIcon name={icon as NavIconName} />
              <b>{label}</b>
            </button>
          ))}
          <div className="nav-section-label">{tr('ИНСТРУМЕНТЫ', tr('ИНСТРУМЕНТЫ', 'TOOLS'))}</div>
          {[
            ['map', 'traces', tr('Маршруты', 'Traces')],
            ['system', 'system', tr('Система', 'System')],
            ['control', 'automation', tr('Автоматизация', 'Automation')],
          ].map(([id, icon, label]) => (
            <button
              key={id}
              title={label}
              aria-label={label}
              className={page === id ? 'nav-active' : ''}
              onClick={() => {
                setPage(id);
                setSidebarOpen(false);
              }}
            >
              <NavIcon name={icon as NavIconName} />
              <b>{label}</b>
              {id === 'map' && runs.some((r) => r.status === 'running') && <i className="live-dot" />}
            </button>
          ))}
        </nav>
        <div className="history-label">
          {tr('НЕДАВНИЕ', tr('НЕДАВНИЕ', 'RECENT'))} <span>{runs.length}</span>
        </div>
        <div className="history">
          {runs.length ? (
            runs.map((r) => (
              <button
                key={r.id}
                className={selected === r.id ? 'selected' : ''}
                onClick={() => {
                  openRun(r.id);
                  setPage('search');
                  setSidebarOpen(false);
                }}
              >
                <span className={`tiny-dot ${r.status}`} />
                <span>{r.query}</span>
              </button>
            ))
          ) : (
            <p>
              {tr(
                'Здесь появятся ваши диалоги.',
                tr('Здесь появятся ваши диалоги.', 'Your conversations will appear here.'),
              )}
            </p>
          )}
        </div>
        <div className="rail-bottom">
          <span className={connected ? 'live-dot' : 'offline-dot'} />
          <span>{connected ? 'Connected' : 'Offline'}</span>
          <small>v0.2</small>
        </div>
      </aside>
      {sidebarOpen && (
        <button
          className="rail-backdrop"
          aria-label={tr('Закрыть навигацию', tr('Закрыть навигацию', 'Close navigation'))}
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <main className="workspace">
        <header className="topbar minimal-topbar">
          <button
            className="brand-menu"
            onClick={() => setSidebarOpen((value) => !value)}
            aria-label={
              sidebarOpen
                ? tr('Закрыть навигацию', 'Close navigation')
                : tr('Открыть навигацию', 'Open navigation')
            }
            title={
              sidebarOpen
                ? tr('Закрыть навигацию', 'Close navigation')
                : tr('Открыть навигацию', 'Open navigation')
            }
          >
            <img className="topbar-logo" src="/icon.svg" alt="INET" />
          </button>
        </header>
        {page === 'control' && <ControlPanel />}
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button aria-label={tr('Закрыть ошибку', 'Dismiss error')} onClick={() => setError('')}>
              ×
            </button>
          </div>
        )}
        {page === 'search' && (
          <div className={`search-page ${current ? 'has-result' : ''}`}>
            {!current ? (
              <div className="welcome-block">
                <h1>{tr('Что хотите узнать?', 'What do you want to know?')}</h1>
              </div>
            ) : (
              <section className="answer-section research-dashboard">
                {threadRuns
                  .filter((run) => run.id !== current.id && run.result)
                  .map((run) => (
                    <article className="chat-turn chat-turn-previous" key={run.id}>
                      <div className="chat-question">{run.query}</div>
                      <div className="chat-answer">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{run.result?.answer || ''}</ReactMarkdown>
                      </div>
                    </article>
                  ))}
                <div className="result-hero">
                  <div className="chat-question current-question">{current.query}</div>
                  <div className="result-actions">
                    {current.result && (
                      <>
                        <a href={`${API}/api/runs/${current.id}/export.md`} download>
                          MD
                        </a>
                        <a href={`${API}/api/runs/${current.id}/export.pdf`} download>
                          PDF
                        </a>
                      </>
                    )}
                  </div>
                </div>
                {threadRuns.length > 1 && (
                  <div className="thread-strip">
                    <small>{tr('ДИАЛОГ', 'CONVERSATION')}</small>
                    {threadRuns.map((run, index) => (
                      <button
                        className={run.id === current.id ? 'selected' : ''}
                        onClick={() => openRun(run.id)}
                        key={run.id}
                      >
                        {index + 1}. {run.query}
                      </button>
                    ))}
                  </div>
                )}
                {['cancelled', 'interrupted'].includes(current.status) && (
                  <button className="text-button" onClick={resumeRun}>
                    {tr('Продолжить с контрольной точки →', 'Resume from checkpoint →')}
                  </button>
                )}
                {active ? (
                  <button className="inline-progress" onClick={() => setProgressOpen(true)}>
                    <span className="progress-icon">
                      <span className="spinner" />
                    </span>
                    <span className="progress-copy">
                      <small>
                        {current.deep
                          ? tr('ГЛУБОКОЕ ИССЛЕДОВАНИЕ', 'DEEP RESEARCH')
                          : tr('ВЕБ-ПОИСК', 'WEB SEARCH')}{' '}
                        · {activityEvents.length} {tr('событий', 'events')}
                      </small>
                      <strong>{activityVerb(currentActivity)}</strong>
                      <span>
                        {currentActivity?.target ||
                          currentActivity?.detail ||
                          tr('Подготовка следующего шага', 'Preparing the next step')}
                      </span>
                      <i className="progress-track">
                        <i />
                      </i>
                    </span>
                    <span className="progress-open">{tr('Подробнее →', tr('Подробнее →', 'Details →'))}</span>
                  </button>
                ) : (
                  <div className="result-layout">
                    <section className="answer-pane">
                      <div className="pane-heading">
                        <span>✳</span>
                        <div>
                          <small>{tr('ОТВЕТ', tr('ОТВЕТ', 'ANSWER'))}</small>
                          <h2>
                            {tr('Результат исследования', tr('Результат исследования', 'Research result'))}
                          </h2>
                        </div>
                      </div>
                      {current.result ? (
                        <article className="answer answer-scroll">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{current.result.answer}</ReactMarkdown>
                        </article>
                      ) : (
                        <p className="empty-inline">
                          {statuses[current.status]}. {current.events[current.events.length - 1]?.detail}
                        </p>
                      )}
                    </section>
                    <aside className="evidence-pane">
                      <div className="pane-heading">
                        <span>↗</span>
                        <div>
                          <small>{tr('ДОКАЗАТЕЛЬСТВА', tr('ДОКАЗАТЕЛЬСТВА', 'EVIDENCE'))}</small>
                          <h2>{tr('Источники', tr('Источники', 'Sources'))}</h2>
                        </div>
                      </div>
                      <div className="route-strip">
                        {current.unique_tools && (
                          <span className="unique-badge">
                            {tr(
                              'Один вызов на инструмент',
                              tr('Один вызов на инструмент', 'One call per tool'),
                            )}
                          </span>
                        )}
                        {routeTools.length ? (
                          routeTools.map((tool, index) => (
                            <React.Fragment key={tool}>
                              <span>{tool}</span>
                              {index < routeTools.length - 1 && <i>→</i>}
                            </React.Fragment>
                          ))
                        ) : (
                          <span>
                            {tr('Маршрут недоступен', tr('Маршрут недоступен', 'Route unavailable'))}
                          </span>
                        )}
                      </div>
                      {current.deep && current.result?.research_stats?.importance && (
                        <div className="importance-strip">
                          <span>
                            {tr('Критичные', tr('Критичные', 'Critical'))}{' '}
                            <b>{current.result.research_stats.importance.critical || 0}</b>
                          </span>
                          <span>
                            {tr('Высокие', tr('Высокие', 'High'))}{' '}
                            <b>{current.result.research_stats.importance.high || 0}</b>
                          </span>
                          <span>
                            {tr('Средние', tr('Средние', 'Medium'))}{' '}
                            <b>{current.result.research_stats.importance.medium || 0}</b>
                          </span>
                          <span>
                            {tr('Низкие', tr('Низкие', 'Low'))}{' '}
                            <b>{current.result.research_stats.importance.low || 0}</b>
                          </span>
                        </div>
                      )}
                      {failedAttempts.length > 0 && (
                        <details className="attempt-details">
                          <summary>
                            <span>!</span>
                            {failedAttempts.length} {tr('неудачных попыток', 'failed attempts')}{' '}
                            <b>{tr('Подробнее', tr('Подробнее', 'Details'))}</b>
                          </summary>
                          <div>
                            {failedAttempts.map((item) => (
                              <article key={item.id}>
                                <strong>{names[item.stage] || item.stage}</strong>
                                <p>{item.detail}</p>
                                <small>
                                  {item.target || current.query}
                                  {item.duration_ms !== undefined ? ` · ${item.duration_ms} ms` : ''}
                                </small>
                              </article>
                            ))}
                          </div>
                        </details>
                      )}
                      <div className="compact-sources">
                        {currentSources.slice(0, failedAttempts.length ? 4 : 6).map((source, index) => (
                          <a href={source.url} key={source.url + index} target="_blank" rel="noreferrer">
                            <b>{index + 1}</b>
                            <div>
                              <small>
                                {(() => {
                                  try {
                                    return new URL(source.url).hostname;
                                  } catch {
                                    return source.url;
                                  }
                                })()}
                              </small>
                              <strong>{source.title}</strong>
                            </div>
                            <span>↗</span>
                          </a>
                        ))}
                      </div>
                      {currentSources.length > (failedAttempts.length ? 4 : 6) && (
                        <p className="more-sources">
                          {currentSources.length - (failedAttempts.length ? 4 : 6)}{' '}
                          {tr(
                            'источников ещё доступны в экспорте',
                            'more sources are available in the export',
                          )}
                        </p>
                      )}
                    </aside>
                    <button className="completed-progress" onClick={() => setProgressOpen(true)}>
                      {tr('Ход исследования', 'View research activity')} · {current.events.length}{' '}
                      {tr('событий', 'events')} <span>→</span>
                    </button>
                  </div>
                )}
                {current.cached && (
                  <div className="cache-note">
                    {tr(
                      '↺ Результат из кэша · без повторного обращения к сервисам',
                      '↺ Cached result · no services were called again',
                    )}
                  </div>
                )}
                {current.result &&
                  (current.result.synthesis_status === 'failed' || current.llm_available === false) && (
                    <div className="recovery-alert">
                      <span>!</span>
                      <div>
                        <strong>
                          {tr('Аналитический синтез не завершён', 'Analysis was not completed')}
                        </strong>
                        <p>
                          {tr(
                            'Источники сохранены отдельно, но сырой текст больше не считается готовым ответом.',
                            'Sources are saved separately, but raw text is not treated as a finished answer.',
                          )}
                        </p>
                      </div>
                      <button disabled={busy} onClick={retrySynthesis}>
                        {busy ? tr('Повторяем…', 'Retrying…') : tr('Повторить синтез', 'Retry synthesis')}
                      </button>
                    </div>
                  )}
                {current.reflection?.has_recovered && (
                  <div className="recovery-alert">
                    <span>!</span>
                    <div>
                      <strong>
                        {tr(
                          'Рефлексия получила доступ к ранее непрочитанным данным',
                          'Reflection reached data that was unreadable before',
                        )}
                      </strong>
                      <p>
                        {tr('Восстановлено источников:', 'Recovered sources:')}{' '}
                        {current.reflection.summary?.recovered ||
                          current.reflection.recovered_sources?.length ||
                          0}
                        {tr(
                          '. Перезапустите исследование, чтобы включить их в новый ответ.',
                          '. Rerun the research to include them in a new answer.',
                        )}
                      </p>
                    </div>
                    <button onClick={rerunWithRecovery}>{tr('Улучшить ответ', 'Improve answer')}</button>
                  </div>
                )}
                {!active && current.reflection && current.reflection.status !== 'disabled' && (
                  <section className={`reflection-panel ${current.reflection.status}`}>
                    <div className="reflection-heading">
                      <div>
                        <small>
                          {tr('ПОСЛЕ ОТВЕТА · УРОВЕНЬ', 'AFTER ANSWER · LEVEL')} {current.reflection.level}/4
                        </small>
                        <h2>
                          {current.reflection.status === 'running' || current.reflection.status === 'queued'
                            ? tr('Рефлексия продолжается', 'Reflection in progress')
                            : tr('Рефлексия агента', 'Agent reflection')}
                        </h2>
                        <p>
                          {tr(
                            'Агент разбирает трассы, сравнивает подходы и live-тестирует улучшения отдельно от уже готового ответа.',
                            'The agent reviews traces, compares approaches and live-tests improvements without touching the finished answer.',
                          )}
                        </p>
                      </div>
                      {['running', 'queued'].includes(current.reflection.status) ? (
                        <button onClick={stopReflection}>{tr('Остановить', 'Stop')}</button>
                      ) : (
                        <button onClick={reflect}>{tr('Запустить снова', 'Run again')}</button>
                      )}
                    </div>
                    {current.reflection.summary && (
                      <div className="reflection-metrics">
                        <span>
                          <b>{current.reflection.summary.events_analyzed}</b> {tr('событий', 'events')}
                        </span>
                        <span>
                          <b>{current.reflection.summary.failures}</b>{' '}
                          {tr('отказов разобрано', 'failures analysed')}
                        </span>
                        <span>
                          <b>{current.reflection.summary.experiments}</b> {tr('экспериментов', 'experiments')}
                        </span>
                        <span>
                          <b>{current.reflection.summary.unread_sites}</b>{' '}
                          {tr('непрочитанных сайтов', 'unread sites')}
                        </span>
                      </div>
                    )}
                    <div className="reflection-feed">
                      {current.reflection.events.length ? (
                        current.reflection.events
                          .slice(-8)
                          .reverse()
                          .map((item) => (
                            <article key={item.id}>
                              <span className={`tiny-dot ${item.status}`} />
                              <div>
                                <strong>
                                  {item.stage === 'pipeline_experiment'
                                    ? tr('Эксперимент с pipeline', 'Pipeline experiment')
                                    : item.stage === 'tool_discovery'
                                      ? tr('Поиск нового инструмента', 'Looking for a new tool')
                                      : item.stage === 'reflection_result'
                                        ? tr('Итог рефлексии', 'Reflection summary')
                                        : tr('Анализ трассировки', 'Trace analysis')}
                                </strong>
                                <p>{item.detail}</p>
                                {item.target && <small>{item.target}</small>}
                              </div>
                            </article>
                          ))
                      ) : (
                        <p>{tr('Рефлексия поставлена в очередь…', 'Reflection queued…')}</p>
                      )}
                    </div>
                  </section>
                )}
                <form
                  className="follow-up"
                  onSubmit={(e) => {
                    e.preventDefault();
                    askFollowUp();
                  }}
                >
                  <textarea
                    aria-label={tr('Уточняющий вопрос', tr('Уточняющий вопрос', 'Follow-up question'))}
                    placeholder={
                      active
                        ? tr(
                            'Задайте уточнение — оно выполнится следующим…',
                            'Ask a follow-up — it will run next…',
                          )
                        : tr('Задайте уточняющий вопрос…', 'Ask a follow-up…')
                    }
                    value={followUp}
                    onChange={(e) => setFollowUp(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        askFollowUp();
                      }
                    }}
                  />
                  <div className="follow-up-actions">
                    <SettingsPopover
                      settings={settings}
                      onChange={saveSettings}
                      instruction={instruction}
                      setInstruction={setInstruction}
                      archive={archive}
                      setArchive={setArchive}
                      theme={theme}
                      setTheme={setTheme}
                      fresh={fresh}
                      setFresh={setFresh}
                      uniqueTools={uniqueTools}
                      setUniqueTools={setUniqueTools}
                      mode={mode}
                    />
                    <button
                      aria-label={tr('Отправить уточнение', tr('Отправить уточнение', 'Send follow-up'))}
                      disabled={!followUp.trim() || busy}
                    >
                      ↑
                    </button>
                  </div>
                </form>
              </section>
            )}
            {!current && (
              <form
                className="research-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <textarea
                  autoFocus
                  aria-label={tr(
                    'Вопрос для исследования',
                    tr('Вопрос для исследования', 'Research question'),
                  )}
                  placeholder={tr('Спросите что угодно…', tr('Спросите что угодно…', 'Ask anything…'))}
                  value={query}
                  maxLength={4000}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      submit();
                    }
                  }}
                />
                <div className="composer-bottom">
                  <select
                    aria-label={tr('Режим исследования', tr('Режим исследования', 'Research mode'))}
                    value={mode}
                    onChange={(e) => {
                      setMode(e.target.value);
                      if (e.target.value === 'deep') setUniqueTools(false);
                    }}
                  >
                    <option value="search">{tr('Быстрый поиск', tr('Быстрый поиск', 'Quick search'))}</option>
                    <option value="deep">
                      {tr('Глубокое исследование', tr('Глубокое исследование', 'Deep research'))}
                    </option>
                  </select>
                  <SettingsPopover
                    settings={settings}
                    onChange={saveSettings}
                    instruction={instruction}
                    setInstruction={setInstruction}
                    archive={archive}
                    setArchive={setArchive}
                    theme={theme}
                    setTheme={setTheme}
                    fresh={fresh}
                    setFresh={setFresh}
                    uniqueTools={uniqueTools}
                    setUniqueTools={setUniqueTools}
                    mode={mode}
                  />
                  <button
                    type="submit"
                    aria-label={tr('Начать исследование', tr('Начать исследование', 'Start research'))}
                    disabled={!query.trim() || busy}
                  >
                    ↑
                  </button>
                </div>
              </form>
            )}
          </div>
        )}
        {page === 'map' && (
          <div className="wide-page">
            <div className="page-heading">
              <div className="eyebrow">{tr('КАРТА МАРШРУТОВ', tr('КАРТА МАРШРУТОВ', 'ROUTE MAP'))}</div>
              <h1>{tr('Маршруты запросов и сайтов', 'Query and site routes')}</h1>
              <p>
                {tr(
                  'Каждая строка показывает конкретную цель и фактический порядок инструментов. Полный журнал остаётся обычным списком справа.',
                  'Each row shows one target and the actual order of tools. The full log stays as a list on the right.',
                )}
              </p>
            </div>
            <select
              className="run-select"
              aria-label={tr('Запрос для карты', 'Request to map')}
              value={selected || ''}
              onChange={(e) => openRun(e.target.value)}
            >
              <option value="">{tr('Выберите исследование', 'Choose a research run')}</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.query}
                </option>
              ))}
            </select>
            <div className="map-layout route-map-layout">
              <section className="map-canvas route-canvas">
                <div className="map-label">
                  <span className={active ? 'live-dot' : 'offline-dot'} />{' '}
                  {current ? statuses[current.status] : tr('Ожидание запроса', 'Waiting for a request')}
                  <span>
                    {routeGroups.length} {tr('МАРШРУТОВ', 'ROUTES')}
                  </span>
                </div>
                {routeGroups.length ? (
                  <div className="route-graph">
                    {routeGroups.map((group, index) => (
                      <article key={group.target + index}>
                        <div className="route-target">
                          <small>
                            {group.target.startsWith('http')
                              ? tr('САЙТ', 'SITE')
                              : tr('ПОИСКОВЫЙ ЗАПРОС', 'SEARCH QUERY')}
                          </small>
                          <strong>{group.target}</strong>
                        </div>
                        <div className="route-chain">
                          {group.events.map((item, i) => (
                            <React.Fragment key={item.span_id || i}>
                              {i > 0 && <span className="route-arrow">→</span>}
                              <button onClick={() => setEvent(item)} className={`route-node ${item.status}`}>
                                <b>{toolName(item.stage)}</b>
                                <small>
                                  {statuses[item.status] || item.status}
                                  {item.duration_ms !== undefined
                                    ? ` · ${item.duration_ms} ${tr('мс', 'ms')}`
                                    : ''}
                                </small>
                              </button>
                            </React.Fragment>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="map-empty">
                    <Mark />
                    <h2>{tr('Маршруты ещё не появились', 'No routes yet')}</h2>
                    <p>
                      {tr(
                        'Они строятся из реальных вызовов поисковых и parsing-инструментов.',
                        'They are built from real calls to search and parsing tools.',
                      )}
                    </p>
                  </div>
                )}
              </section>
              <aside className="event-panel">
                <h3>{event ? tr('Детали вызова', 'Call details') : tr('Журнал событий', 'Event log')}</h3>
                {event ? (
                  <>
                    <div className={`event-status ${event.status}`}>{statuses[event.status]}</div>
                    <h2>{toolName(event.stage)}</h2>
                    <p>{event.detail}</p>
                    {event.target && (
                      <p>
                        {tr('Цель', 'Target')}: {event.target}
                      </p>
                    )}
                    {event.service_url && (
                      <p>
                        {tr('Сервис', 'Service')}: {event.service_url}
                      </p>
                    )}
                    <small>{new Date(event.at * 1000).toLocaleTimeString()}</small>
                    <button className="text-button" onClick={() => setEvent(null)}>
                      {tr('← Журнал списком', '← Log as list')}
                    </button>
                  </>
                ) : current?.events.length ? (
                  current.events
                    .slice()
                    .reverse()
                    .map((e) => (
                      <button className="event-row" key={e.id} onClick={() => setEvent(e)}>
                        <span className={`tiny-dot ${e.status}`} />
                        <div>
                          <strong>{toolName(e.stage)}</strong>
                          <p>{e.detail}</p>
                          <small>{new Date(e.at * 1000).toLocaleTimeString()}</small>
                        </div>
                      </button>
                    ))
                ) : (
                  <p className="muted">{tr('Событий пока нет.', 'No events yet.')}</p>
                )}
              </aside>
            </div>
          </div>
        )}
        {page === 'catalog' && (
          <div className="wide-page">
            <div className="page-heading">
              <div className="eyebrow">
                {tr('БИБЛИОТЕКА РЕСУРСОВ', tr('БИБЛИОТЕКА РЕСУРСОВ', 'RESOURCE LIBRARY'))}
              </div>
              <h1>
                {tr('Инструменты для исследования', 'Research tools')} <sup>{resources.length}</sup>
              </h1>
              <p>
                {tr(
                  'Каталог из видения проекта. Кандидаты требуют проверки перед подключением.',
                  'Catalog of free tools. Candidates are verified before they are connected.',
                )}
              </p>
            </div>
            <div className="catalog-controls">
              <input
                aria-label={tr('Найти инструмент', 'Find a tool')}
                placeholder={tr(
                  tr('⌕  Поиск по названию и описанию', '⌕  Search by name and description'),
                  '⌕  Search by name and description',
                )}
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <select
                aria-label={tr('Категория', 'Category')}
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="all">{tr('Все категории', 'All categories')}</option>
                {['search', 'fetch', 'proxy', 'reference', 'community'].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="catalog-grid">
              {shown.map((r) => (
                <article className="resource-card" key={r.id}>
                  <div>
                    <span className="resource-icon">
                      {r.category === 'proxy' ? '⇄' : r.category === 'search' ? '⌕' : '▧'}
                    </span>
                    <span className="tag">{r.category}</span>
                  </div>
                  <h3>{r.name}</h3>
                  <div className="resource-description">
                    <ReactMarkdown>{r.description}</ReactMarkdown>
                  </div>
                  <a href={r.url} target="_blank" rel="noreferrer">
                    {tr('Открыть источник ↗', 'Open source ↗')}
                  </a>
                  <small>
                    {r.integration_status} · {tr('сведения из каталога', 'from catalog')}
                  </small>
                  <button
                    className="text-button"
                    onClick={async () => {
                      try {
                        await api('/jobs', { kind: 'generate', payload: { candidate: r.id } });
                        setPage('control');
                      } catch {
                        setError(tr('Не удалось запустить разработку', 'Could not start development'));
                      }
                    }}
                  >
                    {tr('Разработать адаптер ↗', 'Build adapter ↗')}
                  </button>
                </article>
              ))}
            </div>
            {!shown.length && (
              <p className="empty-inline">{tr('Инструменты не найдены.', 'No tools found.')}</p>
            )}
          </div>
        )}
        {page === 'system' && (
          <div className="wide-page">
            <div className="page-heading">
              <div className="eyebrow">{tr('СРЕДА', tr('СРЕДА', 'RUNTIME'))}</div>
              <h1>{tr('Система под наблюдением', 'System status')}</h1>
              <p>
                {tr(
                  'Подключённые адаптеры, расход локальных бюджетов и диагностика.',
                  'Connected adapters, local budget usage and diagnostics.',
                )}
              </p>
            </div>
            <div className="system-grid">
              {Object.entries(system?.providers || {}).map(([kind, list]) => (
                <section className="system-card" key={kind}>
                  <div className="eyebrow">{kind}</div>
                  <h2>{tr('Доступные адаптеры', 'Available adapters')}</h2>
                  {list.map((p) => (
                    <div className="provider-row" key={p}>
                      <span className="live-dot" />
                      {names[p] || p}
                      <small>{tr('Настроен', 'Configured')}</small>
                    </div>
                  ))}
                </section>
              ))}
              <section className="system-card">
                <div className="eyebrow">{tr('КВОТЫ', tr('КВОТЫ', 'QUOTAS'))}</div>
                <h2>{tr('Расход за месяц', 'Usage this month')}</h2>
                {system?.quotas.length ? (
                  system.quotas.map((q) => (
                    <div className="provider-row" key={q.provider}>
                      {names[q.provider]}
                      <small>
                        {q.used} {tr('запросов', 'requests')} · {q.period}
                      </small>
                    </div>
                  ))
                ) : (
                  <p className="muted">
                    {tr('Квотируемые API ещё не использовались.', 'Quota-based APIs have not been used yet.')}
                  </p>
                )}
              </section>
            </div>
            <h2 className="section-title">{tr('Кейсы восстановления', 'Recovery cases')}</h2>
            {system?.cases.length ? (
              system.cases.map((c) => (
                <section className="case-card" key={c.id}>
                  <span className="tag">{tr('Требует проверки', 'Needs review')}</span>
                  <h3>{c.query}</h3>
                  <ReactMarkdown>{c.advice}</ReactMarkdown>
                  <button
                    className="text-button"
                    onClick={() => {
                      openRun(c.id);
                      setPage('map');
                    }}
                  >
                    {tr('Открыть трассировку ↗', 'Open trace ↗')}
                  </button>
                </section>
              ))
            ) : (
              <p className="empty-inline">{tr('Пока нет неразрешённых кейсов.', 'No open cases.')}</p>
            )}
          </div>
        )}
        {progressOpen && current && (
          <div
            className="progress-overlay"
            role="dialog"
            aria-modal="true"
            aria-label={tr('Ход исследования', tr('Ход исследования', 'Research activity'))}
            onMouseDown={() => setProgressOpen(false)}
          >
            <section className="progress-drawer" onMouseDown={(e) => e.stopPropagation()}>
              <header>
                <div>
                  <small>
                    {active
                      ? tr('ИССЛЕДОВАНИЕ ИДЁТ', 'RESEARCH IN PROGRESS')
                      : tr('ИССЛЕДОВАНИЕ ЗАВЕРШЕНО', 'RESEARCH COMPLETE')}
                  </small>
                  <h2>{tr('Ход исследования', tr('Ход исследования', 'Research activity'))}</h2>
                </div>
                <button
                  onClick={() => setProgressOpen(false)}
                  aria-label={tr(
                    'Закрыть ход исследования',
                    tr('Закрыть ход исследования', 'Close activity'),
                  )}
                >
                  ×
                </button>
              </header>
              <div className="drawer-progress">
                <div>
                  <span className={active ? 'spinner' : 'result-check'}>{active ? '' : '✓'}</span>
                  <div>
                    <strong>
                      {active
                        ? activityVerb(currentActivity)
                        : tr('Исследование завершено', 'Research completed')}
                    </strong>
                    <small>
                      {current.events.length} {tr('событий', 'events')} ·{' '}
                      {attemptedTools.length || routeTools.length} {tr('инструментов', 'tools')} ·{' '}
                      {failedAttempts.length} {tr('с ошибкой', 'failed')}
                    </small>
                  </div>
                </div>
                <i className={active ? 'is-active' : ''}>
                  <i />
                </i>
              </div>
              <div className="drawer-metrics">
                <span>
                  <b>{current.result?.research_stats?.sites_read ?? currentSources.length}</b>{' '}
                  {tr('сайтов прочитано', tr('сайтов прочитано', 'sites read'))}
                </span>
                <span>
                  <b>
                    {current.call_budget?.used ?? 0}/{current.call_budget?.limit ?? 120}
                  </b>{' '}
                  agent messages
                </span>
                <span>
                  <b>{current.tool_budget?.used ?? attemptedTools.length}</b>{' '}
                  {tr('вызовов инструментов', tr('вызовов инструментов', 'tool calls'))}
                </span>
                <span>
                  <b>{routeDuration || '—'}</b> {tr('секунд', tr('секунд', 'seconds'))}
                </span>
              </div>
              <div className="event-list">
                <div className="event-list-heading">
                  <strong>{tr('Все события', tr('Все события', 'All events'))}</strong>
                  {active && (
                    <button onClick={cancel}>
                      {tr('Остановить исследование', tr('Остановить исследование', 'Stop research'))}
                    </button>
                  )}
                </div>
                {current.events.length ? (
                  current.events
                    .slice()
                    .reverse()
                    .map((item) => (
                      <details className={`event-detail ${item.status}`} key={item.id}>
                        <summary>
                          <span className={`tiny-dot ${item.status}`} />
                          <div>
                            <strong>{activityVerb(item)}</strong>
                            <small>
                              {toolName(item.stage)} · {new Date(item.at * 1000).toLocaleTimeString()}
                            </small>
                          </div>
                          <span>
                            {item.duration_ms !== undefined
                              ? `${item.duration_ms} ms`
                              : tr('Подробнее', 'Details')}
                            ⌄
                          </span>
                        </summary>
                        <div className="event-detail-body">
                          <p>{item.detail}</p>
                          {item.target && (
                            <dl>
                              <dt>{tr('Цель', tr('Цель', 'Target'))}</dt>
                              <dd>{item.target}</dd>
                            </dl>
                          )}
                          {item.service_url && (
                            <dl>
                              <dt>{tr('Сервис', tr('Сервис', 'Service'))}</dt>
                              <dd>{item.service_url}</dd>
                            </dl>
                          )}
                          {item.proxy && (
                            <dl>
                              <dt>{tr('Прокси', tr('Прокси', 'Proxy'))}</dt>
                              <dd>{item.proxy}</dd>
                            </dl>
                          )}
                          {item.span_id && (
                            <dl>
                              <dt>Span ID</dt>
                              <dd>{item.span_id}</dd>
                            </dl>
                          )}
                          <dl>
                            <dt>{tr('Статус', tr('Статус', 'Status'))}</dt>
                            <dd>{item.status}</dd>
                          </dl>
                        </div>
                      </details>
                    ))
                ) : (
                  <p className="empty-inline">
                    {tr(
                      'Ожидание первого события…',
                      tr('Ожидание первого события…', 'Waiting for the first event…'),
                    )}
                  </p>
                )}
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
