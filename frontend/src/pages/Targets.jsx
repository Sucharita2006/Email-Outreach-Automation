import { useState, useEffect } from 'react';
import api from '../api';
import { useToast, StatusBadge, Spinner, EmptyState, EnrichDots, Modal, CopyButton, ConfirmButton, useApi, fmtDate, truncate } from '../components';
import { Building, Users, Mail, MessageSquare, AlertCircle, Briefcase, LayoutDashboard, UserCircle } from 'lucide-react';
import { DashboardMetricCard } from '@/components/ui/dashboard-overview';
import { ScrollArea } from '@/components/ui/scroll-area';

// ════════════════════════════════════════════════════════════
//  Dashboard Page
// ════════════════════════════════════════════════════════════
export function Dashboard({ navigate }) {
  const { data: stats, loading } = useApi(() => api.getStats());
  const { data: dashboard } = useApi(() => api.getDashboard());
  const { data: campaigns } = useApi(() => api.getCampaigns());

  if (loading) return <div className="loading-overlay"><Spinner size="lg" /><span>Loading dashboard…</span></div>;

  const totals = dashboard?.totals || {};
  const metrics = dashboard?.metrics || {};

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="page-header shrink-0">
        <div>
          <h1 className="page-title"><LayoutDashboard className="inline-block w-6 h-6 mr-1" style={{ WebkitTextFillColor: 'initial', color: '#818cf8', verticalAlign: '-3px' }} /> Outreach Dashboard</h1>
          <p className="page-subtitle">Animal advocacy email campaigns at a glance</p>
        </div>
      </div>

      <ScrollArea className="flex-1 w-full pr-4">
        {/* Stats Grid */}
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 mb-8">
          <DashboardMetricCard
            title="Companies"
            value={stats?.companies?.total ?? '—'}
            icon={Building}
            iconColor="#06b6d4"
            trendChange={`${stats?.companies?.known ?? 0} contacted`}
            trendType="neutral"
          />
          <DashboardMetricCard
            title="Individuals"
            value={stats?.individuals?.total ?? '—'}
            icon={Users}
            iconColor="#6366f1"
            trendChange={`${stats?.individuals?.known ?? 0} contacted`}
            trendType="neutral"
          />
          <DashboardMetricCard
            title="Emails Sent"
            value={totals.sent ?? 0}
            icon={Mail}
            iconColor="#3b82f6"
            trendChange={`${totals.drafted ?? 0} drafted`}
            trendType="neutral"
          />
          <DashboardMetricCard
            title="Replies"
            value={totals.replied ?? 0}
            icon={MessageSquare}
            iconColor="#ec4899"
            trendChange={`${metrics.reply_rate_pct ?? 0}% rate`}
            trendType={(metrics.reply_rate_pct ?? 0) > 5 ? "up" : "neutral"}
          />
          <DashboardMetricCard
            title="Follow-ups Due"
            value={metrics.follow_ups_due_now ?? 0}
            icon={AlertCircle}
            iconColor="#f59e0b"
            trendChange="Needs attention"
            trendType={(metrics.follow_ups_due_now ?? 0) > 0 ? "down" : "neutral"}
          />
          <DashboardMetricCard
            title="Campaigns"
            value={campaigns?.length ?? 0}
            icon={Briefcase}
            iconColor="#8b5cf6"
            trendChange="Active workflows"
            trendType="neutral"
          />
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
                  <div key={c.id} 
                       onClick={() => navigate('campaigns', { campaignId: c.id })}
                       style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-glass)', border: '1px solid var(--border)', cursor: 'pointer' }}>
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
      </ScrollArea>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
//  Companies Page
// ════════════════════════════════════════════════════════════
export function Companies() {
  const toast = useToast();
  const [search, setSearch] = useState('');
  const [searchType, setSearchType] = useState('name');
  const [selected, setSelected] = useState(null);
  const [enriching, setEnriching] = useState({});

  const { data: companies, loading, reload } = useApi(
    () => search ? api.searchCompanies(search, searchType) : api.getCompanies({ limit: 100 }),
    [search, searchType]
  );
  const { data: campaigns } = useApi(() => api.getCampaigns());

  const getContactStr = (target) => {
    if (!target.last_contacted_at) return '—';
    const dateStr = fmtDate(target.last_contacted_at);
    if (!campaigns || !target.campaign_ids || target.campaign_ids.length === 0) return dateStr;
    const cid = target.campaign_ids[target.campaign_ids.length - 1];
    const camp = campaigns.find(c => c.id === cid);
    return camp ? `${camp.name} (${dateStr})` : dateStr;
  };

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
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="page-header shrink-0">
        <div>
          <h1 className="page-title"><Building className="inline-block w-6 h-6 mr-1" style={{ WebkitTextFillColor: 'initial', color: '#818cf8', verticalAlign: '-3px' }} /> Companies</h1>
          <p className="page-subtitle">Target company database for outreach</p>
        </div>
      </div>

      <div className="flex gap-3 mb-4 shrink-0">
        <div style={{ display: 'flex', flex: 1, maxWidth: 500, gap: 10 }}>
          <select 
            className="form-input" 
            style={{ width: '160px', cursor: 'pointer' }}
            value={searchType}
            onChange={e => setSearchType(e.target.value)}
          >
            <option value="name" style={{ background: 'var(--bg-card)', color: 'var(--text)' }}>Company Name</option>
            <option value="website" style={{ background: 'var(--bg-card)', color: 'var(--text)' }}>Website Domain</option>
            <option value="domain_tag" style={{ background: 'var(--bg-card)', color: 'var(--text)' }}>Advocacy Domain</option>
          </select>
          <div className="search-bar" style={{ flex: 1 }}>
            <span className="search-icon">🔍</span>
            <input
              className="form-input"
              placeholder={`Search by ${searchType.replace('_', ' ')}...`}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={reload}>🔄 Refresh</button>
      </div>

      {loading ? (
        <div className="loading-overlay flex-1"><Spinner size="lg" /></div>
      ) : !companies?.length ? (
        <EmptyState icon="🏢" title="No companies found" text="Seed the database or add companies manually." />
      ) : (
        <div className="flex-1 w-full rounded-md border border-white/10 bg-black/20 overflow-y-auto relative">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Contact Person</th>
                  <th>Email</th>
                  <th>Sector</th>
                  <th>Product</th>
                  <th>Status</th>
                  <th>Last Contact</th>
                </tr>
              </thead>
              <tbody>
                {companies.map(c => {
                  let bestContact = null;
                  if (c.individuals && c.individuals.length > 0) {
                    bestContact = c.individuals.find(i => i.email) || c.individuals[0];
                  }
                  
                  return (
                    <tr key={c.id} onClick={() => setSelected(c)} style={{ cursor: 'pointer' }}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{c.name}</div>
                        <div className="text-xs text-muted">{c.website || '—'}</div>
                      </td>
                      <td>
                        {bestContact ? (
                          <>
                            <div style={{ fontWeight: 500, fontSize: '0.875rem' }}>{bestContact.name}</div>
                            <div className="text-xs text-muted">{bestContact.role || '—'}</div>
                          </>
                        ) : <span className="text-muted">—</span>}
                      </td>
                      <td>
                        {bestContact?.email ? (
                          <span className="font-mono text-xs">{bestContact.email}</span>
                        ) : (
                          <span className="text-xs" style={{ color: '#ef4444' }}>Email not found</span>
                        )}
                      </td>
                      <td>{c.sector || '—'}</td>
                      <td><span className="text-xs">{c.product_type || '—'}</span></td>
                    <td>
                      {c.known ? <span className="badge badge-replied">Known</span> : <span className="badge badge-drafted">Target</span>}
                    </td>
                    <td className="text-xs text-muted">{getContactStr(c)}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
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
  const { data: campaigns } = useApi(() => api.getCampaigns());

  const getContactStr = (target) => {
    if (!target.last_contacted_at) return '—';
    const dateStr = fmtDate(target.last_contacted_at);
    if (!campaigns || !target.campaign_ids || target.campaign_ids.length === 0) return dateStr;
    const cid = target.campaign_ids[target.campaign_ids.length - 1];
    const camp = campaigns.find(c => c.id === cid);
    return camp ? `${camp.name} (${dateStr})` : dateStr;
  };

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
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="page-header shrink-0">
        <div>
          <h1 className="page-title"><UserCircle className="inline-block w-6 h-6 mr-1" style={{ WebkitTextFillColor: 'initial', color: '#818cf8', verticalAlign: '-3px' }} /> Individuals</h1>
          <p className="page-subtitle">Contact persons for personalized outreach</p>
        </div>
      </div>

      {loading ? (
        <div className="loading-overlay flex-1"><Spinner size="lg" /></div>
      ) : !individuals?.length ? (
        <EmptyState icon="👤" title="No individuals found" text="Seed the database to add contacts." />
      ) : (
        <div className="flex-1 w-full rounded-md border border-white/10 bg-black/20 overflow-y-auto relative">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Sector</th>
                  <th>Email</th>
                  <th>Last Contact</th>
                </tr>
              </thead>
              <tbody>
                {individuals.map(ind => (
                  <tr key={ind.id} onClick={() => setSelected(ind)} style={{ cursor: 'pointer' }}>
                    <td>{ind.name}</td>
                    <td className="text-sm text-secondary">{ind.role || '—'}</td>
                    <td>
                      {ind.domain_tags?.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {ind.domain_tags.slice(0, 2).map(tag => (
                            <span key={tag} className="badge" style={{ background: 'var(--bg-glass-hover)', border: '1px solid var(--border)', fontSize: '0.7rem', padding: '2px 6px' }}>
                              {tag}
                            </span>
                          ))}
                          {ind.domain_tags.length > 2 && <span className="text-xs text-muted mt-0.5">+{ind.domain_tags.length - 2}</span>}
                        </div>
                      ) : (
                        <span className="text-sm text-secondary">—</span>
                      )}
                    </td>
                    <td>
                      {ind.email ? (
                        <span className="font-mono text-xs">{ind.email}</span>
                      ) : (
                        <span className="text-xs" style={{ color: '#ef4444' }}>Email not found</span>
                      )}
                    </td>
                    <td className="text-xs text-muted">{getContactStr(ind)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
      </div>
    </div>
  );
}
