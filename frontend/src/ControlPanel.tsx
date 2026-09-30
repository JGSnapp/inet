import React, { useEffect, useState } from 'react';
import './control-dashboard.css';
import { tr } from './i18n';
type Job = {
  id: string;
  kind: string;
  status: string;
  error?: string;
  events: { stage: string; detail: string; status: string }[];
  result?: unknown;
};
type Version = {
  id: string;
  status: string;
  digest: string;
  spec: { name: string; code: string; requirements: string[] };
  diff: string;
  successes: number;
  failures: number;
};
type ManagedService = {
  name: string;
  status: string;
  healthy: boolean;
  image: string;
  resolved_image?: string;
  memory_bytes?: number;
  memory_limit_bytes?: number;
  cpu_percent?: number;
  restart_count?: number;
};
type ManagedProject = {
  name: string;
  file_count: number;
  bytes: number;
  updated_at?: number;
  snapshots: { id: string; created_at: number }[];
  spec: { repository?: string; runtime_image: string; service?: string };
};
type PipelineVersion = {
  id: string;
  status: string;
  successes: number;
  failures: number;
  spec: { name: string; domain: string; stages: { id: string; kind: string; url: string }[] };
};
type ApiCandidate = {
  id: string;
  endpoint: string;
  verification_status: string;
  cost_status: string;
  license_status: string;
  evidence: string[];
};
type Control = {
  jobs: Job[];
  versions: Version[];
  evaluations: {
    version: string;
    passed: number;
    count: number;
    eligible: boolean;
    details: { query: string; passed: boolean; reason: string }[];
  }[];
  pipeline_versions: PipelineVersion[];
  pipeline_evaluations: { version: string; eligible: boolean; stage?: string; diagnostics: unknown[] }[];
  api_candidates: ApiCandidate[];
  proxies: { id: string; healthy: boolean; latency_ms: number; expires_at: number }[];
  connectors: { id: string; mode: string; endpoint: string; key_configured: boolean; enabled: boolean }[];
  managed_services: ManagedService[];
  managed_projects: ManagedProject[];
  policies: Record<string, unknown>[];
  remote_quotas: { provider: string; remaining: number }[];
  crawls: { id: string; max_pages: number; interval_seconds: number }[];
  datasets: { id: string; plan: string; count: number }[];
  audit: { action: string; version: string; at: number }[];
};
const API = import.meta.env.VITE_API_URL || '';
async function request<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(
    API + '/api' + path,
    body === undefined
      ? undefined
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
  );
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
const labels: Record<string, string> = {
  queued: tr('В очереди', 'Queued'),
  running: tr('Выполняется', 'Running'),
  completed: tr('Завершено', 'Done'),
  failed: tr('Ошибка', 'Error'),
  blocked: tr('Ожидает настройки', 'Needs setup'),
  candidate: tr('Кандидат', 'Candidate'),
  canary: tr('Пробная версия', 'Canary'),
  active: tr('Активна', 'Active'),
  rolled_back: tr('Откачена', 'Rolled back'),
  rejected: tr('Не прошла проверку', 'Failed checks'),
  tested: tr('Проверена', 'Verified'),
};
const connectorExample = {
  id: 'my-search',
  mode: 'search',
  endpoint: 'https://api.example.com/search',
  method: 'POST',
  query_param: 'query',
  sources_field: 'results',
  url_field: 'url',
  title_field: 'title',
  snippet_field: 'content',
  monthly_limit: 100,
  cost: 1,
};
const policyExample = {
  domain: 'example.com',
  timeout: 20,
  wait_selector: 'body',
  min_chars: 100,
  preferred: ['httpx'],
  blocked_markers: ['verify you are human', 'access denied'],
  official_urls: [],
  extractors: { title: 'h1' },
};
const crawlExample = {
  id: 'my-monitor',
  urls: ['https://example.com'],
  max_pages: 10,
  follow_links: false,
  interval_seconds: 0,
  enabled: true,
};
const projectExample = {
  name: 'my-engine',
  runtime_image: 'inet-sandbox-workspace:local',
  repository: 'https://github.com/owner/repository.git',
  revision: 'main',
  files: {},
  service: '',
  test_commands: [{ argv: ['python', '-m', 'pytest', '-q'], timeout: 300, network: false }],
  memory_mb: 1024,
  cpus: 1,
  pids: 256,
};
export default function ControlPanel() {
  const [data, setData] = useState<Control | null>(null),
    [tab, setTab] = useState('jobs'),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false);
  const [discovery, setDiscovery] = useState('web scraping language:Python stars:>100');
  const [pipelineUrl, setPipelineUrl] = useState('https://example.com/');
  const [json, setJson] = useState(JSON.stringify(connectorExample, null, 2)),
    [key, setKey] = useState(''),
    [provider, setProvider] = useState('tavily');
  const [policy, setPolicy] = useState(JSON.stringify(policyExample, null, 2)),
    [crawl, setCrawl] = useState(JSON.stringify(crawlExample, null, 2));
  const [project, setProject] = useState(JSON.stringify(projectExample, null, 2)),
    [repairProject, setRepairProject] = useState(''),
    [repairIssue, setRepairIssue] = useState('');
  const [sources, setSources] = useState(
    'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt',
  );
  const [sandbox, setSandbox] = useState(tr('Проверка…', 'Checking…'));
  const [adapter, setAdapter] = useState(
    JSON.stringify(
      {
        name: 'my-adapter',
        mode: 'fetch',
        description: '',
        code: 'def run(query, limit):\n    raise NotImplementedError("Implement adapter")',
        requirements: [],
      },
      null,
      2,
    ),
  );
  useEffect(() => {
    let live = true;
    const refresh = async () => {
      try {
        const d = await request<Control>('/control');
        if (live) setData(d);
      } catch (e) {
        if (live) setError(String(e));
      }
    };
    refresh();
    request<{ status: string }>('/sandbox/health')
      .then((r) => {
        if (live) setSandbox(r.status === 'ok' ? tr('Готова', 'Ready') : r.status);
      })
      .catch(() => {
        if (live) setSandbox(tr('Недоступна', 'Unavailable'));
      });
    const timer = setInterval(refresh, 2000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);
  async function action(path: string, body: unknown) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await request(path, body);
      setData(await request<Control>('/control'));
      setNotice(
        tr('Сохранено. Ход выполнения отражается в журнале.', 'Saved. Progress appears in the job log.'),
      );
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function parsed(path: string, value: string, extra?: Record<string, unknown>) {
    try {
      await action(path, extra ? { spec: JSON.parse(value), ...extra } : JSON.parse(value));
    } catch {
      setError(tr('Некорректный JSON', 'Invalid JSON'));
    }
  }
  const job = (kind: string, payload: Record<string, unknown> = {}) => action('/jobs', { kind, payload });
  const recentJobs = data?.jobs.slice(0, 12) || [];
  const latestPipelines = (data?.pipeline_versions || []).filter(
    (pipeline, index, all) => all.findIndex((item) => item.spec.domain === pipeline.spec.domain) === index,
  );
  const completedJobs = data?.jobs.filter((item) => item.status === 'completed').length || 0;
  const failedJobs = data?.jobs.filter((item) => ['failed', 'blocked'].includes(item.status)).length || 0;
  return (
    <div className="wide-page control-page">
      <div className="page-heading">
        <div className="eyebrow">{tr('АВТОНОМНЫЕ ОПЕРАЦИИ', 'AUTONOMOUS OPERATIONS')}</div>
        <h1>{tr('Лаборатория инструментов', 'Tool lab')}</h1>
        <p>
          {tr(
            'От обнаружения кандидата до проверенной версии в рабочем маршруте.',
            'From discovering a candidate to a verified version in the working route.',
          )}
        </p>
      </div>
      <div className="control-status">
        {tr('Песочница:', 'Sandbox:')} <strong>{sandbox}</strong>
        <span>
          {tr('Заданий в очереди', 'Jobs queued')}:{' '}
          {data?.jobs.filter((j) => j.status === 'queued').length || 0}
        </span>
      </div>
      <div className="control-tabs" role="tablist">
        {[
          ['jobs', tr('Очередь', 'Queue')],
          ['versions', tr('Версии', 'Versions')],
          ['pipelines', tr('Repair-loop', 'Repair loop')],
          ['services', tr('Инструменты', 'Tools')],
          ['projects', tr('Проекты', 'Projects')],
          ['proxies', tr('Прокси', 'Proxies')],
          ['connectors', tr('Подключения', 'Connections')],
          ['policies', tr('Правила сайтов', 'Site rules')],
          ['crawls', tr('Парсинг', 'Crawling')],
        ].map(([id, label]) => (
          <button
            role="tab"
            aria-selected={tab === id}
            key={id}
            onClick={() => {
              setTab(id);
              setNotice('');
              setError('');
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <p className="control-notice" role="status">
          {notice}
        </p>
      )}
      {tab === 'jobs' && (
        <>
          <div className="automation-overview">
            <div>
              <small>{tr('ВСЕГО', 'TOTAL')}</small>
              <strong>{data?.jobs.length || 0}</strong>
              <span>{tr('заданий', 'jobs')}</span>
            </div>
            <div>
              <small>{tr('УСПЕШНО', 'SUCCEEDED')}</small>
              <strong>{completedJobs}</strong>
              <span>{tr('проверок', 'checks')}</span>
            </div>
            <div>
              <small>{tr('ТРЕБУЮТ ВНИМАНИЯ', 'NEED ATTENTION')}</small>
              <strong>{failedJobs}</strong>
              <span>{tr('с диагностикой', 'with diagnostics')}</span>
            </div>
            <div>
              <small>{tr('В ОЧЕРЕДИ', 'QUEUED')}</small>
              <strong>
                {data?.jobs.filter((j) => ['queued', 'running'].includes(j.status)).length || 0}
              </strong>
              <span>{tr('сейчас', 'now')}</span>
            </div>
          </div>
          <section className="system-card discovery-card">
            <div>
              <h2>{tr('Найти и подключить инструмент', 'Find and connect a tool')}</h2>
              <p className="muted">
                {tr(
                  'Discovery проверяет репозитории, затем отправляет кандидата в изолированную разработку.',
                  'Discovery checks repositories, then sends a candidate to isolated development.',
                )}
              </p>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                job('discover', { query: discovery, integrate: true });
              }}
              className="control-inline"
            >
              <input
                aria-label={tr(
                  tr('Запрос обнаружения инструментов', 'Tool discovery query'),
                  'Tool discovery query',
                )}
                value={discovery}
                onChange={(e) => setDiscovery(e.target.value)}
              />
              <button disabled={busy || !discovery.trim()}>{tr('Запустить', 'Run')}</button>
            </form>
          </section>
          <div className="section-heading">
            <div>
              <h2>{tr('Последние задания', 'Recent jobs')}</h2>
              <p>
                {tr(
                  'Выполняющиеся операции раскрываются автоматически и обновляются каждые 2 секунды.',
                  'Running operations expand automatically and refresh every 2 seconds.',
                )}
              </p>
            </div>
            <div className="control-actions">
              <button disabled={busy} onClick={() => job('metadata')}>
                {tr('Обновить метаданные', 'Refresh metadata')}
              </button>
              <button disabled={busy} onClick={() => job('quotas')}>
                {tr('Проверить квоты', 'Check quotas')}
              </button>
            </div>
          </div>
          <div className="jobs-grid">
            {recentJobs.length ? (
              recentJobs.map((j) => (
                <details className="job-card" key={j.id} open={j.status === 'running' ? true : undefined}>
                  <summary>
                    <span className={'job-kind-icon ' + j.status}>
                      {j.status === 'completed'
                        ? '✓'
                        : j.status === 'running'
                          ? '◌'
                          : j.status === 'failed'
                            ? '!'
                            : '◇'}
                    </span>
                    <div>
                      <b>
                        {j.kind}
                        {j.status === 'running' ? ' · LIVE' : ''}
                      </b>
                      <small>{j.events.at(-1)?.detail || j.id.slice(0, 8)}</small>
                    </div>
                    <span className={'tag ' + j.status}>{labels[j.status] || j.status}</span>
                  </summary>
                  {j.error && <p className="job-error">{j.error}</p>}
                  {j.events.map((e, i) => (
                    <p className="job-event" key={i}>
                      <b>{e.stage}</b> {e.detail}
                    </p>
                  ))}
                  {j.result !== undefined && <pre>{JSON.stringify(j.result, null, 2)}</pre>}
                </details>
              ))
            ) : (
              <p className="empty-inline">{tr('Пока нет заданий.', 'No jobs yet.')}</p>
            )}
          </div>
        </>
      )}
      {tab === 'versions' && (
        <>
          <details className="system-card">
            <summary>
              {tr('Добавить адаптер или новую ревизию вручную', 'Add an adapter or a new revision manually')}
            </summary>
            <p className="muted">
              {tr(
                'Контракт: run(query, limit) возвращает content/status/final_url/sources для fetch либо sources для search. Зависимости фиксируются как package==version. Для ревизии укажите parent.',
                'Contract: run(query, limit) returns content/status/final_url/sources for fetch or sources for search. Pin dependencies as package==version. Set parent for a revision.',
              )}
            </p>
            <textarea
              className="json-editor"
              aria-label={tr(tr('Спецификация адаптера', 'Adapter specification'), 'Adapter specification')}
              value={adapter}
              onChange={(e) => setAdapter(e.target.value)}
            />
            <button className="control-primary" disabled={busy} onClick={() => parsed('/versions', adapter)}>
              {tr('Создать кандидата', 'Create candidate')}
            </button>
          </details>
          {data?.versions.map((v) => (
            <section className="system-card version-card" key={v.id}>
              <div className="version-heading">
                <h2>{v.spec.name}</h2>
                <span className="tag">{labels[v.status] || v.status}</span>
              </div>
              <small>
                {v.id} · {v.successes} {tr('успехов', 'successes')} / {v.failures} {tr('ошибок', 'errors')}
              </small>
              <div className="control-actions">
                <button disabled={busy} onClick={() => job('evaluate', { version: v.id, promote: true })}>
                  {tr('Запустить испытания', 'Run tests')}
                </button>
                <button
                  disabled={busy || !data.evaluations.some((e) => e.version === v.id && e.eligible)}
                  onClick={() => action(`/versions/${v.id}/promote`, {})}
                >
                  {tr('Продвинуть', 'Promote')}
                </button>
                <button
                  disabled={busy || !['active', 'canary'].includes(v.status)}
                  onClick={() => action(`/versions/${v.id}/rollback`, {})}
                >
                  {tr('Откатить', 'Roll back')}
                </button>
              </div>
              <details>
                <summary>{tr('Код и изменения', 'Code and changes')}</summary>
                <pre>{v.spec.code}</pre>
                <pre>{v.diff}</pre>
                <p>
                  {v.spec.requirements.join(', ') ||
                    tr('Без дополнительных зависимостей', 'No extra dependencies')}
                </p>
              </details>
              {data.evaluations
                .filter((e) => e.version === v.id)
                .map((e) => (
                  <details key={e.version}>
                    <summary>
                      {tr('Результаты', 'Results')}: {e.passed}/{e.count}
                    </summary>
                    {e.details.map((d, i) => (
                      <p key={i}>
                        {d.passed ? '✓' : '×'} {d.query} {d.reason}
                      </p>
                    ))}
                  </details>
                ))}
            </section>
          ))}
          {!data?.versions.length && (
            <p className="empty-inline">
              {tr(
                'Адаптеры появятся после разработки кандидатов или ручного добавления.',
                'Adapters appear after candidates are developed or added manually.',
              )}
            </p>
          )}
        </>
      )}
      {tab === 'services' && (
        <>
          <section className="system-card">
            <h2>{tr('Управляемые инструменты', 'Managed tools')}</h2>
            <p className="muted">
              {tr(
                'Агент разворачивает сервисные инструменты в изолированной Docker-сети, ограничивает CPU, RAM и PID, проверяет готовность и автоматически перезапускает сбойные экземпляры.',
                'The agent deploys service tools in an isolated Docker network, limits CPU, RAM and PIDs, checks readiness and restarts failed instances automatically.',
              )}
            </p>
            <div className="control-actions">
              <button disabled={busy} onClick={() => job('provision', { profile: 'searxng' })}>
                {tr('Поднять SearXNG', 'Start SearXNG')}
              </button>
              <button disabled={busy} onClick={() => job('services')}>
                {tr('Обновить состояние', 'Refresh status')}
              </button>
            </div>
          </section>
          {data?.managed_services.map((s) => (
            <section className="case-card" key={s.name}>
              <h3>{s.name}</h3>
              <p>{s.image}</p>
              <span className="tag">
                {s.status} · {s.healthy ? 'healthy' : 'unhealthy'}
              </span>
              <p className="muted">
                RAM {Math.round((s.memory_bytes || 0) / 1048576)} /{' '}
                {Math.round((s.memory_limit_bytes || 0) / 1048576)} MB · CPU {s.cpu_percent || 0}% ·
                {tr('перезапусков', 'restarts')} {s.restart_count || 0}
              </p>
              <div className="control-actions">
                <button disabled={busy} onClick={() => action(`/services/${s.name}/restart`, {})}>
                  {tr('Перезапустить', 'Restart')}
                </button>
                <button
                  disabled={busy || s.status !== 'running'}
                  onClick={() => action(`/services/${s.name}/stop`, {})}
                >
                  {tr('Остановить', 'Stop')}
                </button>
              </div>
            </section>
          ))}
          {!data?.managed_services.length && (
            <p className="empty-inline">
              {tr('Постоянные инструменты ещё не развёрнуты.', 'No persistent tools deployed yet.')}
            </p>
          )}
        </>
      )}
      {tab === 'projects' && (
        <>
          <section className="system-card">
            <h2>{tr('Редактируемые проекты и движки', 'Editable projects and engines')}</h2>
            <p className="muted">
              {tr(
                'Исходники хранятся в изолированном volume. Перед каждым изменением создаётся snapshot; тесты идут с лимитами CPU/RAM и без сети по умолчанию. Неуспешная правка автоматически откатывается.',
                'Sources live in an isolated volume. A snapshot is taken before every change; tests run with CPU/RAM limits and no network by default. A failed edit is rolled back automatically.',
              )}
            </p>
            <textarea
              className="json-editor"
              aria-label={tr(
                tr('Спецификация управляемого проекта', 'Managed project specification'),
                'Managed project specification',
              )}
              value={project}
              onChange={(e) => setProject(e.target.value)}
            />
            <button className="control-primary" disabled={busy} onClick={() => parsed('/projects', project)}>
              {tr('Создать или подключить проект', 'Create or connect a project')}
            </button>
          </section>
          <section className="system-card">
            <h2>{tr('Автономное исправление', 'Autonomous repair')}</h2>
            <div className="control-inline">
              <select
                aria-label={tr(tr('Проект', 'Project'), 'Project')}
                value={repairProject}
                onChange={(e) => setRepairProject(e.target.value)}
              >
                <option value="">{tr('Выберите проект', 'Choose a project')}</option>
                {data?.managed_projects.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}
                  </option>
                ))}
              </select>
              <input
                aria-label={tr(tr('Описание проблемы', 'Problem description'), 'Problem description')}
                value={repairIssue}
                onChange={(e) => setRepairIssue(e.target.value)}
                placeholder={tr(
                  tr('Что сломано и какой результат ожидается', 'What is broken and what result is expected'),
                  'What is broken and what result is expected',
                )}
              />
              <button
                disabled={busy || !repairProject || !repairIssue.trim()}
                onClick={() => job('workspace_repair', { project: repairProject, issue: repairIssue })}
              >
                {tr('Исправить и проверить', 'Repair and test')}
              </button>
            </div>
          </section>
          {data?.managed_projects.map((p) => (
            <section className="case-card" key={p.name}>
              <h3>{p.name}</h3>
              <p>{p.spec.repository || tr('Локально созданный проект', 'Locally created project')}</p>
              <span className="tag">
                {p.file_count} {tr('файлов', 'files')} · {Math.round(p.bytes / 1024)} KB
              </span>
              <p className="muted">
                Runtime: {p.spec.runtime_image}
                {p.spec.service ? ` · ${tr('сервис', 'service')}: ${p.spec.service}` : ''} · snapshots:{' '}
                {p.snapshots?.length || 0}
              </p>
            </section>
          ))}
          {!data?.managed_projects.length && (
            <p className="empty-inline">
              {tr('Редактируемые проекты ещё не подключены.', 'No editable projects connected yet.')}
            </p>
          )}
        </>
      )}
      {tab === 'proxies' && (
        <>
          <section className="system-card">
            <h2>{tr('Источники прокси', 'Proxy sources')}</h2>
            <p className="muted">
              {tr(
                'Проверяются публичный IP, HTTPS CONNECT с проверкой TLS и контрольное содержимое. Срок действия результата — 15 минут.',
                'Checks the public IP, HTTPS CONNECT with TLS verification and reference content. Results are valid for 15 minutes.',
              )}
            </p>
            <textarea
              className="json-editor short-editor"
              aria-label={tr(tr('Источники прокси', 'Proxy sources'), 'Proxy sources')}
              value={sources}
              onChange={(e) => setSources(e.target.value)}
            />
            <div className="control-actions">
              <button
                disabled={busy}
                onClick={() =>
                  action('/proxies/sources', {
                    sources: sources
                      .split('\n')
                      .map((x) => x.trim())
                      .filter(Boolean),
                  })
                }
              >
                {tr('Сохранить источники', 'Save sources')}
              </button>
              <button disabled={busy} onClick={() => job('proxies')}>
                {tr('Обновить и проверить', 'Refresh and check')}
              </button>
            </div>
          </section>
          <div className="control-table">
            <table>
              <thead>
                <tr>
                  <th>{tr('Адрес', 'Address')}</th>
                  <th>{tr('Состояние', 'Status')}</th>
                  <th>{tr('Задержка', 'Latency')}</th>
                </tr>
              </thead>
              <tbody>
                {data?.proxies.map((p) => (
                  <tr key={p.id}>
                    <td>{p.id}</td>
                    <td>
                      {p.expires_at * 1000 < Date.now()
                        ? tr('Истёк TTL', 'TTL expired')
                        : p.healthy
                          ? tr('Доступен', 'Available')
                          : tr('Недоступен', 'Unavailable')}
                    </td>
                    <td>{p.latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {tab === 'connectors' && (
        <>
          <section className="system-card">
            <h2>{tr('Ключ встроенного сервиса', 'Built-in service key')}</h2>
            <form
              className="control-inline"
              onSubmit={async (e) => {
                e.preventDefault();
                if (await action('/keys', { provider, key })) setKey('');
              }}
            >
              <select
                aria-label={tr(tr('Сервис для ключа', 'Service for the key'), 'Service for the key')}
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="tavily">Tavily</option>
                <option value="firecrawl">Firecrawl</option>
                <option value="capsolver">CapSolver</option>
                <option value="twocaptcha">2Captcha</option>
              </select>
              <input
                type="password"
                autoComplete="off"
                aria-label={tr(tr('API-ключ', 'API key'), 'API key')}
                placeholder={tr(tr('API-ключ', 'API key'), 'API key')}
                value={key}
                onChange={(e) => setKey(e.target.value)}
              />
              <button disabled={busy || !key}>{tr('Сохранить ключ', 'Save key')}</button>
            </form>
            <p className="muted">
              {tr(
                'Ключ шифруется перед записью и не возвращается через API.',
                'The key is encrypted before it is stored and is never returned by the API.',
              )}
            </p>
          </section>
          <section className="system-card">
            <h2>{tr('Подключить произвольный Search / Fetch API', 'Connect a custom Search / Fetch API')}</h2>
            <textarea
              className="json-editor"
              aria-label={tr(tr('Конфигурация API', 'API configuration'), 'API configuration')}
              value={json}
              onChange={(e) => setJson(e.target.value)}
            />
            <p className="muted">
              {tr(
                'Поле выше задаёт URL, контракт, бюджет и при необходимости usage_endpoint / remaining_path. Ключ берётся из поля API-ключа.',
                'The field above sets the URL, contract, budget and optionally usage_endpoint / remaining_path. The key comes from the API key field.',
              )}
            </p>
            <button
              className="control-primary"
              disabled={busy}
              onClick={async () => {
                try {
                  if (await action('/connectors', { spec: JSON.parse(json), key: key || undefined }))
                    setKey('');
                } catch {
                  setError(tr('Некорректный JSON', 'Invalid JSON'));
                }
              }}
            >
              {tr('Сохранить подключение', 'Save connection')}
            </button>
          </section>
          {data?.connectors.map((c) => (
            <section className="case-card" key={c.id}>
              <h3>
                {c.id} · {c.mode}
              </h3>
              <p>{c.endpoint}</p>
              <span className="tag">
                {c.enabled ? tr('Включён', 'Enabled') : tr('Выключен', 'Disabled')} ·{' '}
                {c.key_configured ? tr('Ключ настроен', 'Key configured') : tr('Без ключа', 'No key')}
              </span>
            </section>
          ))}
          {data?.remote_quotas.map((q) => (
            <p key={q.provider}>
              {q.provider}: {tr('осталось', 'remaining')} {q.remaining} {tr('кредитов', 'credits')}
            </p>
          ))}
        </>
      )}
      {tab === 'policies' && (
        <>
          <section className="system-card">
            <h2>{tr('Правила для домена', 'Rules for a domain')}</h2>
            <p className="muted">
              {tr(
                'Таймаут, ожидание селектора, порог качества, официальные источники и CSS-поля для парсинга. Каждое изменение сохраняется как ревизия.',
                'Timeout, selector wait, quality threshold, official sources and CSS fields for parsing. Every change is saved as a revision.',
              )}
            </p>
            <textarea
              className="json-editor"
              aria-label={tr(tr('Правила домена', 'Domain rules'), 'Domain rules')}
              value={policy}
              onChange={(e) => setPolicy(e.target.value)}
            />
            <button className="control-primary" disabled={busy} onClick={() => parsed('/policies', policy)}>
              {tr('Сохранить правила', 'Save rules')}
            </button>
          </section>
          {data?.policies.map((p, i) => (
            <details className="case-card" key={i}>
              <summary>{String(p.domain)}</summary>
              <pre>{JSON.stringify(p, null, 2)}</pre>
              <button onClick={() => setPolicy(JSON.stringify(p, null, 2))}>
                {tr('Редактировать', 'Edit')}
              </button>
            </details>
          ))}
        </>
      )}
      {tab === 'crawls' && (
        <>
          <section className="system-card">
            <h2>{tr('План парсинга', 'Crawl plan')}</h2>
            <p className="muted">
              {tr(
                'До 50 страниц, переходы внутри исходных доменов, повтор по расписанию. Для извлечения полей задайте extractors в правилах сайта.',
                'Up to 50 pages, links within the source domains, repeated on a schedule. Set extractors in the site rules to extract fields.',
              )}
            </p>
            <textarea
              className="json-editor"
              aria-label={tr(tr('План парсинга', 'Crawl plan'), 'Crawl plan')}
              value={crawl}
              onChange={(e) => setCrawl(e.target.value)}
            />
            <button className="control-primary" disabled={busy} onClick={() => parsed('/crawls', crawl)}>
              {tr('Сохранить план', 'Save plan')}
            </button>
          </section>
          {data?.crawls.map((c) => (
            <section className="case-card" key={c.id}>
              <h3>{c.id}</h3>
              <p>
                {tr('До', 'Up to')} {c.max_pages} {tr('страниц', 'pages')} ·{' '}
                {c.interval_seconds
                  ? tr(`каждые ${c.interval_seconds} с`, `every ${c.interval_seconds} s`)
                  : tr('ручной запуск', 'manual run')}
              </p>
              <button disabled={busy} onClick={() => job('crawl', { plan: c.id })}>
                {tr('Запустить', 'Run')}
              </button>
            </section>
          ))}
          <h2 className="section-title">{tr('Собранные данные', 'Collected data')}</h2>
          {data?.datasets.map((d) => (
            <div className="dataset-row" key={d.id}>
              <b>{d.plan}</b>
              <span>
                {d.count} {tr('страниц', 'pages')}
              </span>
              <a href={`${API}/api/datasets/${d.id}`} target="_blank" rel="noreferrer">
                JSON ↗
              </a>
              <a href={`${API}/api/datasets/${d.id}?format=csv`}>{tr('Скачать CSV', 'Download CSV')}</a>
            </div>
          ))}
        </>
      )}
      {tab === 'pipelines' && (
        <>
          <div className="automation-overview">
            <div>
              <small>{tr('ДОМЕНЫ', 'DOMAINS')}</small>
              <strong>{latestPipelines.length}</strong>
              <span>{tr('адаптированы', 'adapted')}</span>
            </div>
            <div>
              <small>{tr('РАБОТАЮТ', 'WORKING')}</small>
              <strong>
                {latestPipelines.filter((p) => ['active', 'canary', 'tested'].includes(p.status)).length}
              </strong>
              <span>pipeline</span>
            </div>
            <div>
              <small>API</small>
              <strong>
                {data?.api_candidates.filter((a) => a.verification_status === 'verified_unauthenticated')
                  .length || 0}
              </strong>
              <span>{tr('проверено', 'verified')}</span>
            </div>
            <div>
              <small>{tr('РЕЗЕРВ', 'FALLBACK')}</small>
              <strong>4</strong>
              <span>{tr('уровня', 'levels')}</span>
            </div>
          </div>
          <section className="system-card pipeline-designer">
            <div>
              <div className="eyebrow">{tr('АВТОНОМНЫЙ РЕМОНТ', 'AUTONOMOUS REPAIR')}</div>
              <h2>{tr('Спроектировать маршрут для сайта', 'Design a route for a site')}</h2>
              <p className="muted">
                {tr(
                  'API/feeds → JSON-LD → semantic HTML → browser. Новая версия включается только после live-проверки.',
                  'API/feeds → JSON-LD → semantic HTML → browser. A new version is enabled only after a live check.',
                )}
              </p>
            </div>
            <form
              className="control-inline"
              onSubmit={(e) => {
                e.preventDefault();
                job('pipeline_design', { url: pipelineUrl });
              }}
            >
              <input
                aria-label={tr(tr('URL источника', 'Source URL'), 'Source URL')}
                value={pipelineUrl}
                onChange={(e) => setPipelineUrl(e.target.value)}
              />
              <button disabled={busy || !pipelineUrl}>{tr('Проверить сайт', 'Check site')}</button>
              <button
                type="button"
                disabled={busy || !pipelineUrl}
                onClick={() => job('discover_apis', { url: pipelineUrl })}
              >
                {tr('Найти API', 'Find API')}
              </button>
            </form>
          </section>
          <div className="section-heading">
            <div>
              <h2>{tr('Активные маршруты', 'Active routes')}</h2>
              <p>{tr('Последняя ревизия для каждого домена.', 'Latest revision for each domain.')}</p>
            </div>
            <span className="success-note">{tr('● live проверка обязательна', '● live check required')}</span>
          </div>
          <div className="pipeline-grid">
            {latestPipelines.map((p) => (
              <section className="pipeline-card" key={p.id}>
                <div>
                  <span className="pipeline-domain">{p.spec.domain.split('.').slice(-2).join('.')}</span>
                  <span className={'tag ' + p.status}>{labels[p.status] || p.status}</span>
                </div>
                <h3>{p.spec.domain}</h3>
                <div className="stage-flow">
                  {p.spec.stages.map((stage, index) => (
                    <React.Fragment key={stage.id}>
                      <span className={stage.kind === 'browser' ? 'browser-stage' : ''}>
                        {stage.kind.replace('_', ' ')}
                      </span>
                      {index < p.spec.stages.length - 1 && <i>→</i>}
                    </React.Fragment>
                  ))}
                </div>
                <small>
                  {p.successes} {tr('успешных вызовов', 'successful calls')} · {p.failures}{' '}
                  {tr('ошибок', 'errors')}
                </small>
              </section>
            ))}
          </div>
          <div className="section-heading">
            <div>
              <h2>{tr('Проверенные API и feeds', 'Verified APIs and feeds')}</h2>
              <p>
                {tr(
                  'Endpoints, реально ответившие без ключа.',
                  'Endpoints that actually answered without a key.',
                )}
              </p>
            </div>
          </div>
          <div className="api-grid">
            {data?.api_candidates.slice(0, 6).map((a) => (
              <section className="api-card" key={a.id}>
                <span className="tag">{a.verification_status}</span>
                <h3>{a.endpoint}</h3>
                <p>{a.cost_status}</p>
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
