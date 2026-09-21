import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ActionButton } from "../components/ActionButton";
import { InvoiceReviewPanel } from "../components/InvoiceReviewPanel";
import { InboundMailPanel } from "../components/InboundMailPanel";
import { InboundTeamsPanel } from "../components/InboundTeamsPanel";
import { DemoGuidePanel } from "../components/DemoGuidePanel";
import { EventTimeline } from "../components/EventTimeline";
import { PipelineAnimation } from "../components/PipelineAnimation";
import { StatusBadge } from "../components/StatusBadge";
import { StatusBanner, type BannerType } from "../components/StatusBanner";
import { getPollingInterval, isRunInProgress, usePolling } from "../hooks/usePolling";
import {
  demoAdmission,
  demoReset,
  deleteRun,
  fetchLeads,
  fetchMetrics,
  fetchQueueMessages,
  fetchQueueStatus,
  fetchRun,
  fetchRunEvents,
  fetchRunInboundMail,
  fetchRunInboundTeams,
  fetchRuns,
  fetchSchedulerSamples,
  getToken,
  schedulerIngest,
  schedulerReset,
  schedulerRunAdmissionDemo,
  schedulerStatus,
  schedulerTimerPause,
  schedulerTimerStart,
  startWorker,
  stopWorker,
  teamsRequest,
  zohoCreateLead,
  zohoWebhook,
  ApiError,
  type Lead,
  type QueueMessage,
  type Run,
  type SchedulerSample,
  type SchedulerStatus,
} from "../services/api";
import { formatIst } from "../utils/datetime";

const SAMPLE_LEAD_BASE = {
  industry: "Banking",
  employee_count: 500,
  requirement: "AI fraud detection platform",
  budget: 5000000,
  contact_name: "Anita Sharma",
  contact_role: "CTO",
  source: "Website",
};

function buildSampleLead() {
  const suffix = Date.now().toString(36).slice(-4).toUpperCase();
  return {
    ...SAMPLE_LEAD_BASE,
    company_name: `Demo Corp ${suffix}`,
    email: `demo-${suffix.toLowerCase()}@example.com`,
  };
}

const ADMISSION_DEMOS: { id: string; title: string; say: string }[] = [
  { id: "invalid-auth", title: "Invalid auth", say: "Bad identity is rejected before a run exists." },
  { id: "tenant-mismatch", title: "Tenant mismatch", say: "Token tenant must match the request tenant." },
  { id: "duplicate", title: "Duplicate event_id", say: "Same event_id twice is idempotent — same run_id." },
  { id: "active-run", title: "Active run blocked", say: "Second request while lead still has a QUEUED run is rejected." },
  { id: "quota-exceeded", title: "Quota exceeded", say: "Tenant active-run budget is full — admission refuses." },
];

type LoadingKey =
  | "zohoCreate"
  | "zohoWebhook"
  | "teams"
  | "schedulerIngest"
  | "schedulerStart"
  | "schedulerPause"
  | "schedulerReset"
  | "workerOn"
  | "workerOff"
  | "reset"
  | "admission";

export default function Dashboard() {
  const [mode, setMode] = useState<"sales_lead" | "invoice_review">("invoice_review");
  const [invoiceResetNonce, setInvoiceResetNonce] = useState(0);
  const [tenant, setTenant] = useState("company-a");
  const [tab, setTab] = useState<"zoho" | "teams" | "scheduler">("zoho");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [teamsMsg, setTeamsMsg] = useState("Qualify lead LEAD-10001");
  const [selectedLead, setSelectedLead] = useState("");
  const [admissionResult, setAdmissionResult] = useState<string>("");
  const [forceSync, setForceSync] = useState(false);
  const [metricsSourceFilter, setMetricsSourceFilter] = useState<"all" | "zoho_mail" | "teams">("all");
  const [loading, setLoading] = useState<Partial<Record<LoadingKey | string, boolean>>>({});
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [admissionDemosOpen, setAdmissionDemosOpen] = useState(true);
  const [sampleTeams, setSampleTeams] = useState<SchedulerSample[]>([]);
  const [sampleZoho, setSampleZoho] = useState<SchedulerSample[]>([]);
  const [selectedTeamsIds, setSelectedTeamsIds] = useState<string[]>([]);
  const [selectedZohoIds, setSelectedZohoIds] = useState<string[]>([]);
  const [timerInterval, setTimerInterval] = useState(15);
  const [timerBatchTeams, setTimerBatchTeams] = useState(1);
  const [timerBatchZoho, setTimerBatchZoho] = useState(1);
  const [playerStatus, setPlayerStatus] = useState<SchedulerStatus | null>(null);
  const [banner, setBanner] = useState<{ message: string; type: BannerType } | null>(null);
  const [lastActiveRunDemo, setLastActiveRunDemo] = useState(false);

  const tokensRef = useRef<Record<string, string>>({});
  const knownRunIdsRef = useRef<Set<string>>(new Set());
  const watchRunOverrideRef = useRef<string | null | undefined>(undefined);

  const showBanner = (message: string, type: BannerType, autoDismiss = type !== "error") => {
    setBanner({ message, type });
    if (autoDismiss && type !== "error") {
      setTimeout(() => setBanner(null), 5000);
    }
  };

  const setActionLoading = (key: string, value: boolean) => {
    setLoading((prev) => ({ ...prev, [key]: value }));
  };

  const getRoleToken = useCallback(async (role: string, sub: string) => {
    const key = `${tenant}-${role}-${sub}`;
    if (tokensRef.current[key]) return tokensRef.current[key];
    const t = await getToken(sub, tenant, role);
    tokensRef.current[key] = t;
    return t;
  }, [tenant]);

  const fetchDashboardData = useCallback(async () => {
    const [l, r] = await Promise.all([fetchLeads(tenant), fetchRuns(tenant)]);
    return { leads: l, runs: r };
  }, [tenant]);

  const { data: dashboardData, refresh: refreshDashboardData } = usePolling(
    fetchDashboardData,
    [tenant],
    2000
  );

  useEffect(() => {
    tokensRef.current = {};
    knownRunIdsRef.current = new Set();
    watchRunOverrideRef.current = undefined;
    setActiveRunId(null);
  }, [tenant]);

  const refreshSamples = useCallback(async () => {
    try {
      const samples = await fetchSchedulerSamples();
      setSampleTeams(samples.teams);
      setSampleZoho(samples.zoho);
    } catch {
      /* ignore while backend warm */
    }
  }, []);

  const refreshPlayerStatus = useCallback(async () => {
    try {
      setPlayerStatus(await schedulerStatus());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refreshSamples();
    void refreshPlayerStatus();
  }, [refreshSamples, refreshPlayerStatus]);

  useEffect(() => {
    if (tab !== "scheduler" && !playerStatus?.enabled) return;
    const id = window.setInterval(() => {
      void refreshPlayerStatus();
      void refreshSamples();
    }, 2000);
    return () => window.clearInterval(id);
  }, [tab, playerStatus?.enabled, refreshPlayerStatus, refreshSamples]);

  useEffect(() => {
    if (!dashboardData) return;
    const { leads: l, runs: r } = dashboardData;
    const prevKnown = knownRunIdsRef.current;
    const newRuns = r.filter((x) => !prevKnown.has(x.run_id));
    knownRunIdsRef.current = new Set(r.map((x) => x.run_id));

    setLeads(l);
    setRuns(r);
    setSelectedLead((prev) => (l.some((x) => x.lead_id === prev) ? prev : l[0]?.lead_id ?? prev));

    const override = watchRunOverrideRef.current;
    if (override === null) {
      setActiveRunId(null);
      watchRunOverrideRef.current = undefined;
    } else if (typeof override === "string") {
      setActiveRunId(override);
      watchRunOverrideRef.current = undefined;
    } else if (newRuns.length > 0 && prevKnown.size > 0) {
      const newest = [...newRuns].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
      setActiveRunId(newest.run_id);
      const newestLead = l.find((x) => x.lead_id === newest.lead_id);
      const banner =
        newestLead?.source === "Zoho Mail"
          ? `New email received → ${newest.run_id}`
          : newestLead?.source === "Teams"
            ? `New Teams message → ${newest.run_id}`
            : `New run detected → ${newest.run_id}`;
      showBanner(banner, "info");
    } else {
      setActiveRunId((prev) => {
        if (prev && r.some((x) => x.run_id === prev)) return prev;
        const inProgress = r.find((x) => isRunInProgress(x.state));
        return inProgress?.run_id ?? null;
      });
    }
  }, [dashboardData]);

  const loadData = useCallback(
    async (watchRunId?: string | null) => {
      watchRunOverrideRef.current = watchRunId;
      await refreshDashboardData();
    },
    [refreshDashboardData]
  );

  const { data: metrics, refresh: refreshMetrics } = usePolling(
    () => fetchMetrics(metricsSourceFilter),
    [metricsSourceFilter],
    3000
  );

  const { data: queueStatus, refresh: refreshQueue } = usePolling(
    fetchQueueStatus,
    [],
    3000
  );

  const { data: queueMessages } = usePolling(fetchQueueMessages, [], 3000);
  const pendingQueueMessages = (queueMessages || []).filter(
    (m) => m.status === "PENDING" || m.status.toLowerCase() === "pending"
  );

  const { data: activeRun, refresh: refreshRun } = usePolling(
    () => (activeRunId ? fetchRun(activeRunId) : Promise.resolve(null as unknown as Run)),
    [activeRunId],
    500,
    !!activeRunId
  );

  const watchedRunState = activeRun?.state ?? runs.find((r) => r.run_id === activeRunId)?.state;
  const pollInterval = getPollingInterval(watchedRunState);

  const { data: runEvents, refresh: refreshEvents } = usePolling(
    () => (activeRunId ? fetchRunEvents(activeRunId) : Promise.resolve([])),
    [activeRunId],
    pollInterval,
    !!activeRunId
  );

  const { data: inboundMail, refresh: refreshInboundMail } = usePolling(
    () => (activeRunId ? fetchRunInboundMail(activeRunId) : Promise.resolve(null)),
    [activeRunId],
    pollInterval,
    !!activeRunId
  );

  const { data: inboundTeams, refresh: refreshInboundTeams } = usePolling(
    () => (activeRunId ? fetchRunInboundTeams(activeRunId) : Promise.resolve(null)),
    [activeRunId],
    pollInterval,
    !!activeRunId
  );

  const refreshAll = useCallback(async (watchRunId?: string | null) => {
    await Promise.all([
      loadData(watchRunId),
      refreshMetrics(),
      refreshQueue(),
      refreshRun(),
      refreshEvents(),
      refreshInboundMail(),
      refreshInboundTeams(),
    ]);
  }, [loadData, refreshMetrics, refreshQueue, refreshRun, refreshEvents, refreshInboundMail, refreshInboundTeams]);

  const watchedEvents = activeRunId ? runEvents || [] : [];

  const selectedLeadMeta = leads.find((l) => l.lead_id === selectedLead);

  const runAction = async (key: string, fn: () => Promise<void>) => {
    if (loading[key]) return;
    setActionLoading(key, true);
    try {
      await fn();
    } catch (e) {
      if (e instanceof ApiError && e.code === "ACTIVE_RUN_EXISTS" && e.existingRunId) {
        showBanner(`Rejected — lead already has active run ${e.existingRunId}`, "error", false);
        setActiveRunId(e.existingRunId);
        await refreshAll(e.existingRunId);
      } else {
        showBanner(e instanceof Error ? e.message : "Something went wrong", "error", false);
      }
    } finally {
      setActionLoading(key, false);
    }
  };

  const handleZohoCreate = () =>
    runAction("zohoCreate", async () => {
      const token = await getRoleToken("zoho-simulator", "zoho-simulator");
      const result = await zohoCreateLead({ ...buildSampleLead(), tenant_id: tenant }, token);
      setSelectedLead(result.lead_id);
      showBanner(`New lead ${result.lead_id} → Run ${result.run_id}`, "success");
      await refreshAll(result.run_id);
    });

  const handleZohoWebhook = () =>
    runAction("zohoWebhook", async () => {
      const token = await getRoleToken("zoho-simulator", "zoho-simulator");
      const r = await zohoWebhook(selectedLead, token);
      showBanner(`Webhook sent → ${r.run_id}`, "success");
      await refreshAll(r.run_id);
    });

  const handleTeams = () =>
    runAction("teams", async () => {
      const token = await getRoleToken("sales-user", "sales-user-01");
      const result = await teamsRequest(
        { tenant_id: tenant, requested_by: "sales-user-01", message: teamsMsg, lead_id: selectedLead },
        token,
        forceSync
      );
      showBanner(`Teams → Run ${result.run_id} (${result.state})`, "success");
      await refreshAll(result.run_id);
    });

  const toggleSample = (channel: "teams" | "zoho", id: string) => {
    if (channel === "teams") {
      setSelectedTeamsIds((prev) =>
        prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      );
    } else {
      setSelectedZohoIds((prev) =>
        prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      );
    }
  };

  const handleSchedulerIngest = () =>
    runAction("schedulerIngest", async () => {
      const result = await schedulerIngest(selectedTeamsIds, selectedZohoIds);
      setSelectedTeamsIds([]);
      setSelectedZohoIds([]);
      setPlayerStatus(result.status);
      await refreshSamples();
      const okResults = result.results.filter(
        (r): r is { run_id: string } =>
          typeof r === "object" &&
          r !== null &&
          "run_id" in r &&
          typeof (r as { run_id: unknown }).run_id === "string" &&
          !("error" in r)
      );
      const errors = result.results.filter(
        (r): r is { sample_id?: string; message?: string; error?: string } =>
          typeof r === "object" && r !== null && "error" in r
      );
      if (result.ingested === 0 && errors.length > 0) {
        const msg = errors
          .map((e) => e.message || e.error || "ingest failed")
          .slice(0, 2)
          .join("; ");
        showBanner(`Ingest failed: ${msg}`, "error");
        return;
      }
      if (errors.length > 0) {
        showBanner(
          `Ingested ${result.ingested}; ${errors.length} failed`,
          "info"
        );
      } else {
        showBanner(`Ingested ${result.ingested} sample(s)`, "success");
      }
      await refreshAll(okResults[0]?.run_id ?? null);
    });

  const handleSchedulerStart = () =>
    runAction("schedulerStart", async () => {
      const status = await schedulerTimerStart(
        timerInterval,
        timerBatchTeams,
        timerBatchZoho
      );
      setPlayerStatus(status);
      if (status.pause_reason === "samples_exhausted") {
        showBanner("Not enough unused samples for that batch — timer paused", "info");
      } else {
        showBanner(
          `Timer on: every ${status.interval_seconds}s ingest ${status.batch_teams} Teams + ${status.batch_zoho} Zoho`,
          "info"
        );
      }
    });

  const handleSchedulerPause = () =>
    runAction("schedulerPause", async () => {
      setPlayerStatus(await schedulerTimerPause());
      showBanner("Sample ingress timer paused", "info");
    });

  const handleSchedulerReset = () =>
    runAction("schedulerReset", async () => {
      if (
        !confirm(
          "Reset sample player and clear simulator/sample-player data? Real live Zoho Mail and Teams bot data will be kept. Summary and Leads will update to match."
        )
      ) {
        return;
      }
      const result = await schedulerReset();
      setPlayerStatus(result.player);
      setSelectedTeamsIds([]);
      setSelectedZohoIds([]);
      await refreshSamples();
      showBanner(result.message, "info");
      await refreshAll(null);
    });

  const handleWorkerOn = () =>
    runAction("workerOn", async () => {
      await startWorker();
      showBanner("Mock Band B worker started", "success");
      await refreshQueue();
    });

  const handleWorkerOff = () =>
    runAction("workerOff", async () => {
      await stopWorker();
      showBanner("Mock Band B worker stopped — queue will backlog", "info");
      await refreshQueue();
    });

  const handleReset = () =>
    runAction("reset", async () => {
      if (!confirm("Clear simulator/sample-player data? Real live Zoho Mail and Teams bot data will be kept.")) return;
      await demoReset();
      tokensRef.current = {};
      setActiveRunId(null);
      setAdmissionResult("");
      setInvoiceResetNonce((n) => n + 1);
      showBanner("Demo reset complete — Zoho Mail & Teams data preserved", "success");
      await refreshAll(null);
    });

  const handleAdmission = (path: string, label: string) =>
    runAction(`admission-${path}`, async () => {
      const r = await demoAdmission(path);
      setAdmissionResult(JSON.stringify(r, null, 2));
      if (path === "quota-exceeded") {
        showBanner(
          "Quota test may add extra runs — click Reset Demo to restore clean state",
          "info"
        );
      } else if (r.rejected || r.duplicate) {
        showBanner(`${label}: ${r.reason || (r.duplicate ? "Idempotent duplicate" : "Done")}`, "info");
      } else {
        showBanner(`${label} completed`, "success");
      }
      await refreshMetrics();
    });

  const handleSchedulerAdmissionDemo = (id: string, title: string) =>
    runAction(`sched-demo-${id}`, async () => {
      const r = await schedulerRunAdmissionDemo(id);
      setAdmissionResult(JSON.stringify(r, null, 2));
      setLastActiveRunDemo(id === "active-run");
      const watchId = r.run_id || r.existing_run_id || null;
      let bannerType: BannerType = "success";
      const baseMsg = r.message || `${title} completed`;
      let bannerMsg = baseMsg;
      if (r.outcome === "unexpected_success") {
        bannerType = "error";
        bannerMsg = `${title}: ${baseMsg}`;
      } else if (r.rejected) {
        bannerType = "error";
        bannerMsg = baseMsg.startsWith("Rejected") ? baseMsg : `Rejected — ${baseMsg}`;
      } else if (r.duplicate || r.outcome === "duplicate") {
        bannerType = "info";
        bannerMsg = baseMsg.startsWith("Duplicate") || baseMsg.includes("idempotent")
          ? baseMsg
          : `Duplicate — ${baseMsg}`;
      } else {
        bannerMsg = `${title}: ${baseMsg}`;
      }
      if (id === "quota-exceeded") {
        bannerMsg += " · Reset when finished to clear fill runs.";
      }
      showBanner(bannerMsg, bannerType, bannerType !== "error");
      await refreshAll(watchId);
      await refreshQueue();
    });

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <header className="border-b-2 border-ink pb-6 mb-6">
        <div className="font-mono text-xs uppercase tracking-widest text-ink-soft">Agentic Systems Lab · Local Emulator</div>
        <h1 className="font-display text-3xl font-bold mt-2">
          {mode === "invoice_review" ? (
            <>
              Invoice Review — <span className="text-own">Build 02</span>
            </>
          ) : (
            <>
              Sales Lead Qualification — <span className="text-own">Band A</span> Runtime
            </>
          )}
        </h1>
        <p className="text-ink-soft mt-2">
          {mode === "invoice_review"
            ? "Local invoice agent (Band A + Band B). Foundry model only cloud dependency. Mocks on :8090."
            : "Local emulator of Entry & Control. No Azure, no real Zoho/Teams."}
        </p>
        <div className="mt-4 flex flex-wrap gap-4 items-center">
          <div className="flex gap-1 border border-hairline rounded p-0.5">
            <button
              type="button"
              onClick={() => setMode("invoice_review")}
              className={`px-3 py-1 rounded text-sm font-mono ${
                mode === "invoice_review" ? "bg-own text-white" : "hover:bg-own-tint"
              }`}
            >
              Invoice Review
            </button>
            <button
              type="button"
              onClick={() => setMode("sales_lead")}
              className={`px-3 py-1 rounded text-sm font-mono ${
                mode === "sales_lead" ? "bg-own text-white" : "hover:bg-own-tint"
              }`}
            >
              Sales Lead
            </button>
          </div>
          <label className="font-mono text-sm">
            Tenant:{" "}
            <select
              value={tenant}
              onChange={(e) => setTenant(e.target.value)}
              className="border border-hairline rounded px-2 py-1 bg-white"
            >
              <option value="company-a">company-a</option>
              <option value="company-b">company-b</option>
            </select>
          </label>
          <ActionButton
            variant="danger"
            loading={!!loading.reset}
            onClick={handleReset}
            className="!w-auto px-4 py-1 text-sm"
          >
            Reset Demo
          </ActionButton>
        </div>
      </header>

      {banner && (
        <StatusBanner
          message={banner.message}
          type={banner.type}
          onDismiss={() => setBanner(null)}
          autoDismissMs={5000}
        />
      )}

      {mode === "invoice_review" ? (
        <InvoiceReviewPanel
          tenant={tenant}
          resetNonce={invoiceResetNonce}
          onBanner={showBanner}
          onWatchRun={(id) => setActiveRunId(id)}
        />
      ) : (
      <>
      <DemoGuidePanel onGoToTab={setTab} />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-ink-soft uppercase tracking-wide">Summary source</span>
        {(
          [
            ["all", "All"],
            ["zoho_mail", "Zoho Mail"],
            ["teams", "Teams"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setMetricsSourceFilter(value)}
            className={`px-3 py-1 rounded text-sm font-mono ${
              metricsSourceFilter === value ? "bg-own text-white" : "border border-hairline hover:bg-own-tint"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-8">
          {[
            ["Leads", metrics.total_leads],
            ["Active Runs", metrics.active_runs],
            ["Queued", metrics.queued_messages],
            ["Handoffs", metrics.completed_handoffs],
            ["Rejected", metrics.rejected_requests],
            ["Failed", metrics.failed_runs],
          ].map(([label, val]) => (
            <div key={label as string} className="bg-white border border-hairline rounded-md p-3 text-center">
              <div className="font-display text-2xl font-bold">{val}</div>
              <div className="font-mono text-xs text-ink-soft">{label}</div>
            </div>
          ))}
        </div>
      )}

      <section className="grid md:grid-cols-3 gap-4 mb-8">
        <div className="md:col-span-1 bg-white border border-hairline rounded-md p-4">
          <h2 className="font-display font-semibold mb-3">Entry Points</h2>
          <div className="flex gap-2 mb-4">
            {(["zoho", "teams", "scheduler"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={`px-3 py-1 rounded text-sm font-mono capitalize ${tab === t ? "bg-own text-white" : "border border-hairline hover:bg-own-tint"}`}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === "zoho" && (
            <div>
              <p className="text-xs text-ink-soft mb-2">Zoho Simulator — Local</p>
              <p className="text-xs text-ink-soft mb-3">
                <span className="font-mono text-own">New Lead → Band A</span> creates a{" "}
                <span className="font-semibold text-ink">new lead ID every click</span> (happy-path demo). It does not test resend rejection.
                <span className="italic block mt-1">
                  To test rejection: pick one lead below, click Send Webhook twice (Worker OFF). Same lead ID required.
                </span>
              </p>
              {queueStatus?.worker_running && (
                <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 mb-3">
                  Band B worker is ON — runs finish in seconds, so resend may succeed instead of rejecting. Turn Worker OFF in the Queue panel first.
                </p>
              )}
              <ActionButton loading={!!loading.zohoCreate} onClick={handleZohoCreate}>
                New Lead → Band A
              </ActionButton>
              <select
                value={selectedLead}
                onChange={(e) => setSelectedLead(e.target.value)}
                className="w-full border rounded px-2 py-1 mt-3 mb-1 text-sm"
                aria-label="Existing lead for webhook"
              >
                {leads.map((l) => (
                  <option key={l.lead_id} value={l.lead_id}>
                    {l.lead_id} — {l.company_name}
                    {l.active_run_id ? ` (active: ${l.active_run_id})` : ""}
                  </option>
                ))}
              </select>
              {selectedLeadMeta?.active_run_id ? (
                <p className="text-xs font-mono text-own mb-2">
                  Active run: {selectedLeadMeta.active_run_id} — resending should reject
                </p>
              ) : (
                <p className="text-xs text-ink-soft mb-2">No active run for this lead — webhook will create a new run</p>
              )}
              <ActionButton variant="secondary" loading={!!loading.zohoWebhook} onClick={handleZohoWebhook} className="mt-1">
                Send Webhook — {selectedLead}
              </ActionButton>
            </div>
          )}

          {tab === "teams" && (
            <div>
              <p className="text-xs text-ink-soft mb-2">Teams Simulator — Local</p>
              <p className="text-xs text-ink-soft mb-3 italic">Type: Qualify lead LEAD-10001 — same Band A pipeline as Zoho.</p>
              <select value={selectedLead} onChange={(e) => setSelectedLead(e.target.value)} className="w-full border rounded px-2 py-1 mb-2 text-sm">
                {leads.map((l) => (
                  <option key={l.lead_id} value={l.lead_id}>{l.lead_id} — {l.company_name}</option>
                ))}
              </select>
              <input
                value={teamsMsg}
                onChange={(e) => setTeamsMsg(e.target.value)}
                className="w-full border rounded px-2 py-1 mb-2 text-sm font-mono"
              />
              <label className="flex items-center gap-2 text-xs mb-2">
                <input type="checkbox" checked={forceSync} onChange={(e) => setForceSync(e.target.checked)} />
                Force sync dispatch (demo)
              </label>
              <ActionButton loading={!!loading.teams} onClick={handleTeams}>
                Ask Teams to Qualify Lead
              </ActionButton>
            </div>
          )}

          {tab === "scheduler" && (
            <div className="space-y-3">
              <p className="text-xs text-ink-soft">
                <span className="font-semibold text-ink">Happy path samples</span> — fictional Teams / Zoho
                payloads through the real webhook adapters.{" "}
                <span className="font-semibold text-ink">Admission failures</span> — one-click reject /
                duplicate demos below.
              </p>

              <button
                type="button"
                onClick={() => setCatalogOpen((o) => !o)}
                className="w-full text-left text-sm font-mono border border-hairline rounded px-2 py-1.5 hover:bg-own-tint flex justify-between"
              >
                <span>Happy path — sample catalog</span>
                <span className="text-ink-soft">{catalogOpen ? "▾" : "▸"}</span>
              </button>

              {catalogOpen && (
                <div className="border border-hairline rounded p-2 max-h-56 overflow-auto space-y-3 bg-paper/40">
                  <div>
                    <p className="font-mono text-xs text-ink-soft mb-1">Teams ({sampleTeams.length})</p>
                    {sampleTeams.map((s) => (
                      <label key={s.id} className="flex gap-2 items-start text-xs mb-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedTeamsIds.includes(s.id)}
                          onChange={() => toggleSample("teams", s.id)}
                          className="mt-0.5"
                        />
                        <span>
                          <span className="font-semibold">{s.title}</span>
                          {s.used ? <span className="text-ink-soft"> · used</span> : null}
                          <span className="block text-ink-soft truncate max-w-[220px]">{s.preview}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                  <div>
                    <p className="font-mono text-xs text-ink-soft mb-1">Zoho ({sampleZoho.length})</p>
                    {sampleZoho.map((s) => (
                      <label key={s.id} className="flex gap-2 items-start text-xs mb-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedZohoIds.includes(s.id)}
                          onChange={() => toggleSample("zoho", s.id)}
                          className="mt-0.5"
                        />
                        <span>
                          <span className="font-semibold">{s.title}</span>
                          {s.used ? <span className="text-ink-soft"> · used</span> : null}
                          <span className="block text-ink-soft truncate max-w-[220px]">{s.preview}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <p className="text-xs font-mono text-ink-soft mb-1">Manual</p>
                <ActionButton
                  loading={!!loading.schedulerIngest}
                  onClick={handleSchedulerIngest}
                  disabled={selectedTeamsIds.length + selectedZohoIds.length === 0}
                  className="w-full"
                >
                  Ingest selected ({selectedTeamsIds.length + selectedZohoIds.length})
                </ActionButton>
              </div>

              <div className="border-t border-hairline pt-3">
                <p className="text-xs font-mono text-ink-soft mb-2">Timer — custom Teams + Zoho each tick</p>
                <div className="grid grid-cols-3 gap-2 mb-2">
                  <label className="text-xs">
                    Interval (s)
                    <input
                      type="number"
                      min={5}
                      max={3600}
                      value={timerInterval}
                      onChange={(e) => setTimerInterval(Number(e.target.value) || 15)}
                      className="w-full border border-hairline rounded px-2 py-1 mt-0.5 text-sm"
                    />
                  </label>
                  <label className="text-xs">
                    Teams N
                    <input
                      type="number"
                      min={0}
                      max={10}
                      value={timerBatchTeams}
                      onChange={(e) => setTimerBatchTeams(Math.max(0, Number(e.target.value) || 0))}
                      className="w-full border border-hairline rounded px-2 py-1 mt-0.5 text-sm"
                    />
                  </label>
                  <label className="text-xs">
                    Zoho N
                    <input
                      type="number"
                      min={0}
                      max={10}
                      value={timerBatchZoho}
                      onChange={(e) => setTimerBatchZoho(Math.max(0, Number(e.target.value) || 0))}
                      className="w-full border border-hairline rounded px-2 py-1 mt-0.5 text-sm"
                    />
                  </label>
                </div>
                <div className="flex gap-2 mb-2">
                  <ActionButton
                    variant="secondary"
                    loading={!!loading.schedulerStart}
                    onClick={handleSchedulerStart}
                    className="flex-1 text-xs py-1"
                    disabled={!!playerStatus?.enabled || timerBatchTeams + timerBatchZoho < 1}
                  >
                    Start timer
                  </ActionButton>
                  <ActionButton
                    variant="secondary"
                    loading={!!loading.schedulerPause}
                    onClick={handleSchedulerPause}
                    className="flex-1 text-xs py-1"
                    disabled={!playerStatus?.enabled}
                  >
                    Pause
                  </ActionButton>
                </div>
                {playerStatus && (
                  <p className="text-xs font-mono text-ink-soft leading-relaxed">
                    {playerStatus.enabled ? "ON" : "OFF"}
                    {playerStatus.pause_reason ? ` · ${playerStatus.pause_reason}` : ""}
                    <br />
                    remaining T/Z: {playerStatus.remaining_teams}/{playerStatus.remaining_zoho}
                    {playerStatus.enabled && playerStatus.seconds_remaining != null
                      ? ` · next in ${playerStatus.seconds_remaining}s`
                      : ""}
                    {playerStatus.last_tick?.ingested_teams != null
                      ? ` · last +${playerStatus.last_tick.ingested_teams}T/+${playerStatus.last_tick.ingested_zoho ?? 0}Z`
                      : ""}
                  </p>
                )}
              </div>

              <div className="border-t border-hairline pt-3">
                <button
                  type="button"
                  onClick={() => setAdmissionDemosOpen((o) => !o)}
                  className="w-full text-left text-sm font-mono border border-hairline rounded px-2 py-1.5 hover:bg-invariant-tint/40 flex justify-between"
                >
                  <span>Admission failure demos</span>
                  <span className="text-ink-soft">{admissionDemosOpen ? "▾" : "▸"}</span>
                </button>
                {admissionDemosOpen && (
                  <div className="mt-2 space-y-2">
                    <p className="text-xs text-ink-soft">
                      One-click reject / duplicate scenarios. Primary path for admission demos (legacy
                      buttons further down still work).
                    </p>
                    {ADMISSION_DEMOS.map((demo) => (
                      <div
                        key={demo.id}
                        className="flex gap-2 items-start border border-hairline rounded px-2 py-2 bg-paper/40"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-semibold">{demo.title}</div>
                          <div className="text-xs text-ink-soft mt-0.5">Say: {demo.say}</div>
                        </div>
                        <ActionButton
                          variant="danger"
                          loading={!!loading[`sched-demo-${demo.id}`]}
                          onClick={() => handleSchedulerAdmissionDemo(demo.id, demo.title)}
                          className="!w-auto shrink-0 px-3 py-1 text-xs"
                        >
                          Run
                        </ActionButton>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <ActionButton
                variant="secondary"
                loading={!!loading.schedulerReset}
                onClick={handleSchedulerReset}
                className="w-full text-xs"
              >
                Reset player + demo
              </ActionButton>
            </div>
          )}
        </div>

        <div className="md:col-span-2 bg-white border border-hairline rounded-md p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h2 className="font-display font-semibold">Band A Pipeline</h2>
            {runs.length > 0 && (
              <label className="font-mono text-xs flex items-center gap-2">
                Watch run:
                <select
                  value={activeRunId || ""}
                  onChange={(e) => setActiveRunId(e.target.value || null)}
                  className="border border-hairline rounded px-2 py-1 bg-white text-sm max-w-[200px]"
                >
                  {runs.map((r) => (
                    <option key={r.run_id} value={r.run_id}>
                      {r.run_id} ({r.source})
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          {!activeRunId ? (
            <p className="text-sm text-ink-soft py-8 text-center">Trigger an entry point to watch the pipeline animate.</p>
          ) : (
            <PipelineAnimation events={watchedEvents} />
          )}
        </div>
      </section>

      {activeRunId && activeRun && (
        <section className="bg-white border border-hairline rounded-md p-4 mb-8">
          <h2 className="font-display font-semibold mb-3">Watch Run</h2>
          <div className="grid md:grid-cols-4 gap-4 font-mono text-sm">
            <div>Run ID: <Link to={`/runs/${activeRun.run_id}`} className="text-own">{activeRun.run_id}</Link></div>
            <div>Source: {activeRun.source}</div>
            <div>Lead: {activeRun.lead_id}</div>
            <div>State: <StatusBadge status={activeRun.state} /></div>
          </div>
        </section>
      )}

      {inboundMail && (
        <div className="mb-8">
          <InboundMailPanel mail={inboundMail} />
        </div>
      )}

      {inboundTeams && (
        <div className="mb-8">
          <InboundTeamsPanel message={inboundTeams} />
        </div>
      )}

      <section className="grid md:grid-cols-2 gap-4 mb-8">
        <div className="bg-white border border-hairline rounded-md p-4">
          <h2 className="font-display font-semibold mb-3">Event Timeline</h2>
          <EventTimeline events={watchedEvents} />
        </div>
        <div className="bg-white border border-hairline rounded-md p-4">
          <h2 className="font-display font-semibold mb-3">Queue</h2>
          {queueStatus && (
            <div className="font-mono text-sm mb-3">
              Pending: {queueStatus.pending} · Processing: {queueStatus.processing} · Worker:{" "}
              {queueStatus.worker_running ? "ON" : "OFF"}
            </div>
          )}
          {lastActiveRunDemo && (
            <p className="text-xs text-invariant mb-3 font-mono">
              {queueStatus?.worker_running
                ? "Hint: Worker is ON — Active-run demo needs the setup run to stay QUEUED. Turn Worker OFF, then re-run Active run blocked."
                : "Hint: Worker is OFF (Active-run demo stopped it if needed) so the blocked run stays QUEUED. Turn Worker ON only after you show the reject."}
            </p>
          )}
          <div className="flex gap-2 mb-3">
            <ActionButton variant="secondary" loading={!!loading.workerOn} onClick={handleWorkerOn} className="!w-auto text-xs px-3 py-1">
              Worker ON
            </ActionButton>
            <ActionButton variant="secondary" loading={!!loading.workerOff} onClick={handleWorkerOff} className="!w-auto text-xs px-3 py-1">
              Worker OFF
            </ActionButton>
          </div>
          {pendingQueueMessages.length === 0 ? (
            <p className="text-sm text-ink-soft font-mono">No pending queue messages</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left font-mono text-xs text-ink-soft">
                    <th className="py-2 pr-2">Run ID</th>
                    <th className="pr-2">Lead ID</th>
                    <th className="pr-2">Source</th>
                    <th className="pr-2">Status</th>
                    <th>Enqueued</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingQueueMessages.map((m: QueueMessage) => (
                    <tr key={m.message_id} className="border-b border-hairline hover:bg-paper/50">
                      <td className="py-2 pr-2 font-mono text-xs">
                        <Link to={`/runs/${m.run_id}`} className="text-own underline">
                          {m.run_id}
                        </Link>
                      </td>
                      <td className="pr-2 font-mono text-xs">{m.lead_id}</td>
                      <td className="pr-2">{m.source || "—"}</td>
                      <td className="pr-2">
                        <StatusBadge status={m.status} />
                      </td>
                      <td className="font-mono text-xs text-ink-soft">
                        {m.enqueued_at ? formatIst(m.enqueued_at) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <section className="bg-white border border-hairline rounded-md p-4 mb-8">
        <h2 className="font-display font-semibold mb-3">Test Admission Controls</h2>
        <p className="text-xs text-ink-soft mb-3">
          Legacy shortcuts — prefer <span className="font-semibold">Scheduler → Admission failure demos</span>{" "}
          for the presenter path (includes active-run).
        </p>
        <div className="flex flex-wrap gap-2">
          {[
            ["invalid-auth", "Invalid Auth"],
            ["tenant-mismatch", "Wrong Tenant"],
            ["duplicate", "Duplicate Event"],
            ["quota-exceeded", "Quota Exceeded"],
          ].map(([path, label]) => (
            <ActionButton
              key={path}
              variant="danger"
              loading={!!loading[`admission-${path}`]}
              onClick={() => handleAdmission(path, label)}
              className="!w-auto px-3 py-1 text-sm"
            >
              {label}
            </ActionButton>
          ))}
        </div>
        {admissionResult && <pre className="mt-3 text-xs font-mono bg-paper p-3 rounded overflow-auto">{admissionResult}</pre>}
      </section>

      <section className="bg-white border border-hairline rounded-md p-4">
        <h2 className="font-display font-semibold mb-3">Leads</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left font-mono text-xs text-ink-soft">
              <th className="py-2">Lead ID</th>
              <th>Company</th>
              <th>Industry</th>
              <th>Budget</th>
              <th>Status</th>
              <th>Run</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((l) => {
              const runId = l.active_run_id || l.latest_run_id || null;
              return (
              <tr key={l.lead_id} className="border-b border-hairline hover:bg-paper/50">
                <td className="py-2 font-mono">{l.lead_id}</td>
                <td>{l.company_name}</td>
                <td>{l.industry}</td>
                <td>₹{(l.budget / 100000).toFixed(1)}L</td>
                <td><StatusBadge status={l.status} /></td>
                <td className="font-mono text-xs">
                  {runId ? (
                    <span className="group relative inline-flex items-center gap-1">
                      <Link to={`/runs/${runId}`} className="text-own underline">
                        {runId}
                        {!l.active_run_id ? (
                          <span className="text-ink-soft no-underline"> (done)</span>
                        ) : null}
                      </Link>
                      <button
                        type="button"
                        title={`Delete ${runId}`}
                        aria-label={`Delete run ${runId}`}
                        className="opacity-0 group-hover:opacity-100 focus:opacity-100 focus-visible:opacity-100 text-invariant hover:text-invariant/80 px-1 leading-none"
                        onClick={async (e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          if (
                            !window.confirm(
                              `Delete run ${runId}? If this is the lead's only run, the lead will also be removed. This cannot be undone.`
                            )
                          ) {
                            return;
                          }
                          try {
                            await deleteRun(runId);
                            await refreshDashboardData();
                          } catch (err) {
                            window.alert(
                              err instanceof Error ? err.message : "Failed to delete run"
                            );
                          }
                        }}
                      >
                        ×
                      </button>
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      </>
      )}
    </div>
  );
}
