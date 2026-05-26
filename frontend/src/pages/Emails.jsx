import { useState } from 'react';
import api from '../api';
import { useToast, StatusBadge, Spinner, EmptyState, Modal, CopyButton, ConfirmButton, useApi, fmtDate, fmtRelative, truncate } from '../components';

// ════════════════════════════════════════════════════════════
//  Email Generate Page
// ════════════════════════════════════════════════════════════
export function Generate() {
  const toast = useToast();
  const [step, setStep] = useState(1); // 1=campaign, 2=target, 3=generating, 4=result
  const [campaign, setCampaign] = useState(null);
  const [individual, setIndividual] = useState(null);
  const [company, setCompany] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [forceRefresh, setForceRefresh] = useState(false);

  const { data: campaigns } = useApi(() => api.getCampaigns());
  const { data: companies } = useApi(() => api.getCompanies({ limit: 100 }));
  const { data: individuals } = useApi(() => api.getIndividuals({ limit: 200 }));

  const [newCampName, setNewCampName] = useState('');
  const [newCampDomain, setNewCampDomain] = useState('');
  const [creatingCamp, setCreatingCamp] = useState(false);

  const createCampaign = async () => {
    if (!newCampName || !newCampDomain) return;
    setCreatingCamp(true);
    try {
      const camp = await api.createCampaign({ name: newCampName, domain_target: newCampDomain, created_by: '' });
      setCampaign(camp);
      toast(`Campaign "${camp.name}" created`, 'success');
      setStep(2);
    } catch (e) { toast(e.message, 'error'); }
    finally { setCreatingCamp(false); }
  };

  const generate = async () => {
    if (!campaign || !individual || !company) {
      toast('Select a campaign, individual, and company first.', 'error');
      return;
    }
    setLoading(true);
    setStep(3);
    try {
      const r = await api.generateSingle({
        campaign_id: campaign.id,
        individual_id: individual.id,
        company_id: company.id,
        force_refresh_analysis: forceRefresh,
      });
      setResult(r);
      setStep(4);
    } catch (e) {
      toast(`Generation failed: ${e.message}`, 'error');
      setStep(2);
    } finally { setLoading(false); }
  };

  const reset = () => { setStep(1); setCampaign(null); setIndividual(null); setCompany(null); setResult(null); };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">✉️ Generate Email</h1>
          <p className="page-subtitle">3-call AI pipeline: Individual → Company → Draft</p>
        </div>
      </div>

      {/* Pipeline Steps */}
      <div className="pipeline">
        {['Campaign', 'Target', 'Generating', 'Review'].map((s, i) => (
          <span key={s}>
            <div className={`pipeline-step ${step === i+1 ? 'active' : step > i+1 ? 'done' : ''}`}>
              {step > i+1 ? '✓' : i+1} {s}
            </div>
            {i < 3 && <div className="pipeline-arrow">→</div>}
          </span>
        ))}
      </div>

      {/* Step 1: Campaign */}
      {step === 1 && (
        <div className="card" style={{ maxWidth: 600 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Select or Create Campaign</h3>

          {campaigns?.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div className="form-label">Existing Campaigns</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {campaigns.map(c => (
                  <button key={c.id} className={`btn btn-secondary${campaign?.id === c.id ? ' active' : ''}`}
                    style={{ justifyContent: 'flex-start', ...(campaign?.id === c.id ? { borderColor: 'var(--accent-1)', color: 'var(--accent-1)' } : {}) }}
                    onClick={() => { setCampaign(c); setStep(2); }}>
                    <span style={{ fontWeight: 700 }}>{c.name}</span>
                    <span className="text-muted text-xs" style={{ marginLeft: 'auto' }}>{c.domain_target}</span>
                  </button>
                ))}
              </div>
              <div className="gradient-line" />
            </div>
          )}

          <div className="form-label">Create New Campaign</div>
          <div className="form-group">
            <input className="form-input" placeholder="Campaign name (e.g. Q3 Plant-Based Push)" value={newCampName} onChange={e => setNewCampName(e.target.value)} />
          </div>
          <div className="form-group">
            <input className="form-input" placeholder="Domain target (e.g. vegan, plant-based, alternatives)" value={newCampDomain} onChange={e => setNewCampDomain(e.target.value)} />
          </div>
          <button className="btn btn-primary" disabled={!newCampName || !newCampDomain || creatingCamp} onClick={createCampaign}>
            {creatingCamp ? <><Spinner /> Creating…</> : '+ Create Campaign'}
          </button>
        </div>
      )}

      {/* Step 2: Target selection */}
      {step === 2 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 700 }}>
          <div className="card">
            <div className="flex justify-between items-center mb-4">
              <h3 className="card-title">Campaign: {campaign?.name}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setStep(1)}>← Back</button>
            </div>

            <div className="form-label">Select Individual</div>
            <select className="form-select" style={{ marginBottom: 16 }} value={individual?.id || ''}
              onChange={e => setIndividual(individuals?.find(i => i.id === e.target.value) || null)}>
              <option value="">-- Choose a contact --</option>
              {individuals?.map(i => <option key={i.id} value={i.id}>{i.name} — {i.role || 'Unknown role'} @ {i.company_name || 'Unknown'}</option>)}
            </select>

            <div className="form-label">Select Company</div>
            <select className="form-select" style={{ marginBottom: 20 }} value={company?.id || ''}
              onChange={e => setCompany(companies?.find(c => c.id === e.target.value) || null)}>
              <option value="">-- Choose a company --</option>
              {companies?.map(c => <option key={c.id} value={c.id}>{c.name} {c.sector ? `(${c.sector})` : ''}</option>)}
            </select>

            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 20, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={forceRefresh} onChange={e => setForceRefresh(e.target.checked)} />
              Force refresh analysis (ignore cached results)
            </label>

            {individual && company && (
              <div style={{ padding: '14px 16px', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', marginBottom: 16, fontSize: '0.875rem' }}>
                <div><strong>📧 To:</strong> {individual.name} ({individual.email || 'no email'}) — {individual.role}</div>
                <div style={{ marginTop: 4 }}><strong>🏢 Re:</strong> {company.name} — {company.sector || company.product_type || ''}</div>
              </div>
            )}

            <button className="btn btn-primary btn-lg w-full" disabled={!individual || !company} onClick={generate}>
              🚀 Generate Email Draft
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Generating */}
      {step === 3 && (
        <div className="card" style={{ maxWidth: 500, textAlign: 'center' }}>
          <div style={{ marginBottom: 20 }}>
            <Spinner size="lg" />
          </div>
          <h3 style={{ marginBottom: 8 }}>Running 3-Call AI Pipeline</h3>
          <p className="text-secondary text-sm">
            Call 1 → Individual analysis ({individual?.name})<br />
            Call 2 → Company analysis ({company?.name})<br />
            Call 3 → Drafting personalized email…
          </p>
        </div>
      )}

      {/* Step 4: Result */}
      {step === 4 && result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 800 }}>
          <div className="flex justify-between items-center">
            <div>
              <StatusBadge status={result.status === 'ok' ? 'drafted' : 'error'} />
              <span className="text-sm text-muted" style={{ marginLeft: 12 }}>
                {result.total_tokens} tokens · {result.model_used?.split('/').pop() || 'AI'}
              </span>
            </div>
            <div className="flex gap-2">
              <button className="btn btn-secondary btn-sm" onClick={reset}>+ New Email</button>
            </div>
          </div>

          {result.status === 'no_api_key' ? (
            <div className="card">
              <div style={{ color: 'var(--status-ignored)', fontWeight: 600, marginBottom: 8 }}>⚠️ OPENROUTER_API_KEY not configured</div>
              <p className="text-sm text-secondary">Add your OpenRouter API key to the backend <code>.env</code> file to enable email generation.</p>
            </div>
          ) : (
            <>
              <div className="card">
                <div className="email-subject">Subject: {result.subject || 'No subject generated'}</div>
                <div className="email-preview">{result.body || 'No body generated'}</div>
                <div className="flex gap-2 mt-4">
                  <CopyButton text={`Subject: ${result.subject}\n\n${result.body}`} label="Copy Email" />
                  {result.email_id && <PushToGmailButton emailId={result.email_id} />}
                </div>
              </div>

              <div className="grid-2">
                <div className="card card-sm">
                  <div className="form-label" style={{ marginBottom: 10 }}>👤 Individual Analysis</div>
                  {result.individual_analysis && Object.entries(result.individual_analysis).map(([k, v]) => (
                    <div key={k} style={{ marginBottom: 8 }}>
                      <div className="text-xs text-muted" style={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.replace('_', ' ')}</div>
                      <div className="text-sm text-secondary">{v}</div>
                    </div>
                  ))}
                </div>
                <div className="card card-sm">
                  <div className="form-label" style={{ marginBottom: 10 }}>🏢 Company Analysis</div>
                  {result.company_analysis && Object.entries(result.company_analysis).map(([k, v]) => (
                    <div key={k} style={{ marginBottom: 8 }}>
                      <div className="text-xs text-muted" style={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.replace('_', ' ')}</div>
                      <div className="text-sm text-secondary">{v}</div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
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
