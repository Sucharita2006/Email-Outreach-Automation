// API client — communicates with the FastAPI backend
const BASE_URL = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const body = await res.json(); detail = body.detail || JSON.stringify(body); } catch {}
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('text/plain')) return res.text();
  if (ct.includes('text/event-stream')) return res;
  return res.json();
}

const get  = (path, params) => request(path + (params ? '?' + new URLSearchParams(params).toString() : ''));
const post = (path, body)   => request(path, { method: 'POST', body: body != null ? JSON.stringify(body) : undefined });
const patch = (path, body)  => request(path, { method: 'PATCH', body: JSON.stringify(body) });

// ── Targets ───────────────────────────────────────────────
export const api = {
  // Companies
  getCompanies: (params) => get('/targets/companies', params),
  getCompany:   (id)     => get(`/targets/companies/${id}`),
  createCompany:(data)   => post('/targets/companies', data),
  updateCompany:(id, d)  => patch(`/targets/companies/${id}`, d),
  searchCompanies:(q)    => get('/targets/companies/search', { q, limit: 20 }),
  getStats:     ()       => get('/targets/stats'),

  // Individuals
  getIndividuals: (params) => get('/targets/individuals', params),
  getIndividual:  (id)     => get(`/targets/individuals/${id}`),
  createIndividual:(data)  => post('/targets/individuals', data),

  // Research / Enrichment
  getCompanyStatus:    (id)      => get(`/research/company/${id}/status`),
  getIndividualStatus: (id)      => get(`/research/individual/${id}/status`),
  enrichCompanyAll:    (id, fr)  => post(`/research/company/${id}/enrich-all${fr ? '?force_refresh=true' : ''}`),
  enrichCompanySerper: (id)      => post(`/research/company/${id}/serper`),
  enrichCompanyOC:     (id)      => post(`/research/company/${id}/opencorporates`),
  enrichCompanyHunter: (id)      => post(`/research/company/${id}/hunter`),
  enrichIndividualAll: (id, fr)  => post(`/research/individual/${id}/enrich-all${fr ? '?force_refresh=true' : ''}`),
  enrichIndividualHumantic:(id)  => post(`/research/individual/${id}/humantic`),
  enrichIndividualSerper:(id)    => post(`/research/individual/${id}/serper`),
  enrichIndividualHunter:(id)    => post(`/research/individual/${id}/hunter`),
  getDiscInstructions: (type)    => get(`/research/disc/${type}`),
  batchEnrichOC:       (ids)     => post('/research/batch/opencorporates', ids),
  batchSerperCompanies:(ids)     => post('/research/batch/serper/companies', ids),
  batchHumantic:       (ids)     => post('/research/batch/humantic', ids),

  // Campaigns
  getCampaigns:    ()     => get('/emails/campaigns'),
  createCampaign:  (data) => post('/emails/campaigns', data),

  // Emails
  getEmails:   (params)  => get('/emails/', params),
  getEmail:    (id)      => get(`/emails/${id}`),
  generateSingle:(data)  => post('/emails/generate/single', data),
  generateBatch: (data)  => post('/emails/generate', data),
  updateEmail:   (id, d) => patch(`/emails/${id}`, d),
  approveEmail:  (id)    => post(`/emails/${id}/approve`),
  regenerateEmail:(id, fr)=> post(`/emails/${id}/regenerate${fr ? '?force_refresh_analysis=true' : ''}`),
  exportEmail:   (id)    => get(`/emails/${id}/export`, { format: 'text' }),

  // Tracking
  markReplied:     (id, d) => post(`/tracking/${id}/mark-replied`, d),
  markIgnored:     (id, sfu)=> post(`/tracking/${id}/mark-ignored?schedule_follow_up=${sfu !== false}`),
  scheduleFollowUp:(id, d)  => post(`/tracking/${id}/schedule-followup`, d),
  processFollowUps:(cid, gmail) => post(`/tracking/process-follow-ups?${new URLSearchParams({...(cid ? {campaign_id:cid}:{}), push_to_gmail: gmail||false})}`),
  getDueFollowUps: (cid)   => get('/tracking/follow-ups/due', cid ? { campaign_id: cid } : {}),
  getReplyHistory: (tid)   => get(`/tracking/reply-history/${tid}`),
  getDashboard:    (cid)   => get('/tracking/dashboard', cid ? { campaign_id: cid } : {}),
  pushToGmail:     (id)    => post(`/tracking/${id}/push-to-gmail`),
  gmailStatus:     ()      => get('/tracking/auth/gmail/status'),
  gmailAuthorize:  ()      => get('/tracking/auth/gmail/authorize'),
  pollGmail:       (cid)   => post(`/tracking/poll-gmail${cid ? '?campaign_id='+cid : ''}`),
};

export default api;
