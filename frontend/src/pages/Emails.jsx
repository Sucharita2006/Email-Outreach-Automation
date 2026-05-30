import { useState, useEffect, Fragment } from 'react';
import api from '../api';
import { useToast, StatusBadge, Spinner, EmptyState, Modal, CopyButton, ConfirmButton, useApi, fmtDate, fmtRelative, truncate } from '../components';
import { Building, Users, Mail, MessageSquare, AlertCircle, Briefcase, Rocket, FolderOpen } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';

// ════════════════════════════════════════════════════════════
//  Email Generate Page — Domain-Driven Wizard
// ════════════════════════════════════════════════════════════
export function Generate() {
  const toast = useToast();

  // Step 1 — Campaign Setup
  const [campName, setCampName] = useState('');
  const [domain, setDomain] = useState('');
  const [purpose, setPurpose] = useState('');
  
  const { data: campaigns } = useApi(() => api.getCampaigns());
  const PREDEFINED_DOMAINS = [
    'animal welfare', 'veganism', 'plant-based', 'fermentation', 
    'cellular agriculture', 'alternative proteins', 'factory farming', 'animal rights'
  ];
  const allDomains = [...PREDEFINED_DOMAINS, ...(campaigns || []).map(c => c.domain_target)].filter(Boolean);
  const uniqueDomains = Object.values(allDomains.reduce((acc, d) => {
    const key = d.toLowerCase().replace(/[- ]/g, '');
    if (!acc[key]) acc[key] = d;
    return acc;
  }, {}));
  const [discovering, setDiscovering] = useState(false);
  const [discoverProgress, setDiscoverProgress] = useState(0);

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
  const [selectedResultIds, setSelectedResultIds] = useState(new Set());
  const [pushingBulk, setPushingBulk] = useState(false);
  
  const validResults = genResults.filter(r => r.status === 'ok' && !r._deleted);
  const allResultsSelected = validResults.length > 0 && validResults.every(r => selectedResultIds.has(r.email_id));
    
  const toggleAllResultIds = () => {
    if (allResultsSelected) setSelectedResultIds(new Set());
    else setSelectedResultIds(new Set(validResults.map(r => r.email_id)));
  };

  const toggleResultId = (id) => {
    setSelectedResultIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  
  const handleBulkPush = async () => {
    if (selectedResultIds.size === 0) return;
    setPushingBulk(true);
    let successCount = 0;
    try {
      for (const id of selectedResultIds) {
        const res = await api.pushToGmail(id);
        if (res.status === 'ok') successCount++;
      }
      toast(`Successfully pushed ${successCount} emails to Gmail!`, 'success');
      setSelectedResultIds(new Set());
    } catch (e) {
      toast(`Bulk push failed: ${e.message}`, 'error');
    } finally {
      setPushingBulk(false);
    }
  };

  // ── Step 1: Discover ──────────────────────────────────────
  const discover = async () => {
    if (!campName.trim() || !domain.trim() || !purpose.trim()) {
      toast('Fill in campaign name, domain, and purpose.', 'error');
      return;
    }
    setDiscovering(true);
    setDiscoverProgress(0);

    const interval = setInterval(() => {
      setDiscoverProgress(p => {
        if (p >= 95) return p;
        return p + Math.random() * 5 + 1;
      });
    }, 1000);

    try {
      const res = await api.discoverTargets({
        campaign_name: campName.trim(),
        domain: domain.trim(),
        campaign_purpose: purpose.trim(),
        limit: 30,
      });
      clearInterval(interval);
      setDiscoverProgress(100);
      
      setTimeout(() => {
        setCampaignId(res.campaign_id);
        setDiscovered(res);
        setSelectedCompanyIds(new Set());
        setSelectedIndividualIds(new Set());
        setStep(2);
        toast(`Found ${res.total_companies} companies and ${res.total_individuals} individuals.`, 'success');
        setDiscovering(false);
      }, 500);
    } catch (e) {
      clearInterval(interval);
      setDiscoverProgress(0);
      toast(`Discovery failed: ${e.message}`, 'error');
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

    // Selected individuals — pair with their company if available, otherwise standalone
    for (const indId of selectedIndividualIds) {
      const ind = individualsById[indId];
      if (!ind) continue;
      targets.push({
        individual_id: indId,
        company_id: ind.company_id || null,
      });
    }

    // Selected companies — use their best contact if available, otherwise send to company directly
    for (const compId of selectedCompanyIds) {
      const comp = companiesByid[compId];
      if (!comp) continue;
      if (comp.best_contact_id) {
        // avoid duplicates if somehow already added
        if (!targets.find(t => t.company_id === compId && t.individual_id === comp.best_contact_id)) {
          targets.push({ individual_id: comp.best_contact_id, company_id: compId });
        }
      } else {
        // No specific contact — send to company directly
        if (!targets.find(t => t.company_id === compId)) {
          targets.push({ individual_id: null, company_id: compId });
        }
      }
    }

    if (targets.length === 0) {
      toast('No valid targets found. Make sure selected targets have a valid contact person.', 'error');
      return;
    }

    // Init progress rows
    setGenResults(targets.map(t => {
      const comp = companiesByid[t.company_id];
      const indName = individualsById[t.individual_id]?.name || (comp?.best_contact_id === t.individual_id ? comp?.best_contact_name : '…');
      return {
        individual_id: t.individual_id,
        company_id: t.company_id,
        individual_name: indName,
        company_name: comp?.name || '…',
        status: 'pending',
      };
    }));
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
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="page-header shrink-0">
        <div>
          <h1 className="page-title"><Rocket className="inline-block w-6 h-6 mr-1" style={{ WebkitTextFillColor: 'initial', color: '#818cf8', verticalAlign: '-3px' }} /> Start Campaign</h1>
          <p className="page-subtitle">Enter your domain → discover targets → generate personalized emails</p>
        </div>
        {step > 1 && <button className="btn btn-ghost btn-sm" onClick={reset}>↩ Start Over</button>}
      </div>

      {/* Step indicators */}
      <div className="pipeline shrink-0" style={{ marginBottom: 28 }}>
        {['Campaign Setup', 'Select Targets', 'Generating', 'Review'].map((s, i) => (
          <Fragment key={s}>
            <div className={`pipeline-step ${step === i+1 ? 'active' : step > i+1 ? 'done' : ''}`}>
              {step > i+1 ? '✓' : i+1} {s}
            </div>
            {i < 3 && <div className="pipeline-arrow">→</div>}
          </Fragment>
        ))}
      </div>

      <div className="flex-1 w-full pr-4 flex flex-col overflow-hidden">
        {/* ── Step 1: Campaign Setup ── */}
        {step === 1 && (
        <ScrollArea className="flex-1 w-full">
        <div className="flex justify-center items-start pt-4 w-full h-full pb-10">
          <div className="card w-full" style={{ maxWidth: 680 }}>
            <h3 className="card-title" style={{ marginBottom: 20 }}>Campaign Setup</h3>

          <div className="form-group">
            <label className="form-label">Campaign Name</label>
            <input className="form-input" placeholder="e.g. Q3 Plant-Based Outreach"
              value={campName} onChange={e => setCampName(e.target.value)} />
          </div>

          <div className="form-group">
            <label className="form-label">Domain</label>
            <input className="form-input" placeholder="e.g. plant-based, fermentation, animal-welfare"
              list="domain-suggestions"
              value={domain} onChange={e => setDomain(e.target.value)} />
            <datalist id="domain-suggestions">
              {domain.trim().length > 0 && uniqueDomains
                .filter(d => d.toLowerCase().startsWith(domain.trim().toLowerCase()))
                .map(d => <option key={d} value={d} />)}
            </datalist>
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
            {discovering ? <><Spinner /> Discovering &amp; finding contacts…</> : '🔍 Discover Targets'}
          </button>

          {discovering && (
            <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', padding: '12px 16px', borderRadius: 'var(--radius-md)' }}>
                <div style={{ fontSize: '1.2rem' }}>⏳</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  <span style={{ color: 'var(--text)', fontWeight: 600 }}>Please be patient.</span> This process can take up to 3-4 minutes to complete. Hold tight while we fetch all the contacts for you!
                </div>
              </div>
              <div style={{ width: '100%', height: 6, background: 'var(--bg-glass)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${discoverProgress}%`, height: '100%', background: 'var(--accent-1)', transition: 'width 0.5s ease-out' }} />
              </div>
            </div>
          )}
          </div>
        </div>
        </ScrollArea>
      )}

      {/* ── Step 2: Target Selection ── */}
      {step === 2 && discovered && (
        <div className="flex-1 flex flex-col h-full overflow-hidden w-full" style={{ gap: 16 }}>

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
            <span className="text-xs" style={{ marginLeft: 'auto', color: 'var(--status-replied)' }}>
              ✓ Discovery complete
            </span>
          </div>

          <div className="grid-2 flex-1 overflow-hidden" style={{ alignItems: 'stretch', minHeight: 0 }}>

            {/* Companies column */}
            <div className="card flex-1 flex flex-col overflow-hidden" style={{ padding: 0 }}>
              <div className="shrink-0" style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
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
                <ScrollArea className="flex-1 w-full">
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
                        {c.best_contact_name ? (
                          <div className="text-xs" style={{ marginTop: 6, color: 'var(--accent-1)', fontWeight: 500 }}>
                            ↳ Contact: {c.best_contact_name} {c.best_contact_role && `— ${c.best_contact_role}`}
                          </div>
                        ) : (
                          <div className="text-xs" style={{ marginTop: 6, color: '#ef4444', fontStyle: 'italic' }}>
                            ↳ Contact: Email not found
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </ScrollArea>
              )}
            </div>

            {/* Individuals column */}
            <div className="card flex-1 flex flex-col overflow-hidden" style={{ padding: 0 }}>
              <div className="shrink-0" style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
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
                <ScrollArea className="flex-1 w-full">
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
                        {i.email ? (
                          <div className="text-xs font-mono text-muted" style={{ marginTop: 2 }}>{i.email}</div>
                        ) : (
                          <div className="text-xs" style={{ marginTop: 2, color: '#ef4444' }}>Email not found</div>
                        )}
                        {i.relevance_reason && (
                          <div className="text-xs text-secondary" style={{ marginTop: 4, lineHeight: 1.4 }}>
                            {i.relevance_reason.slice(0, 100)}{i.relevance_reason.length > 100 ? '…' : ''}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </ScrollArea>
              )}
            </div>
          </div>

          {/* Generate bar */}
          <div className="shrink-0" style={{
            display: 'flex', alignItems: 'center', gap: 16,
            padding: '16px 20px', background: 'var(--bg-glass)',
            border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
            marginTop: 8,
          }}>
            <span className="text-sm">
              {totalSelected === 0
                ? 'Select targets above to start campaign'
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
        <ScrollArea className="flex-1 w-full">
        <div className="card" style={{ maxWidth: 700 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', padding: '12px 16px', borderRadius: 'var(--radius-md)', marginBottom: 20 }}>
            <div style={{ fontSize: '1.2rem' }}>⏳</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <span style={{ color: 'var(--text)', fontWeight: 600 }}>Please be patient.</span> We are running our 3-call AI pipeline per target to generate highly personalized emails. This can take up to 3-4 minutes to complete. Hold tight!
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
        </ScrollArea>
      )}

      {/* ── Step 4: Review Results ── */}
      {step === 4 && genResults.length > 0 && (
        <ScrollArea className="flex-1 w-full">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="flex justify-between items-center">
            <div>
              <span style={{ fontWeight: 700, fontSize: '1.1rem' }}>
                {validResults.length} / {genResults.filter(r => !r._deleted).length} emails generated
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
          
          {validResults.length > 0 && (
            <div style={{ 
              display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', 
              background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)',
              position: 'sticky', top: 16, zIndex: 10, backdropFilter: 'blur(8px)',
              boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
            }}>
              <input type="checkbox" checked={allResultsSelected} onChange={toggleAllResultIds} style={{ cursor: 'pointer' }} id="select-all-results" />
              <label htmlFor="select-all-results" className="text-sm" style={{ fontWeight: 600, cursor: 'pointer', margin: 0 }}>
                Select All ({validResults.length})
              </label>
              
              <button 
                className="btn btn-primary btn-sm" 
                style={{ marginLeft: 'auto' }}
                disabled={selectedResultIds.size === 0 || pushingBulk}
                onClick={handleBulkPush}
              >
                {pushingBulk ? <Spinner /> : '📤'} Push {selectedResultIds.size > 0 ? selectedResultIds.size : ''} Selected to Gmail
              </button>
            </div>
          )}

          {genResults.map((r, idx) => (
            !r._deleted && (
              <EmailResultCard
                key={r.email_id || idx}
                result={r}
                idx={idx}
                campaignId={campaignId}
                selected={selectedResultIds.has(r.email_id)}
                onToggle={() => toggleResultId(r.email_id)}
                onDeleted={() => {
                  setGenResults(prev => prev.map((p, i) => i === idx ? { ...p, _deleted: true } : p));
                  toast('Email deleted.', 'success');
                }}
                onRegenerated={(newResult) => {
                  setGenResults(prev => prev.map((p, i) => i === idx ? { ...newResult, individual_name: p.individual_name, company_name: p.company_name } : p));
                  if (newResult.status === 'ok') {
                    toast('Email regenerated!', 'success');
                  }
                }}
              />
            )
          ))}
        </div>
        </ScrollArea>
      )}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
//  EmailResultCard — Individual email card with Save/Delete/Regenerate
// ════════════════════════════════════════════════════════════
function EmailResultCard({ result: r, idx, onDeleted, onRegenerated, selected, onToggle, campaignId }) {
  const toast = useToast();
  const [deleting, setDeleting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [showRegenInput, setShowRegenInput] = useState(false);
  const [regenFeedback, setRegenFeedback] = useState('');

  const [editing, setEditing] = useState(false);
  const [editSubject, setEditSubject] = useState(r.subject);
  const [editBody, setEditBody] = useState(r.body);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(r.status === 'SENT');

  // Poll for regenerated email when status is processing
  useEffect(() => {
    if (r.status !== 'processing' || !campaignId) return;
    
    const targetId = r.individual_id || r.company_id;
    const interval = setInterval(async () => {
      try {
        const latestEmails = await api.getEmails({ campaign_id: campaignId });
        const newEmail = latestEmails.find(e => e.target_id === targetId && e.id !== r.email_id && e.status !== 'archived');
        
        if (newEmail) {
          clearInterval(interval);
          onRegenerated({
            ...r,
            email_id: newEmail.id,
            subject: newEmail.subject,
            body: newEmail.body,
            status: 'ok',
            recipient_name: newEmail.recipient_name || r.individual_name,
            company_name: newEmail.company_name || r.company_name
          });
        }
      } catch (e) {
        console.error("Polling error:", e);
      }
    }, 3000);
    
    return () => clearInterval(interval);
  }, [r.status, r.email_id, r.individual_id, r.company_id, campaignId, onRegenerated]);

  const handleSave = async () => {
    if (!r.email_id) return;
    setSaving(true);
    try {
      const updated = await api.updateEmail(r.email_id, { subject: editSubject, body: editBody });
      onRegenerated(updated);
      setEditing(false);
      toast('Draft updated!', 'success');
    } catch (e) {
      toast(`Update failed: ${e.message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleSend = async () => {
    if (!r.email_id) return;
    setSending(true);
    try {
      await api.sendEmailDirectly(r.email_id);
      setSent(true);
      toast('Email sent directly! 🚀', 'success');
      // Update selected state to remove this one since it's no longer a draft
      if (selected) onToggle();
    } catch (e) {
      toast(`Send failed: ${e.message}`, 'error');
    } finally {
      setSending(false);
    }
  };

  const handleDelete = async () => {
    if (!r.email_id) return;
    setDeleting(true);
    try {
      await api.deleteEmail(r.email_id);
      onDeleted();
    } catch (e) {
      toast(`Delete failed: ${e.message}`, 'error');
      setDeleting(false);
    }
  };

  const handleRegenerate = async () => {
    if (!r.email_id || !regenFeedback.trim()) {
      toast('Please describe what changes you want.', 'error');
      return;
    }
    setRegenerating(true);
    try {
      const res = await api.regenerateEmail(r.email_id, regenFeedback.trim());
      setShowRegenInput(false);
      setRegenFeedback('');
      onRegenerated(res);
    } catch (e) {
      toast(`Regenerate failed: ${e.message}`, 'error');
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="card" style={{
      transition: 'all 0.3s ease',
      opacity: deleting ? 0.4 : 1,
      background: selected ? 'var(--bg-glass)' : 'var(--bg-card)',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        {r.status === 'ok' && (
          <input type="checkbox" checked={selected} onChange={onToggle} style={{ cursor: 'pointer', marginTop: 2 }} />
        )}
        <span style={{
          width: 28, height: 28, borderRadius: '50%', display: 'flex',
          alignItems: 'center', justifyContent: 'center', fontSize: '0.85rem', fontWeight: 700,
          background: r.status === 'ok' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
          color: r.status === 'ok' ? '#22c55e' : '#ef4444',
        }}>
          {r.status === 'ok' ? '✓' : r.status === 'processing' ? <Spinner size="sm" /> : '✗'}
        </span>
        <div>
          <div style={{ fontWeight: 600 }}>
            {r.individual_name || r.recipient_name}
            <span className="text-muted text-sm" style={{ fontWeight: 400 }}> · {r.company_name}</span>
          </div>
          {r.recipient_email && (
            <div className="text-muted text-sm" style={{ marginTop: 4 }}>
              ✉️ {r.recipient_email}
            </div>
          )}
        </div>
      </div>

      {/* Email Content */}
      {r.status === 'processing' ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 150 }}>
           <Spinner size="md" />
           <div className="mt-4 text-muted text-sm">Regenerating email... This may take up to a minute.</div>
        </div>
      ) : r.status === 'ok' ? (
        <>
          {editing ? (
            <div style={{ padding: '10px 0', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input
                className="form-input"
                value={editSubject}
                onChange={e => setEditSubject(e.target.value)}
                placeholder="Subject"
              />
              <textarea
                className="form-input"
                value={editBody}
                onChange={e => setEditBody(e.target.value)}
                style={{ height: 250, resize: 'vertical' }}
              />
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
                  {saving ? <Spinner /> : '💾 Save'}
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => {
                  setEditing(false);
                  setEditSubject(r.subject);
                  setEditBody(r.body);
                }} disabled={saving}>Cancel</button>
              </div>
            </div>
          ) : (
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
          )}

          {/* ── Action Buttons ── */}
          {!sent ? (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              marginTop: 16, paddingTop: 14,
              borderTop: '1px solid var(--border)',
              flexWrap: 'wrap'
            }}>
              <button
                className="btn btn-sm"
                style={{
                  background: 'rgba(239,68,68,0.08)',
                  color: '#ef4444', border: '1px solid rgba(239,68,68,0.25)',
                }}
                disabled={deleting || editing}
                onClick={handleDelete}
              >
                {deleting ? <Spinner /> : '🗑️ Delete'}
              </button>

              <button
                className="btn btn-sm"
                style={{
                  background: showRegenInput ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.08)',
                  color: '#3b82f6', border: '1px solid rgba(59,130,246,0.25)',
                }}
                disabled={regenerating || editing}
                onClick={() => setShowRegenInput(!showRegenInput)}
              >
                🔄 Regenerate
              </button>
              
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setEditing(true)}
                disabled={editing}
              >
                ✏️ Edit
              </button>

              <button
                className="btn btn-sm"
                style={{
                  background: 'linear-gradient(135deg, #3b82f6, #2563eb)', color: 'white', border: 'none'
                }}
                disabled={sending || editing}
                onClick={handleSend}
              >
                {sending ? <Spinner /> : '🚀 Send Directly'}
              </button>

              <div style={{ marginLeft: 'auto' }}>
                <CopyButton
                  text={`Subject: ${r.subject}\n\n${r.body}`}
                  label="Copy Full Email"
                />
              </div>
            </div>
          ) : (
            <div style={{
              marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--border)',
              color: '#22c55e', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6
            }}>
              ✅ Email sent directly!
            </div>
          )}

          {/* ── Regenerate Feedback Input ── */}
          {showRegenInput && (
            <div style={{
              marginTop: 12, padding: 16,
              background: 'rgba(59,130,246,0.04)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid rgba(59,130,246,0.15)',
              animation: 'fadeIn 0.2s ease-out',
            }}>
              <label style={{ display: 'block', fontWeight: 600, fontSize: '0.85rem', marginBottom: 8, color: '#3b82f6' }}>
                What changes would you like?
              </label>
              <textarea
                value={regenFeedback}
                onChange={e => setRegenFeedback(e.target.value)}
                placeholder="e.g. Make the tone more casual, shorten the email, focus more on sustainability partnerships..."
                rows={3}
                style={{
                  width: '100%', padding: '10px 12px',
                  background: 'var(--bg-card)', color: 'var(--text-primary)',
                  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                  resize: 'vertical', fontFamily: 'inherit', fontSize: '0.875rem',
                  lineHeight: 1.5,
                }}
              />
              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                <button
                  className="btn btn-sm"
                  style={{
                    background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
                    color: '#fff', border: 'none', fontWeight: 600,
                  }}
                  disabled={regenerating || !regenFeedback.trim()}
                  onClick={handleRegenerate}
                >
                  {regenerating ? <><Spinner /> Regenerating...</> : '🔄 Regenerate with Changes'}
                </button>
                <button
                  className="btn btn-sm btn-secondary"
                  onClick={() => { setShowRegenInput(false); setRegenFeedback(''); }}
                  disabled={regenerating}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div style={{ color: 'var(--status-ignored)', fontSize: '0.875rem', padding: '10px 14px', background: 'rgba(239,68,68,0.06)', borderRadius: 'var(--radius-sm)' }}>
          ⚠️ {r.error || 'Generation failed'}
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
export function Campaigns({ campaignId, navigate }) {
  if (campaignId) {
    return <CampaignDetail campaignId={campaignId} onBack={() => navigate('campaigns')} />;
  }
  return <CampaignList onSelect={(id) => navigate('campaigns', { campaignId: id })} />;
}

function CampaignList({ onSelect }) {
  const { data: campaigns, loading } = useApi(() => api.getCampaigns());

  if (loading) return <div className="loading-overlay"><Spinner size="lg" /></div>;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="page-header shrink-0">
        <div>
          <h1 className="page-title"><FolderOpen className="inline-block w-6 h-6 mr-1" style={{ WebkitTextFillColor: 'initial', color: '#818cf8', verticalAlign: '-3px' }} /> Campaigns</h1>
          <p className="page-subtitle">Manage your outreach campaigns</p>
        </div>
      </div>
      {!campaigns?.length ? (
        <EmptyState icon="📋" title="No campaigns yet" text="Create a campaign from the Generate page." />
      ) : (
        <div className="flex-1 w-full rounded-md border border-white/10 bg-black/20 overflow-y-auto relative">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Domain</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map(c => (
                  <tr key={c.id} onClick={() => onSelect(c.id)} style={{ cursor: 'pointer' }}>
                    <td style={{ fontWeight: 600 }}>{c.name}</td>
                    <td>{c.domain_target}</td>
                    <td><StatusBadge status={c.status} /></td>
                    <td className="text-sm text-muted">{fmtDate(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function CampaignDetail({ campaignId, onBack }) {
  const toast = useToast();
  const [tab, setTab] = useState('targets'); // 'targets' | 'emails'
  const [statusFilter, setStatusFilter] = useState('');
  
  // Modals for emails
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [editSubject, setEditSubject] = useState('');
  const [editBody, setEditBody] = useState('');
  const [editRecipientEmail, setEditRecipientEmail] = useState('');
  const [saving, setSaving] = useState(false);
  const [showRegeneratePrompt, setShowRegeneratePrompt] = useState(false);
  const [regenerateFeedback, setRegenerateFeedback] = useState('');
  const [regeneratingTargetId, setRegeneratingTargetId] = useState(null);

  // Selection & Generation for Targets tab
  const [selectedCompanyIds, setSelectedCompanyIds] = useState(new Set());
  const [selectedIndividualIds, setSelectedIndividualIds] = useState(new Set());
  const [generating, setGenerating] = useState(false);
  const [polling, setPolling] = useState(false);
  // Fetch data
  const { data: campaign, loading: campLoading } = useApi(async () => {
    const list = await api.getCampaigns();
    return list.find(c => c.id === campaignId);
  }, [campaignId]);

  const { data: companies, loading: compLoading } = useApi(() => api.getCompanies({ campaign_id: campaignId, limit: 100 }), [campaignId]);
  const { data: individuals, loading: indLoading } = useApi(() => api.getIndividuals({ campaign_id: campaignId, limit: 100 }), [campaignId]);
  
  const { data: emails, loading: emailsLoading, reload: reloadEmails } = useApi(
    () => api.getEmails({ campaign_id: campaignId, status: statusFilter || undefined, limit: 100 }),
    [campaignId, statusFilter]
  );

  const handleRefresh = async () => {
    setPolling(true);
    try {
      await api.pollGmail(campaignId);
    } catch (e) {
      console.error('Failed to poll Gmail:', e);
    } finally {
      setPolling(false);
      reloadEmails();
    }
  };

  const openDetail = (email) => {
    setSelectedEmail(email);
    setEditMode(false);
    setEditSubject(email.subject || '');
    setEditBody(email.body || '');
    setEditRecipientEmail(email.recipient_email || '');
    setShowRegeneratePrompt(false);
    setRegenerateFeedback('');
    setRegeneratingTargetId(null);
  };

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateEmail(selectedEmail.id, { subject: editSubject, body: editBody, recipient_email: editRecipientEmail });
      setSelectedEmail(updated);
      setEditMode(false);
      toast('Email updated', 'success');
      reloadEmails();
    } catch (e) { toast(e.message, 'error'); }
    finally { setSaving(false); }
  };

  const approve = async (id) => {
    try {
      await api.approveEmail(id);
      toast('Email approved ✅', 'success');
      setSelectedEmail(null);
      reloadEmails();
    } catch (e) { toast(e.message, 'error'); }
  };

  const sendDirectly = async (id) => {
    try {
      toast('Sending email...', 'info');
      await api.sendEmailDirectly(id);
      toast('Email sent successfully 🚀', 'success');
      setSelectedEmail(null);
      reloadEmails();
    } catch (e) { toast(e.message, 'error'); }
  };

  const pollRegeneration = (targetId, oldEmailId) => {
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      if (attempts > 30) {
        clearInterval(interval);
        setRegeneratingTargetId(null);
        toast("Regeneration timed out", "error");
        return;
      }
      try {
        const latestEmails = await api.getEmails({ campaign_id: campaignId });
        const newEmail = latestEmails.find(e => e.target_id === targetId && e.id !== oldEmailId && e.status !== 'archived');
        if (newEmail) {
          clearInterval(interval);
          setRegeneratingTargetId(null);
          setSelectedEmail(newEmail);
          reloadEmails();
          toast("Draft regenerated successfully!", "success");
        }
      } catch (e) {
        console.error(e);
      }
    }, 3000);
  };

  const regenerate = async (id) => {
    try {
      const targetId = selectedEmail.target_id;
      setRegeneratingTargetId(targetId);
      await api.regenerateEmail(id, regenerateFeedback);
      toast('Regenerating draft in background…', 'info');
      setShowRegeneratePrompt(false);
      setRegenerateFeedback('');
      pollRegeneration(targetId, id);
    } catch (e) { 
      setRegeneratingTargetId(null);
      toast(e.message, 'error'); 
    }
  };

  const generateSelected = async () => {
    const targets = [];
    const companiesByid = Object.fromEntries((companies||[]).map(c => [c.id, c]));
    
    for (const indId of selectedIndividualIds) {
      const ind = individuals?.find(i => i.id === indId);
      if (ind) targets.push({ individual_id: ind.id, company_id: ind.company_id });
    }
    
    for (const compId of selectedCompanyIds) {
      const comp = companiesByid[compId];
      if (!comp) continue;
      if (comp.best_contact_id) {
        if (!targets.find(t => t.company_id === compId && t.individual_id === comp.best_contact_id)) {
          targets.push({ individual_id: comp.best_contact_id, company_id: compId });
        }
      } else {
        if (!targets.find(t => t.company_id === compId)) {
          targets.push({ individual_id: null, company_id: compId });
        }
      }
    }

    if (targets.length === 0) {
      toast('Please select at least one target.', 'error');
      return;
    }

    setGenerating(true);
    try {
      const res = await api.generateCampaignTargets({
        campaign_id: campaignId,
        targets,
        force_refresh_analysis: false,
      });
      toast(`${res.ok} email(s) generated.`, res.ok > 0 ? 'success' : 'error');
      setSelectedCompanyIds(new Set());
      setSelectedIndividualIds(new Set());
      setTab('emails');
      reloadEmails();
    } catch (e) {
      toast(`Generation failed: ${e.message}`, 'error');
    } finally {
      setGenerating(false);
    }
  };

  const selectUndrafted = () => {
    const draftedIndIds = new Set(emails?.filter(e => e.target_type === 'individual').map(e => e.target_id));
    const draftedCompIds = new Set(emails?.filter(e => e.target_type === 'company').map(e => e.target_id));
    
    // Also mark companies as drafted if their name matches any email's company_name
    emails?.forEach(e => {
      if (e.company_name) {
        const comp = companies?.find(c => c.name === e.company_name);
        if (comp) draftedCompIds.add(comp.id);
      }
    });
    
    const newSelInd = new Set();
    const newSelComp = new Set();
    
    individuals?.forEach(i => {
      if (!draftedIndIds.has(i.id)) newSelInd.add(i.id);
    });
    
    companies?.forEach(c => {
      if (!draftedCompIds.has(c.id)) newSelComp.add(c.id);
    });
    
    setSelectedIndividualIds(newSelInd);
    setSelectedCompanyIds(newSelComp);
  };


  if (campLoading) return <div className="loading-overlay"><Spinner size="lg" /></div>;
  if (!campaign) return <div>Campaign not found.</div>;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="page-header shrink-0">
        <div>
          <button className="btn btn-secondary btn-sm mb-2" onClick={onBack}>← Back to Campaigns</button>
          <h1 className="page-title">{campaign.name}</h1>
          <p className="page-subtitle">Domain: {campaign.domain_target} · Status: <StatusBadge status={campaign.status} /></p>
        </div>
      </div>

      <div className="shrink-0" style={{ display: 'flex', gap: 10, marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 10 }}>
        <button className={`btn ${tab === 'targets' ? 'btn-primary' : 'btn-secondary'} btn-sm`} onClick={() => setTab('targets')}>Targets ({companies?.length + individuals?.length || 0})</button>
        <button className={`btn ${tab === 'emails' ? 'btn-primary' : 'btn-secondary'} btn-sm`} onClick={() => setTab('emails')}>Emails ({emails?.length || 0})</button>
      </div>

      {tab === 'targets' && (
        <div className="flex-1 flex flex-col overflow-hidden w-full pr-4">
          <div className="shrink-0" style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            <button className="btn btn-sm btn-secondary" onClick={selectUndrafted}>
              ✓ Select Undrafted
            </button>
            <button className="btn btn-sm btn-primary" onClick={generateSelected} disabled={generating || (selectedCompanyIds.size === 0 && selectedIndividualIds.size === 0)}>
              {generating ? <Spinner /> : '⚡'} Start Campaign for Selected
            </button>
          </div>
          <div className="grid-2 shrink-0">
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
                <h3 className="card-title" style={{ margin: 0 }}>Companies Discovered</h3>
              </div>
              {compLoading ? <div style={{ padding: 16 }}><Spinner /></div> : (
                <ScrollArea className="h-[420px] w-full">
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    {companies?.map(c => {
                      const isDrafted = emails?.some(e => 
                        (e.target_type === 'company' && e.target_id === c.id) ||
                        (e.company_name === c.name)
                      );
                      const isSelected = selectedCompanyIds.has(c.id);
                      return (
                        <div key={c.id} style={{ 
                          padding: '12px 16px', borderBottom: '1px solid var(--border)',
                          background: isSelected ? 'var(--bg-glass)' : 'transparent', 
                          display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer',
                          transition: 'background 0.15s'
                        }}
                        onClick={() => {
                          const next = new Set(selectedCompanyIds);
                          next.has(c.id) ? next.delete(c.id) : next.add(c.id);
                          setSelectedCompanyIds(next);
                        }}>
                          <input type="checkbox" checked={isSelected} style={{ marginTop: 3, cursor: 'pointer', flexShrink: 0 }}
                            onChange={() => {}} />
                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.9rem', marginBottom: 4 }}>
                              {c.name}
                              {isDrafted && <span className="badge" style={{ background: 'rgba(34,197,94,0.15)', color: '#22c55e', fontSize: '0.65rem' }}>Drafted</span>}
                            </div>
                            <div className="text-xs text-muted">{c.website}</div>
                          </div>
                        </div>
                      );
                    })}
                    {!companies?.length && <div style={{ padding: '20px 16px', color: 'var(--text-muted)', fontSize: '0.875rem', textAlign: 'center' }}>No companies found.</div>}
                  </div>
                </ScrollArea>
              )}
            </div>
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
                <h3 className="card-title" style={{ margin: 0 }}>Individuals Discovered</h3>
              </div>
              {indLoading ? <div style={{ padding: 16 }}><Spinner /></div> : (
                <ScrollArea className="h-[420px] w-full">
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    {individuals?.map(i => {
                      const isDrafted = emails?.some(e => e.target_type === 'individual' && e.target_id === i.id);
                      const isSelected = selectedIndividualIds.has(i.id);
                      return (
                        <div key={i.id} style={{ 
                          padding: '12px 16px', borderBottom: '1px solid var(--border)',
                          background: isSelected ? 'var(--bg-glass)' : 'transparent', 
                          display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer',
                          transition: 'background 0.15s'
                        }}
                        onClick={() => {
                          const next = new Set(selectedIndividualIds);
                          next.has(i.id) ? next.delete(i.id) : next.add(i.id);
                          setSelectedIndividualIds(next);
                        }}>
                          <input type="checkbox" checked={isSelected} style={{ marginTop: 3, cursor: 'pointer', flexShrink: 0 }}
                            onChange={() => {}} />
                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.9rem', marginBottom: 4 }}>
                              {i.name}
                              {isDrafted && <span className="badge" style={{ background: 'rgba(34,197,94,0.15)', color: '#22c55e', fontSize: '0.65rem' }}>Drafted</span>}
                            </div>
                            <div className="text-xs text-muted">
                              {i.email ? <span className="font-mono text-muted">{i.email}</span> : <span style={{ color: '#ef4444' }}>Email not found</span>} · {companies?.find(c => c.id === i.company_id)?.name || 'Unknown Company'}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                    {!individuals?.length && <div style={{ padding: '20px 16px', color: 'var(--text-muted)', fontSize: '0.875rem', textAlign: 'center' }}>No individuals found.</div>}
                  </div>
                </ScrollArea>
              )}
            </div>
          </div>
        </div>
      )}

      {tab === 'emails' && (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex gap-2 mb-4 shrink-0">
            <select className="form-select" style={{ width: 'auto' }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              <option value="DRAFTED">Drafted</option>
              <option value="SENT">Sent</option>
              <option value="REPLIED">Replied</option>
              <option value="IGNORED">Ignored</option>
              <option value="FOLLOW_UP_SENT">Follow-up Sent</option>
            </select>
            <button className="btn btn-secondary btn-sm" disabled={polling} onClick={handleRefresh}>
              {polling ? <Spinner /> : '🔄'}
            </button>
          </div>
          
          {emailsLoading ? <Spinner /> : !emails?.length ? (
            <EmptyState icon="📬" title="No emails yet" text="No emails drafted for this campaign." />
          ) : (
            <div className="flex-1 w-full rounded-md border border-white/10 bg-black/20 overflow-y-auto relative">
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Recipient</th>
                      <th>Company</th>
                      <th>Subject</th>
                      <th>Status</th>
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
                        <td onClick={ev => ev.stopPropagation()}>
                          <div className="flex gap-1">
                            {e.status === 'drafted' && (
                              <>
                                <button className="btn btn-primary btn-sm" onClick={() => approve(e.id)}>✅ Approve</button>
                                <button className="btn btn-sm" style={{ background: 'linear-gradient(135deg, #3b82f6, #2563eb)', color: 'white', border: 'none' }} onClick={(ev) => { ev.stopPropagation(); sendDirectly(e.id); }}>🚀 Send Directly</button>
                              </>
                            )}
                            <button className="btn btn-secondary btn-sm" onClick={() => openDetail(e)}>View</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Email Detail Modal */}
      <Modal open={!!selectedEmail} onClose={() => { setSelectedEmail(null); setShowRegeneratePrompt(false); setRegenerateFeedback(''); setRegeneratingTargetId(null); }} title="Email Draft" size="xl">
        {selectedEmail && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {regeneratingTargetId === selectedEmail.target_id ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
                 <Spinner size="lg" />
                 <div className="mt-4 text-muted">Regenerating email... This may take up to a minute.</div>
              </div>
            ) : (
              <>
                <div className="flex justify-between items-center">
              <div className="flex gap-2 items-center">
                <StatusBadge status={selectedEmail.status} />
                <span className="text-xs text-muted">{fmtDate(selectedEmail.drafted_at)}</span>
              </div>
              <div className="flex gap-2">
                {editMode ? (
                  <>
                    <button className="btn btn-primary btn-sm" disabled={saving} onClick={save}>{saving ? <Spinner /> : '💾 Save'}</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => setEditMode(false)}>Cancel</button>
                  </>
                ) : (
                  <>
                    {selectedEmail.status === 'drafted' && <button className="btn btn-secondary btn-sm" onClick={() => setEditMode(true)}>✏️ Edit</button>}
                    {selectedEmail.status === 'drafted' && <button className="btn btn-primary btn-sm" onClick={() => approve(selectedEmail.id)}>✅ Approve</button>}
                    {selectedEmail.status === 'drafted' && <button className="btn btn-sm" style={{ background: 'linear-gradient(135deg, #3b82f6, #2563eb)', color: 'white', border: 'none' }} onClick={() => sendDirectly(selectedEmail.id)}>🚀 Send Directly</button>}
                    <button className="btn btn-secondary btn-sm" onClick={() => setShowRegeneratePrompt(true)}>🔄 Regenerate</button>
                    <PushToGmailButton emailId={selectedEmail.id} />
                  </>
                )}
              </div>
            </div>

            <div style={{ padding: '10px 14px', background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)', fontSize: '0.875rem' }}>
              <div className="text-sm font-mono text-muted mb-1">Fetched Email ID: {selectedEmail.recipient_email || 'unknown'}</div>
              <strong>To:</strong> {selectedEmail.recipient_name}
              {selectedEmail.company_name && <> · <strong>Re:</strong> {selectedEmail.company_name}</>}
            </div>

            {editMode ? (
              <>
                <div className="form-group">
                  <label className="form-label">Recipient Email</label>
                  <input className="form-input" value={editRecipientEmail} onChange={e => setEditRecipientEmail(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Subject</label>
                  <input className="form-input" value={editSubject} onChange={e => setEditSubject(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Body</label>
                  <textarea className="form-textarea" style={{ minHeight: 240 }} value={editBody} onChange={e => setEditBody(e.target.value)} />
                </div>
              </>
            ) : showRegeneratePrompt ? (
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Regeneration Instructions (Optional)</label>
                <textarea 
                  className="form-textarea" 
                  style={{ minHeight: 100 }} 
                  placeholder="e.g. Make it shorter, focus more on our partnership..."
                  value={regenerateFeedback}
                  onChange={e => setRegenerateFeedback(e.target.value)}
                />
                <div className="flex gap-2 mt-2">
                  <button className="btn btn-primary btn-sm" onClick={() => regenerate(selectedEmail.id)}>Confirm Regenerate</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => { setShowRegeneratePrompt(false); setRegenerateFeedback(''); }}>Cancel</button>
                </div>
              </div>
            ) : (
              <>
                <div className="email-subject">{selectedEmail.subject || 'No subject'}</div>
                <div className="email-preview">{selectedEmail.body || 'No body'}</div>
                <CopyButton text={`Subject: ${selectedEmail.subject}\n\n${selectedEmail.body}`} label="Copy Full Email" />
              </>
            )}
            </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
