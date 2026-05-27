import { useState } from 'react';
import api from '../api';
import { useToast, StatusBadge, Spinner, EmptyState, Modal, CopyButton, ConfirmButton, useApi, fmtDate, fmtRelative, truncate } from '../components';

// ════════════════════════════════════════════════════════════
//  Email Generate Page — Domain-Driven Wizard
// ════════════════════════════════════════════════════════════
export function Generate() {
  const toast = useToast();

  // Step 1 — Campaign Setup
  const [campName, setCampName] = useState('');
  const [domain, setDomain] = useState('');
  const [purpose, setPurpose] = useState('');
  const [discovering, setDiscovering] = useState(false);

  // Step 2 — Target Selection
  const [campaignId, setCampaignId] = useState(null);
  const [discovered, setDiscovered] = useState(null); // { companies, individuals }
  const [selectedCompanyIds, setSelectedCompanyIds] = useState(new Set());
  const [selectedIndividualIds, setSelectedIndividualIds] = useState(new Set());

  // Step 3 — Generation Progress
  const [generating, setGenerating] = useState(false);
  const [genResults, setGenResults] = useState([]); // per-target result rows

  // Step 4 — Review
  const [step, setStep] = useState(1);

  // ── Step 1: Discover ──────────────────────────────────────
  const discover = async () => {
    if (!campName.trim() || !domain.trim() || !purpose.trim()) {
      toast('Fill in campaign name, domain, and purpose.', 'error');
      return;
    }
    setDiscovering(true);
    try {
      const res = await api.discoverTargets({
        campaign_name: campName.trim(),
        domain: domain.trim(),
        campaign_purpose: purpose.trim(),
        limit: 30,
      });
      setCampaignId(res.campaign_id);
      setDiscovered(res);
      setSelectedCompanyIds(new Set());
      setSelectedIndividualIds(new Set());
      setStep(2);
      if (res.enrichment_queued) {
        toast('Targets found. Enrichment running in background.', 'info');
      }
    } catch (e) {
      toast(`Discovery failed: ${e.message}`, 'error');
    } finally {
      setDiscovering(false);
    }
  };

  // ── Step 2: Selection helpers ─────────────────────────────
  const toggleCompany = (id) => {
    setSelectedCompanyIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleIndividual = (id) => {
    setSelectedIndividualIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const allCompaniesSelected = discovered?.companies?.length > 0 &&
    discovered.companies.every(c => selectedCompanyIds.has(c.id));
  const allIndividualsSelected = discovered?.individuals?.length > 0 &&
    discovered.individuals.every(i => selectedIndividualIds.has(i.id));

  const toggleAllCompanies = () => {
    if (allCompaniesSelected) setSelectedCompanyIds(new Set());
    else setSelectedCompanyIds(new Set(discovered.companies.map(c => c.id)));
  };

  const toggleAllIndividuals = () => {
    if (allIndividualsSelected) setSelectedIndividualIds(new Set());
    else setSelectedIndividualIds(new Set(discovered.individuals.map(i => i.id)));
  };

  const totalSelected = selectedCompanyIds.size + selectedIndividualIds.size;

  // ── Step 3: Generate ──────────────────────────────────────
  const generateEmails = async () => {
    if (totalSelected === 0) {
      toast('Select at least one target.', 'error');
      return;
    }

    // Build target pairs: each individual paired with their company (or a selected company)
    const targets = [];
    const companiesByid = Object.fromEntries((discovered?.companies || []).map(c => [c.id, c]));
    const individualsById = Object.fromEntries((discovered?.individuals || []).map(i => [i.id, i]));

    // Selected individuals — auto-pair with their registered company
    for (const indId of selectedIndividualIds) {
      const ind = individualsById[indId];
      if (ind?.company_id) {
        targets.push({ individual_id: indId, company_id: ind.company_id });
      }
    }

    // Selected companies without a paired individual — skip (need individual for email)
    // But if company is selected AND has individuals in the result, use them
    for (const compId of selectedCompanyIds) {
      const compIndividuals = (discovered?.individuals || []).filter(i => i.company_id === compId);
      for (const ind of compIndividuals) {
        if (!selectedIndividualIds.has(ind.id)) { // avoid duplicates
          targets.push({ individual_id: ind.id, company_id: compId });
        }
      }
    }

    if (targets.length === 0) {
      toast('No valid individual+company pairs found. Select individuals to generate emails.', 'error');
      return;
    }

    // Init progress rows
    setGenResults(targets.map(t => ({
      individual_id: t.individual_id,
      company_id: t.company_id,
      individual_name: individualsById[t.individual_id]?.name || '…',
      company_name: companiesByid[t.company_id]?.name || '…',
      status: 'pending',
    })));
    setGenerating(true);
    setStep(3);

    try {
      const res = await api.generateCampaignTargets({
        campaign_id: campaignId,
        targets,
        force_refresh_analysis: false,
      });
      setGenResults(res.results || []);
      setStep(4);
      toast(`${res.ok} email${res.ok !== 1 ? 's' : ''} generated.`, res.ok > 0 ? 'success' : 'error');
    } catch (e) {
      toast(`Generation failed: ${e.message}`, 'error');
      setStep(2);
    } finally {
      setGenerating(false);
    }
  };

  const reset = () => {
    setStep(1); setCampName(''); setDomain(''); setPurpose('');
    setCampaignId(null); setDiscovered(null);
    setSelectedCompanyIds(new Set()); setSelectedIndividualIds(new Set());
    setGenResults([]);
  };

  // ── Match source badge ────────────────────────────────────
  const SourceBadge = ({ source }) => {
    const map = {
      db_domain_tag: ['🏷️', 'Database'],
      db_personal_tag: ['🔖', 'Past Contrib'],
      db_role_match: ['👤', 'Role Match'],
      serper_web: ['🌐', 'Web Search'],
      hunter_contact: ['📧', 'Hunter'],
      serper_individual: ['🌐', 'Web Search'],
    };
    const [icon, label] = map[source] || ['•', source];
    return (
      <span style={{
        fontSize: '0.7rem', padding: '2px 7px', borderRadius: 99,
        background: 'var(--bg-glass)', border: '1px solid var(--border)',
        color: 'var(--text-secondary)', whiteSpace: 'nowrap',
      }}>{icon} {label}</span>
    );
  };

  // ── Render ────────────────────────────────────────────────
  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">✉️ Generate Emails</h1>
          <p className="page-subtitle">Enter your domain → discover targets → generate personalized emails</p>
        </div>
        {step > 1 && <button className="btn btn-ghost btn-sm" onClick={reset}>↩ Start Over</button>}
      </div>

      {/* Step indicators */}
      <div className="pipeline" style={{ marginBottom: 28 }}>
        {['Campaign Setup', 'Select Targets', 'Generating', 'Review'].map((s, i) => (
          <span key={s}>
            <div className={`pipeline-step ${step === i+1 ? 'active' : step > i+1 ? 'done' : ''}`}>
              {step > i+1 ? '✓' : i+1} {s}
            </div>
            {i < 3 && <div className="pipeline-arrow">→</div>}
          </span>
        ))}
      </div>

      {/* ── Step 1: Campaign Setup ── */}
      {step === 1 && (
        <div className="card" style={{ maxWidth: 580 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Campaign Setup</h3>

          <div className="form-group">
            <label className="form-label">Campaign Name</label>
            <input className="form-input" placeholder="e.g. Q3 Plant-Based Outreach"
              value={campName} onChange={e => setCampName(e.target.value)} />
          </div>

          <div className="form-group">
            <label className="form-label">Domain</label>
            <input className="form-input" placeholder="e.g. plant-based, fermentation, animal-welfare"
              value={domain} onChange={e => setDomain(e.target.value)} />
            <div className="text-xs text-muted" style={{ marginTop: 4 }}>
              Used to discover matching companies and individuals automatically.
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Campaign Purpose</label>
            <textarea className="form-textarea" rows={3}
              placeholder="e.g. We are running a fundraiser for our animal welfare programs and want to partner with companies in this space."
              value={purpose} onChange={e => setPurpose(e.target.value)} />
            <div className="text-xs text-muted" style={{ marginTop: 4 }}>
              Helps the system find the right companies and craft personalized emails.
            </div>
          </div>

          <button className="btn btn-primary btn-lg w-full"
            disabled={!campName.trim() || !domain.trim() || !purpose.trim() || discovering}
            onClick={discover}>
            {discovering ? <><Spinner /> Discovering targets…</> : '🔍 Discover Targets'}
          </button>
        </div>
      )}

      {/* ── Step 2: Target Selection ── */}
      {step === 2 && discovered && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* Summary bar */}
          <div style={{
            padding: '12px 18px', background: 'var(--bg-glass)',
            border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
            display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
          }}>
            <span className="text-sm">
              <strong>{discovered.total_companies}</strong> companies &nbsp;·&nbsp;
              <strong>{discovered.total_individuals}</strong> individuals found for
              <strong> "{discovered.domain}"</strong>
            </span>
            {discovered.enrichment_queued && (
              <span className="text-xs text-muted" style={{ marginLeft: 'auto' }}>
                ⏳ Enrichment running in background…
              </span>
            )}
          </div>

          <div className="grid-2" style={{ alignItems: 'start' }}>

            {/* Companies column */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
                <input type="checkbox" id="select-all-companies"
                  checked={allCompaniesSelected}
                  onChange={toggleAllCompanies}
                  style={{ cursor: 'pointer' }} />
                <label htmlFor="select-all-companies" className="form-label" style={{ margin: 0, cursor: 'pointer' }}>
                  🏢 Companies ({discovered.companies.length})
                </label>
                {selectedCompanyIds.size > 0 && (
                  <span className="text-xs text-muted" style={{ marginLeft: 'auto' }}>
                    {selectedCompanyIds.size} selected
                  </span>
                )}
              </div>

              {discovered.companies.length === 0 ? (
                <div style={{ padding: '20px 16px', color: 'var(--text-muted)', fontSize: '0.875rem', textAlign: 'center' }}>
                  No companies found for this domain.
                </div>
              ) : (
                <div style={{ maxHeight: 420, overflowY: 'auto' }}>
                  {discovered.companies.map(c => (
                    <div key={c.id}
                      onClick={() => toggleCompany(c.id)}
                      style={{
                        padding: '12px 16px', borderBottom: '1px solid var(--border)',
                        cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'flex-start',
                        background: selectedCompanyIds.has(c.id) ? 'var(--bg-glass)' : 'transparent',
                        transition: 'background 0.15s',
                      }}>
                      <input type="checkbox" checked={selectedCompanyIds.has(c.id)} onChange={() => {}}
                        style={{ marginTop: 3, cursor: 'pointer', flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{c.name}</span>
                          <SourceBadge source={c.match_source} />
                          {c.known && <span style={{ fontSize: '0.7rem', color: 'var(--status-replied)', fontWeight: 600 }}>● Known</span>}
                        </div>
                        {c.sector && <div className="text-xs text-muted">{c.sector}</div>}
                        {c.relevance_reason && (
                          <div className="text-xs text-secondary" style={{ marginTop: 4, lineHeight: 1.4 }}>
                            {c.relevance_reason.slice(0, 100)}{c.relevance_reason.length > 100 ? '…' : ''}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Individuals column */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
                <input type="checkbox" id="select-all-individuals"
                  checked={allIndividualsSelected}
                  onChange={toggleAllIndividuals}
                  style={{ cursor: 'pointer' }} />
                <label htmlFor="select-all-individuals" className="form-label" style={{ margin: 0, cursor: 'pointer' }}>
                  👤 Individuals ({discovered.individuals.length})
                </label>
                {selectedIndividualIds.size > 0 && (
                  <span className="text-xs text-muted" style={{ marginLeft: 'auto' }}>
                    {selectedIndividualIds.size} selected
                  </span>
                )}
              </div>

              {discovered.individuals.length === 0 ? (
                <div style={{ padding: '20px 16px', color: 'var(--text-muted)', fontSize: '0.875rem', textAlign: 'center' }}>
                  No individuals found. Add Serper/Hunter keys for contact discovery.
                </div>
              ) : (
                <div style={{ maxHeight: 420, overflowY: 'auto' }}>
                  {discovered.individuals.map(i => (
                    <div key={i.id}
                      onClick={() => toggleIndividual(i.id)}
                      style={{
                        padding: '12px 16px', borderBottom: '1px solid var(--border)',
                        cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'flex-start',
                        background: selectedIndividualIds.has(i.id) ? 'var(--bg-glass)' : 'transparent',
                        transition: 'background 0.15s',
                      }}>
                      <input type="checkbox" checked={selectedIndividualIds.has(i.id)} onChange={() => {}}
                        style={{ marginTop: 3, cursor: 'pointer', flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{i.name}</span>
                          <SourceBadge source={i.match_source} />
                          {i.known && <span style={{ fontSize: '0.7rem', color: 'var(--status-replied)', fontWeight: 600 }}>● Known</span>}
                        </div>
                        <div className="text-xs text-muted">
                          {i.role || 'Unknown role'}{i.company_name ? ` @ ${i.company_name}` : ''}
                        </div>
                        {i.email && <div className="text-xs font-mono text-muted" style={{ marginTop: 2 }}>{i.email}</div>}
                        {i.relevance_reason && (
                          <div className="text-xs text-secondary" style={{ marginTop: 4, lineHeight: 1.4 }}>
                            {i.relevance_reason.slice(0, 100)}{i.relevance_reason.length > 100 ? '…' : ''}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Generate bar */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 16,
            padding: '16px 20px', background: 'var(--bg-glass)',
            border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
            position: 'sticky', bottom: 16,
          }}>
            <span className="text-sm">
              {totalSelected === 0
                ? 'Select targets above to generate emails'
                : <><strong>{totalSelected}</strong> target{totalSelected !== 1 ? 's' : ''} selected</>}
            </span>
            <button className="btn btn-primary btn-lg" style={{ marginLeft: 'auto' }}
              disabled={totalSelected === 0}
              onClick={generateEmails}>
              ✉️ Generate {totalSelected > 0 ? totalSelected : ''} Email{totalSelected !== 1 ? 's' : ''}
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Generation Progress ── */}
      {step === 3 && (
        <div className="card" style={{ maxWidth: 700 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20 }}>
            <Spinner size="lg" />
            <div>
              <div style={{ fontWeight: 600 }}>Generating personalized emails…</div>
              <div className="text-sm text-muted">Running 3-call AI pipeline per target. This may take 1–2 minutes.</div>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {genResults.map((r, idx) => (
              <div key={idx} style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)',
              }}>
                <Spinner />
                <div>
                  <span style={{ fontWeight: 600 }}>{r.individual_name}</span>
                  <span className="text-muted text-sm"> @ {r.company_name}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Step 4: Review Results ── */}
      {step === 4 && genResults.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="flex justify-between items-center">
            <div>
              <span style={{ fontWeight: 700, fontSize: '1.1rem' }}>
                {genResults.filter(r => r.status === 'ok').length} / {genResults.length} emails generated
              </span>
              <span className="text-sm text-muted" style={{ marginLeft: 12 }}>
                Campaign: <strong>{campName}</strong>
              </span>
            </div>
            <div className="flex gap-2">
              <button className="btn btn-secondary btn-sm" onClick={() => setStep(2)}>← Edit Selection</button>
              <button className="btn btn-secondary btn-sm" onClick={reset}>+ New Campaign</button>
            </div>
          </div>

          {genResults.map((r, idx) => (
            <div key={idx} className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                <span style={{
                  width: 28, height: 28, borderRadius: '50%', display: 'flex',
                  alignItems: 'center', justifyContent: 'center', fontSize: '0.85rem', fontWeight: 700,
                  background: r.status === 'ok' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                  color: r.status === 'ok' ? '#22c55e' : '#ef4444',
                }}>
                  {r.status === 'ok' ? '✓' : '✗'}
                </span>
                <div>
                  <span style={{ fontWeight: 600 }}>{r.individual_name}</span>
                  <span className="text-muted text-sm"> · {r.company_name}</span>
                </div>
                {r.status === 'ok' && (
                  <div style={{ marginLeft: 'auto' }}>
                    <CopyButton
                      text={`Subject: ${r.subject}\n\n${r.body}`}
                      label="Copy Email"
                    />
                  </div>
                )}
              </div>

              {r.status === 'ok' ? (
                <>
                  <div style={{
                    padding: '8px 14px', background: 'var(--bg-glass)',
                    borderRadius: 'var(--radius-sm)', marginBottom: 12,
                    fontWeight: 600, fontSize: '0.9rem',
                    borderLeft: '3px solid var(--accent-1)',
                  }}>
                    {r.subject}
                  </div>
                  <div className="email-preview" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                    {r.body}
                  </div>
                </>
              ) : (
                <div style={{ color: 'var(--status-ignored)', fontSize: '0.875rem', padding: '10px 14px', background: 'rgba(239,68,68,0.06)', borderRadius: 'var(--radius-sm)' }}>
                  ⚠️ {r.error || 'Generation failed'}
                </div>
              )}
            </div>
          ))}

          <div style={{ textAlign: 'center', paddingBottom: 20 }}>
            <a href="#drafts" className="btn btn-secondary btn-sm">View All Drafts →</a>
          </div>
        </div>
      )}
    </div>
  );
}

function PushToGmailButton({ emailId }) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const push = async () => {
    setLoading(true);
    try {
      const r = await api.pushToGmail(emailId);
      if (r.status === 'ok') {
        toast('Draft pushed to Gmail!', 'success');
        if (r.gmail_link) window.open(r.gmail_link, '_blank');
      } else {
        toast(r.message || 'Gmail push failed', 'error');
      }
    } catch (e) { toast(e.message, 'error'); }
    finally { setLoading(false); }
  };
  return (
    <button className="btn btn-secondary btn-sm" disabled={loading} onClick={push}>
      {loading ? <Spinner /> : '📤'} Push to Gmail
    </button>
  );
}

// ════════════════════════════════════════════════════════════
//  Email Drafts Page
// ════════════════════════════════════════════════════════════
export function Drafts() {
  const toast = useToast();
  const [selected, setSelected] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [editMode, setEditMode] = useState(false);
  const [editSubject, setEditSubject] = useState('');
  const [editBody, setEditBody] = useState('');
  const [saving, setSaving] = useState(false);

  const { data: emails, loading, reload } = useApi(
    () => api.getEmails(statusFilter ? { status: statusFilter, limit: 100 } : { limit: 100 }),
    [statusFilter]
  );

  const openDetail = (email) => {
    setSelected(email);
    setEditMode(false);
    setEditSubject(email.subject || '');
    setEditBody(email.body || '');
  };

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateEmail(selected.id, { subject: editSubject, body: editBody });
      setSelected(updated);
      setEditMode(false);
      toast('Email updated', 'success');
      reload();
    } catch (e) { toast(e.message, 'error'); }
    finally { setSaving(false); }
  };

  const approve = async (id) => {
    try {
      await api.approveEmail(id);
      toast('Email approved ✅', 'success');
      setSelected(null);
      reload();
    } catch (e) { toast(e.message, 'error'); }
  };

  const regenerate = async (id) => {
    try {
      await api.regenerateEmail(id);
      toast('Regenerating draft…', 'info');
      setSelected(null);
      reload();
    } catch (e) { toast(e.message, 'error'); }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">📬 Email Drafts</h1>
          <p className="page-subtitle">Review, edit, and approve outreach emails</p>
        </div>
        <div className="flex gap-2">
          <select className="form-select" style={{ width: 'auto' }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="DRAFTED">Drafted</option>
            <option value="SENT">Sent</option>
            <option value="REPLIED">Replied</option>
            <option value="IGNORED">Ignored</option>
            <option value="FOLLOW_UP_SENT">Follow-up Sent</option>
          </select>
          <button className="btn btn-secondary btn-sm" onClick={reload}>🔄</button>
        </div>
      </div>

      {loading ? (
        <div className="loading-overlay"><Spinner size="lg" /></div>
      ) : !emails?.length ? (
        <EmptyState icon="📬" title="No emails yet" text="Generate your first email draft from the Generate page." />
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Recipient</th>
                <th>Company</th>
                <th>Subject</th>
                <th>Status</th>
                <th>Drafted</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {emails.map(e => (
                <tr key={e.id} onClick={() => openDetail(e)} style={{ cursor: 'pointer' }}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{e.recipient_name || '—'}</div>
                    <div className="text-xs font-mono text-muted">{e.recipient_email || '—'}</div>
                  </td>
                  <td className="text-sm">{e.company_name || '—'}</td>
                  <td className="text-sm">{truncate(e.subject, 50)}</td>
                  <td><StatusBadge status={e.status} /></td>
                  <td className="text-xs text-muted">{fmtRelative(e.drafted_at)}</td>
                  <td onClick={ev => ev.stopPropagation()}>
                    <div className="flex gap-1">
                      {e.status === 'DRAFTED' && (
                        <button className="btn btn-primary btn-sm" onClick={() => approve(e.id)}>✅ Approve</button>
                      )}
                      <button className="btn btn-secondary btn-sm" onClick={() => openDetail(e)}>View</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Email Detail Modal */}
      <Modal open={!!selected} onClose={() => setSelected(null)} title="Email Draft" size="xl">
        {selected && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="flex justify-between items-center">
              <div className="flex gap-2 items-center">
                <StatusBadge status={selected.status} />
                <span className="text-xs text-muted">{fmtDate(selected.drafted_at)}</span>
                {selected.llm_model_used && <span className="text-xs text-muted">· {selected.llm_model_used.split('/').pop()}</span>}
              </div>
              <div className="flex gap-2">
                {editMode ? (
                  <>
                    <button className="btn btn-primary btn-sm" disabled={saving} onClick={save}>{saving ? <Spinner /> : '💾 Save'}</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => setEditMode(false)}>Cancel</button>
                  </>
                ) : (
                  <>
                    {selected.status === 'DRAFTED' && <button className="btn btn-secondary btn-sm" onClick={() => setEditMode(true)}>✏️ Edit</button>}
                    {selected.status === 'DRAFTED' && <button className="btn btn-primary btn-sm" onClick={() => approve(selected.id)}>✅ Approve</button>}
                    <button className="btn btn-secondary btn-sm" onClick={() => regenerate(selected.id)}>🔄 Regenerate</button>
                    <PushToGmailButton emailId={selected.id} />
                  </>
                )}
              </div>
            </div>

            <div style={{ padding: '10px 14px', background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)', fontSize: '0.875rem' }}>
              <strong>To:</strong> {selected.recipient_name} &lt;{selected.recipient_email || 'unknown'}&gt;
              {selected.company_name && <> · <strong>Re:</strong> {selected.company_name}</>}
            </div>

            {editMode ? (
              <>
                <div className="form-group">
                  <label className="form-label">Subject</label>
                  <input className="form-input" value={editSubject} onChange={e => setEditSubject(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Body</label>
                  <textarea className="form-textarea" style={{ minHeight: 240 }} value={editBody} onChange={e => setEditBody(e.target.value)} />
                </div>
              </>
            ) : (
              <>
                <div className="email-subject">{selected.subject || 'No subject'}</div>
                <div className="email-preview">{selected.body || 'No body'}</div>
                <CopyButton text={`Subject: ${selected.subject}\n\n${selected.body}`} label="Copy Full Email" />
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
