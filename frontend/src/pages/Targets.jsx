import { useState, useEffect } from 'react';
import api from '../api';
import { useToast, StatusBadge, Spinner, EmptyState, EnrichDots, Modal, CopyButton, ConfirmButton, useApi, fmtDate, truncate } from '../components';

// ════════════════════════════════════════════════════════════
//  Dashboard Page
// ════════════════════════════════════════════════════════════
export function Dashboard() {
  const { data: stats, loading } = useApi(() => api.getStats());
  const { data: dashboard } = useApi(() => api.getDashboard());
  const { data: campaigns } = useApi(() => api.getCampaigns());

  if (loading) return <div className="loading-overlay"><Spinner size="lg" /><span>Loading dashboard…</span></div>;

  const totals = dashboard?.totals || {};
  const metrics = dashboard?.metrics || {};

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">🌿 Outreach Dashboard</h1>
          <p className="page-subtitle">Animal advocacy email campaigns at a glance</p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Companies</div>
          <div className="stat-value">{stats?.companies?.total ?? '—'}</div>
          <div className="stat-sub">{stats?.companies?.known ?? 0} contacted</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Individuals</div>
          <div className="stat-value">{stats?.individuals?.total ?? '—'}</div>
          <div className="stat-sub">{stats?.individuals?.with_email ?? 0} with email</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Emails Sent</div>
          <div className="stat-value">{totals.sent ?? 0}</div>
          <div className="stat-sub">{totals.drafted ?? 0} drafted</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Replies</div>
          <div className="stat-value">{totals.replied ?? 0}</div>
          <div className="stat-sub">{metrics.reply_rate_pct ?? 0}% reply rate</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Follow-ups Due</div>
          <div className="stat-value" style={{ color: (metrics.follow_ups_due_now ?? 0) > 0 ? 'var(--status-ignored)' : undefined }}>
            {metrics.follow_ups_due_now ?? 0}
          </div>
          <div className="stat-sub">need attention</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Campaigns</div>
          <div className="stat-value">{campaigns?.length ?? 0}</div>
          <div className="stat-sub">active workflows</div>
        </div>
      </div>

      {/* Status breakdown */}
      <div className="grid-2" style={{ gap: 20 }}>
        <div className="card">
          <div className="card-header">
            <span className="card-title">Email Status Breakdown</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {Object.entries(totals).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <StatusBadge status={k} />
                <div style={{ flex: 1, background: 'var(--border)', borderRadius: 99, height: 6 }}>
                  <div style={{
                    width: `${totals.sent > 0 ? Math.min(100, (v / (totals.all || 1)) * 100) : 0}%`,
                    height: '100%', borderRadius: 99,
                    background: 'linear-gradient(90deg, var(--accent-1), var(--accent-2))',
                    minWidth: v > 0 ? 4 : 0,
                  }} />
                </div>
                <span style={{ fontSize: '0.875rem', fontWeight: 700, minWidth: 24, textAlign: 'right' }}>{v}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Recent Campaigns</span>
          </div>
          {!campaigns?.length ? (
            <EmptyState icon="📋" title="No campaigns yet" text="Create a campaign to start outreach." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {campaigns.slice(0, 5).map(c => (
                <div key={c.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-glass)', border: '1px solid var(--border)' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{c.name}</div>
                    <div className="text-xs text-muted">{c.domain_target} · {fmtDate(c.created_at)}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    <span>📩 {c.total_sent ?? 0}</span>
                    <span>💬 {c.total_replied ?? 0}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
//  Companies Page
// ════════════════════════════════════════════════════════════
export function Companies() {
  const toast = useToast();
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [enriching, setEnriching] = useState({});

  const { data: companies, loading, reload } = useApi(
    () => search ? api.searchCompanies(search) : api.getCompanies({ limit: 100 }),
    [search]
  );

  const enrich = async (company, type = 'all') => {
    setEnriching(e => ({ ...e, [company.id]: type }));
    try {
      const fn = type === 'all' ? api.enrichCompanyAll :
                 type === 'serper' ? api.enrichCompanySerper :
                 type === 'oc' ? api.enrichCompanyOC : api.enrichCompanyHunter;
      await fn(company.id);
      toast(`✨ ${company.name} enriched via ${type.toUpperCase()}`, 'success');
      reload();
    } catch (e) {
      toast(`❌ ${e.message}`, 'error');
    } finally {
      setEnriching(e => ({ ...e, [company.id]: null }));
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">🏢 Companies</h1>
          <p className="page-subtitle">Target company database for outreach</p>
        </div>
      </div>

      <div className="flex gap-3 mb-4">
        <div className="search-bar" style={{ maxWidth: 400, flex: 1 }}>
          <span className="search-icon">🔍</span>
          <input
            className="form-input"
            placeholder="Search companies by name or domain tag…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <button className="btn btn-secondary btn-sm" onClick={reload}>🔄 Refresh</button>
      </div>

      {loading ? (
        <div className="loading-overlay"><Spinner size="lg" /></div>
      ) : !companies?.length ? (
        <EmptyState icon="🏢" title="No companies found" text="Seed the database or add companies manually." />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Sector</th>
                <th>Product</th>
                <th>Status</th>
                <th>Enrichment</th>
                <th>Last Contact</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {companies.map(c => (
                <tr key={c.id} onClick={() => setSelected(c)} style={{ cursor: 'pointer' }}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{c.name}</div>
                    <div className="text-xs text-muted">{c.website || '—'}</div>
                  </td>
                  <td>{c.sector || '—'}</td>
                  <td><span className="text-xs">{c.product_type || '—'}</span></td>
                  <td>
                    {c.known ? <span className="badge badge-replied">Known</span> : <span className="badge badge-drafted">Target</span>}
                  </td>
                  <td><EnrichDotsFetcher companyId={c.id} /></td>
                  <td className="text-xs text-muted">{fmtDate(c.last_contacted_at)}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={!!enriching[c.id]}
                      onClick={() => enrich(c, 'all')}
                    >
                      {enriching[c.id] ? <><Spinner /> Enriching…</> : '⚡ Enrich All'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Company Detail Modal */}
      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.name} size="lg">
        {selected && <CompanyDetail company={selected} onEnrich={enrich} enriching={enriching} />}
      </Modal>
    </div>
  );
}

function EnrichDotsFetcher({ companyId }) {
  const { data } = useApi(() => api.getCompanyStatus(companyId), [companyId]);
  return <EnrichDots status={data?.enrichment_status} />;
}

function CompanyDetail({ company, onEnrich, enriching }) {
  const { data: status } = useApi(() => api.getCompanyStatus(company.id), [company.id]);
  const es = status?.enrichment_status || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="grid-2">
        <div>
          <div className="form-label">Sector</div>
          <div>{company.sector || '—'}</div>
        </div>
        <div>
          <div className="form-label">Product Type</div>
          <div>{company.product_type || '—'}</div>
        </div>
        <div>
          <div className="form-label">Website</div>
          <div>{company.website ? <a href={company.website} target="_blank">{company.website}</a> : '—'}</div>
        </div>
        <div>
          <div className="form-label">LinkedIn</div>
          <div>{company.linkedin_url ? <a href={company.linkedin_url} target="_blank">View Profile</a> : '—'}</div>
        </div>
      </div>

      {company.description && (
        <div>
          <div className="form-label">Description</div>
          <p className="text-sm text-secondary">{company.description}</p>
        </div>
      )}

      <div>
        <div className="form-label" style={{ marginBottom: 10 }}>Enrichment Status</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
          {Object.entries(es).map(([k, v]) => (
            <div key={k} style={{ padding: '10px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', background: 'var(--bg-glass)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>{k.replace('_', ' ')}</div>
              <div className={`enrich-dot ${v?.fresh ? 'fresh' : v?.has_data ? 'stale' : 'empty'}`} style={{ width: 10, height: 10, marginBottom: 4 }} />
              <div className="text-xs text-muted">
                {v?.fresh ? `Fresh · ${v.cached_hours_ago?.toFixed(1) ?? 0}h ago` :
                 v?.has_data ? `Cached · TTL ${v.ttl_days}d` : 'No data'}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
        <button className="btn btn-primary btn-sm" disabled={!!enriching[company.id]} onClick={() => onEnrich(company, 'all')}>
          {enriching[company.id] ? <><Spinner /> Enriching…</> : '⚡ Enrich All'}
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => onEnrich(company, 'serper')}>📰 Serper News</button>
        <button className="btn btn-secondary btn-sm" onClick={() => onEnrich(company, 'oc')}>🏛️ OpenCorporates</button>
        <button className="btn btn-secondary btn-sm" onClick={() => onEnrich(company, 'hunter')}>🔍 Hunter.io</button>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
//  Individuals Page
// ════════════════════════════════════════════════════════════
export function Individuals() {
  const toast = useToast();
  const [selected, setSelected] = useState(null);
  const [enriching, setEnriching] = useState({});

  const { data: individuals, loading, reload } = useApi(() => api.getIndividuals({ limit: 100 }));

  const enrich = async (ind) => {
    setEnriching(e => ({ ...e, [ind.id]: true }));
    try {
      await api.enrichIndividualAll(ind.id);
      toast(`✨ ${ind.name} enriched`, 'success');
      reload();
    } catch (e) {
      toast(`❌ ${e.message}`, 'error');
    } finally {
      setEnriching(e => ({ ...e, [ind.id]: false }));
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">👤 Individuals</h1>
          <p className="page-subtitle">Contact persons for personalized outreach</p>
        </div>
      </div>

      {loading ? (
        <div className="loading-overlay"><Spinner size="lg" /></div>
      ) : !individuals?.length ? (
        <EmptyState icon="👤" title="No individuals found" text="Seed the database to add contacts." />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Role</th>
                <th>Company</th>
                <th>Email</th>
                <th>DISC</th>
                <th>Enrichment</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {individuals.map(ind => (
                <tr key={ind.id} onClick={() => setSelected(ind)} style={{ cursor: 'pointer' }}>
                  <td>{ind.name}</td>
                  <td className="text-sm text-secondary">{ind.role || '—'}</td>
                  <td className="text-sm text-secondary">{ind.company_name || '—'}</td>
                  <td className="text-xs font-mono">{ind.email || '—'}</td>
                  <td>
                    <span className={`disc-chip disc-${ind.humantic_disc || 'UNKNOWN'}`}>
                      {ind.humantic_disc || '?'}
                    </span>
                  </td>
                  <td><IndividualEnrichDots indId={ind.id} /></td>
                  <td onClick={e => e.stopPropagation()}>
                    <button className="btn btn-secondary btn-sm" disabled={enriching[ind.id]} onClick={() => enrich(ind)}>
                      {enriching[ind.id] ? <Spinner /> : '⚡ Enrich'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.name}>
        {selected && <IndividualDetail individual={selected} onEnrich={enrich} enriching={enriching} />}
      </Modal>
    </div>
  );
}

function IndividualEnrichDots({ indId }) {
  const { data } = useApi(() => api.getIndividualStatus(indId), [indId]);
  const es = data?.enrichment_status || {};
  const sources = ['humantic', 'hunter', 'serper', 'individual_analysis'];
  return (
    <div className="enrich-dots" title="Humantic / Hunter / Serper / Analysis">
      {sources.map(s => (
        <div key={s} className={`enrich-dot ${es[s]?.fresh ? 'fresh' : es[s]?.has_data ? 'stale' : 'empty'}`} />
      ))}
    </div>
  );
}

function IndividualDetail({ individual, onEnrich, enriching }) {
  const { data: status } = useApi(() => api.getIndividualStatus(individual.id), [individual.id]);
  const disc = individual.humantic_disc || 'UNKNOWN';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="grid-2">
        <div><div className="form-label">Role</div><div>{individual.role || '—'}</div></div>
        <div><div className="form-label">Email</div><div className="font-mono text-sm">{individual.email || '—'}</div></div>
        <div><div className="form-label">LinkedIn</div><div>{individual.linkedin_url ? <a href={individual.linkedin_url} target="_blank">View</a> : '—'}</div></div>
        <div>
          <div className="form-label">DISC Type</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className={`disc-chip disc-${disc}`}>{disc === 'UNKNOWN' ? '?' : disc}</span>
            <span className="text-sm text-secondary">{disc}</span>
          </div>
        </div>
      </div>

      {individual.humantic_communication_pref && (
        <div>
          <div className="form-label">Communication Preference</div>
          <div className="email-preview" style={{ fontSize: '0.78rem', padding: 14 }}>
            {individual.humantic_communication_pref}
          </div>
        </div>
      )}

      <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
        <button className="btn btn-primary btn-sm" disabled={enriching[individual.id]} onClick={() => onEnrich(individual)}>
          {enriching[individual.id] ? <><Spinner /> Enriching…</> : '⚡ Enrich All'}
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => api.enrichIndividualHumantic(individual.id)}>🧠 Humantic</button>
        <button className="btn btn-secondary btn-sm" onClick={() => api.enrichIndividualSerper(individual.id)}>📰 Serper</button>
      </div>
    </div>
  );
}
