const API_BASE = import.meta.env.VITE_API_URL || "";

export class ApiError extends Error {
  code: string;
  existingRunId?: string;
  runCreated: boolean;

  constructor(
    message: string,
    opts: { code?: string; existingRunId?: string; runCreated?: boolean } = {}
  ) {
    super(message);
    this.name = "ApiError";
    this.code = opts.code || "UNKNOWN";
    this.existingRunId = opts.existingRunId;
    this.runCreated = opts.runCreated ?? false;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
    const detail = err.detail || err.error;
    let message = res.statusText;
    let code = "UNKNOWN";
    let existingRunId: string | undefined;
    let runCreated = false;

    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      message = detail.message || detail.msg || JSON.stringify(detail);
      code = detail.code || code;
      existingRunId = detail.existing_run_id;
      runCreated = detail.run_created ?? false;
    }

    throw new ApiError(message, { code, existingRunId, runCreated });
  }
  return res.json();
}

export async function getToken(sub: string, tenantId: string, role: string) {
  const data = await request<{ access_token: string }>("/api/v1/dev/token", {
    method: "POST",
    body: JSON.stringify({ sub, tenant_id: tenantId, role, aud: "band-a-local" }),
  });
  return data.access_token;
}

export async function fetchMetrics(sourceFilter: "all" | "zoho_mail" | "teams" = "all") {
  const q = sourceFilter !== "all" ? `?source_filter=${sourceFilter}` : "?source_filter=all";
  return request<MetricsSummary>(`/api/v1/metrics/summary${q}`);
}

export async function fetchLeads(tenantId?: string) {
  const q = tenantId ? `?tenant_id=${tenantId}` : "";
  return request<Lead[]>(`/api/v1/leads${q}`);
}

export async function fetchRuns(tenantId?: string) {
  const q = tenantId ? `?tenant_id=${tenantId}` : "";
  return request<Run[]>(`/api/v1/runs${q}`);
}

export async function fetchRun(runId: string) {
  return request<Run>(`/api/v1/runs/${runId}`);
}

export async function deleteRun(runId: string) {
  return request<{
    status: string;
    run_id: string;
    lead_id: string;
    lead_deleted: boolean;
  }>(`/api/v1/runs/${runId}`, {
    method: "DELETE",
  });
}

export async function fetchRunEvents(runId: string) {
  return request<RuntimeEvent[]>(`/api/v1/runs/${runId}/events`);
}

export async function fetchRunInboundMail(runId: string): Promise<InboundMail | null> {
  const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/inbound-mail`, {
    headers: { "Content-Type": "application/json" },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new Error(err.detail || err.error?.message || res.statusText);
  }
  return res.json();
}

export async function fetchRunInboundTeams(runId: string): Promise<InboundTeams | null> {
  const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/inbound-teams`, {
    headers: { "Content-Type": "application/json" },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new Error(err.detail || err.error?.message || res.statusText);
  }
  return res.json();
}

export async function fetchQueueStatus() {
  return request<QueueStatus>("/api/v1/queue/status");
}

export async function fetchQueueMessages() {
  return request<QueueMessage[]>("/api/v1/queue/messages");
}

export async function startWorker() {
  return request("/api/v1/queue/worker/start", { method: "POST" });
}

export async function stopWorker() {
  return request("/api/v1/queue/worker/stop", { method: "POST" });
}

export async function zohoCreateLead(data: object, token: string) {
  return request("/api/v1/simulators/zoho/leads", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(data),
  });
}

export async function zohoWebhook(leadId: string, token: string) {
  return request(`/api/v1/simulators/zoho/webhook?lead_id=${leadId}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function teamsRequest(data: object, token: string, forceSync = false) {
  const q = forceSync ? "?force_sync=true" : "";
  return request(`/api/v1/simulators/teams/request${q}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(data),
  });
}

export async function fetchSchedulerSamples() {
  return request<SchedulerSamples>("/api/v1/scheduler/samples");
}

export async function schedulerIngest(teamsIds: string[], zohoIds: string[]) {
  return request<{ ingested: number; results: unknown[]; status: SchedulerStatus }>(
    "/api/v1/scheduler/ingest",
    {
      method: "POST",
      body: JSON.stringify({ teams_ids: teamsIds, zoho_ids: zohoIds }),
    }
  );
}

export async function schedulerStatus() {
  return request<SchedulerStatus>("/api/v1/scheduler/status");
}

export async function schedulerTimerStart(
  intervalSeconds: number,
  batchTeams: number,
  batchZoho: number
) {
  return request<SchedulerStatus>("/api/v1/scheduler/timer/start", {
    method: "POST",
    body: JSON.stringify({
      interval_seconds: intervalSeconds,
      batch_teams: batchTeams,
      batch_zoho: batchZoho,
    }),
  });
}

export async function schedulerTimerPause() {
  return request<SchedulerStatus>("/api/v1/scheduler/timer/pause", { method: "POST" });
}

export async function schedulerReset() {
  return request<{ status: string; message: string; player: SchedulerStatus }>(
    "/api/v1/scheduler/reset",
    { method: "POST" }
  );
}

export interface AdmissionDemoResult {
  scenario: string;
  outcome: string;
  message: string;
  run_id?: string | null;
  rejected?: boolean;
  duplicate?: boolean;
  run_created?: boolean;
  reason?: string;
  code?: string;
  existing_run_id?: string;
  worker_stopped?: boolean;
  [key: string]: unknown;
}

export async function schedulerRunAdmissionDemo(scenario: string) {
  return request<AdmissionDemoResult>(`/api/v1/scheduler/demos/${scenario}`, {
    method: "POST",
  });
}

export async function demoReset() {
  return request("/api/v1/demo/reset", { method: "POST" });
}

export async function demoAdmission(path: string) {
  return request(`/api/v1/demo/admission/${path}`, { method: "POST" });
}

export async function demoSyncDispatch(data: object, token: string) {
  return request("/api/v1/dispatch/demo-sync", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(data),
  });
}

export interface Lead {
  lead_id: string;
  tenant_id: string;
  company_name: string;
  industry: string;
  budget: number;
  contact_name: string;
  source: string;
  status: string;
  active_run_id: string | null;
  latest_run_id?: string | null;
}

export interface Run {
  run_id: string;
  tenant_id: string;
  source: string;
  trigger_type: string;
  lead_id: string;
  owner: string;
  state: string;
  correlation_id: string;
  created_at: string;
  use_case?: string;
  document_ref?: string | null;
  supplier_id?: string | null;
  dispatch_route?: string | null;
  arrival_source?: string | null;
  budget_turns?: number;
  budget_turns_used?: number;
  budget_usd_cents?: number;
  budget_usd_spent_cents?: number;
}

export interface InvoiceCase {
  case_id: string;
  message_id?: string;
  from?: string;
  subject?: string;
  document_ref?: string;
  auth_results?: Record<string, string>;
}

export interface InvoiceFinding {
  run_id: string;
  use_case?: string;
  document_ref?: string | null;
  supplier_id?: string | null;
  arrival_source?: string | null;
  dispatch_route?: string | null;
  verdict: string;
  checks: Array<{ what?: string; result?: string } | Record<string, unknown>>;
  policy_ids: string[];
  policy_choice_reason?: string;
  reasoning: string;
  uncertainties: string[];
  raw_text: string;
  budget?: {
    turns?: number;
    turns_used?: number;
    usd_cents?: number;
    usd_spent_cents?: number;
    seconds?: number;
  };
}

export interface JournalTurn {
  turn_no: number;
  saw: Record<string, unknown>;
  decided: string;
  tool_name: string | null;
  tool_args: Record<string, unknown>;
  tool_result: Record<string, unknown>;
  blocked_by_policy: boolean;
  token_cost_cents: number;
}

export interface InvoiceHealth {
  api: { ok: boolean; detail?: string };
  mocks: { ok: boolean; url?: string; detail?: string };
  model: { ok: boolean; name?: string; endpoint_host?: string; detail?: string };
}

export interface InvoiceRunSummary {
  run_id: string;
  state: string;
  document_ref?: string;
  supplier_id?: string;
  arrival_source?: string;
  dispatch_route?: string;
  created_at?: string;
}

export async function fetchInvoiceHealth() {
  return request<InvoiceHealth>("/api/v1/invoice/health");
}

export async function fetchInvoiceCases() {
  return request<{ cases: InvoiceCase[] }>("/api/v1/invoice/cases");
}

export async function fetchInvoiceChatQueries() {
  return request<{ queries: Array<Record<string, unknown>> }>("/api/v1/invoice/chat-queries");
}

export async function ingestInvoiceCase(caseId: string, forceSync = false) {
  const q = forceSync ? "?force_sync=true" : "";
  return request<Record<string, unknown>>(`/api/v1/invoice/cases/${caseId}/ingest${q}`, {
    method: "POST",
  });
}

export async function chatInvoiceCase(caseId: string) {
  return request<Record<string, unknown>>(`/api/v1/invoice/chat/${caseId}`, {
    method: "POST",
  });
}

export async function fetchInvoiceFinding(runId: string) {
  return request<InvoiceFinding>(`/api/v1/invoice/runs/${runId}/finding`);
}

export async function fetchInvoiceJournal(runId: string) {
  return request<{ run_id: string; turns: JournalTurn[] }>(`/api/v1/invoice/runs/${runId}/journal`);
}

export async function fetchInvoiceReplay(runId: string) {
  return request<{
    run_id: string;
    turns: JournalTurn[];
    finding: InvoiceFinding | null;
    model_calls: number;
    cost_cents: number;
  }>(`/api/v1/invoice/runs/${runId}/replay`);
}

export async function fetchInvoiceRuns(tenantId?: string) {
  const q = tenantId ? `?tenant_id=${tenantId}` : "";
  return request<InvoiceRunSummary[]>(`/api/v1/invoice/runs${q}`);
}

export async function demoInvoicePolicyBlock(runId: string) {
  return request<{
    run_id: string;
    blocked: boolean;
    reason: string;
    turn: JournalTurn;
  }>(`/api/v1/invoice/runs/${runId}/demo/policy-block`, { method: "POST" });
}

export interface RuntimeEvent {
  event_id: string;
  run_id: string | null;
  timestamp: string;
  stage: string;
  component: string;
  action: string;
  status: string;
  message: string;
}

export interface InboundMail {
  run_id: string;
  lead_id: string;
  source: string;
  event_id: string;
  mail_from: string;
  mail_to: string;
  mail_subject: string;
  mail_body: string;
  mail_message_id: string;
  received_at: string | null;
  attachment_filename?: string;
  invoice_content?: string;
  invoice_source?: string;
}

export interface InboundTeams {
  run_id: string;
  lead_id: string;
  source: string;
  event_id: string;
  teams_from: string;
  teams_text: string;
  teams_channel: string;
  conversation_id: string;
  activity_id: string;
  received_at: string | null;
}

export interface QueueStatus {
  pending: number;
  processing: number;
  completed: number;
  worker_running: boolean;
}

export interface QueueMessage {
  message_id: string;
  run_id: string;
  lead_id: string;
  source?: string;
  status: string;
  enqueued_at: string;
}

export interface MetricsSummary {
  total_leads: number;
  active_runs: number;
  queued_messages: number;
  completed_handoffs: number;
  rejected_requests: number;
  failed_runs: number;
  source_filter?: string;
}

export interface SchedulerStatus {
  enabled: boolean;
  interval_seconds: number;
  batch_teams: number;
  batch_zoho: number;
  batch_size: number;
  next_run_at: string | null;
  seconds_remaining: number | null;
  remaining_teams: number;
  remaining_zoho: number;
  used_teams: number;
  used_zoho: number;
  last_tick_at: string | null;
  last_tick: {
    status?: string;
    reason?: string | null;
    ingested_teams?: number;
    ingested_zoho?: number;
    remaining_teams?: number;
    remaining_zoho?: number;
  } | null;
  pause_reason: string | null;
  last_run_at: string | null;
  last_run_count: number;
}

export interface SchedulerSample {
  id: string;
  channel: string;
  title: string;
  preview: string;
  used: boolean;
}

export interface SchedulerSamples {
  teams: SchedulerSample[];
  zoho: SchedulerSample[];
}
