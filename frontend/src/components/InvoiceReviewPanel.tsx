import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActionButton } from "./ActionButton";
import { StatusBadge } from "./StatusBadge";
import {
  ApiError,
  chatInvoiceCase,
  demoInvoicePolicyBlock,
  fetchInvoiceCases,
  fetchInvoiceFinding,
  fetchInvoiceHealth,
  fetchInvoiceJournal,
  fetchInvoiceReplay,
  fetchInvoiceRuns,
  fetchRunInboundMail,
  fetchRunInboundTeams,
  ingestInvoiceCase,
  startWorker,
  type InvoiceCase,
  type InvoiceFinding,
  type InvoiceHealth,
  type InvoiceRunSummary,
  type InboundMail,
  type InboundTeams,
  type JournalTurn,
} from "../services/api";

type Props = {
  tenant: string;
  resetNonce?: number;
  onBanner: (message: string, type: "success" | "error" | "info", autoDismiss?: boolean) => void;
  onWatchRun: (runId: string | null) => void;
};

const PINNED_CASES: Record<string, string> = {
  "CASE-03": "price variance (recommended)",
  "CASE-06": "clean match (recommended)",
};

const DEMO_STEPS = [
  { id: "email", label: "1 · Email run" },
  { id: "chat", label: "2 · Chat run" },
  { id: "policy", label: "3 · Policy block" },
  { id: "replay", label: "4 · Replay" },
] as const;

const COMPARISON_ROWS: { piece: string; platform: string; ours: string }[] = [
  { piece: "Agent loop", platform: "Responses API + tools", ours: "Hand-rolled while + budgets" },
  { piece: "Tool registry", platform: "Function schemas on call", ours: "Hard allowlist of 7" },
  { piece: "Connectors", platform: "nothing", ours: "HTTP → mocks :8090" },
  { piece: "Policy gate", platform: "nothing", ours: "Independent policy_gate.py" },
  { piece: "Credential broker", platform: "nothing", ours: "Mint only after journal intent" },
  { piece: "Journal", platform: "nothing", ours: "SQLite saw / decided / called / result" },
  { piece: "Replay", platform: "nothing", ours: "0 model calls · $0" },
  { piece: "Context", platform: "nothing", ours: "Rebuild each turn; door never passed" },
  { piece: "Limits", platform: "nothing", ours: "Turns · money · wall-clock" },
  { piece: "Finding", platform: "nothing", ours: "Structured JSON + UI" },
];

function doorLabel(arrival?: string | null) {
  if (arrival === "chat") return "chat";
  if (arrival === "zoho_mail") return "zoho";
  if (arrival === "teams") return "teams";
  if (arrival === "case_email") return "email";
  return arrival || "—";
}

function isIngressDoor(arrival?: string | null) {
  return arrival === "case_email" || arrival === "zoho_mail" || arrival === "teams";
}

function toolOrder(turns: JournalTurn[]) {
  return turns.filter((t) => t.tool_name && !t.blocked_by_policy).map((t) => t.tool_name as string);
}

function HealthPill({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <span
      title={detail}
      className={`inline-flex items-center gap-1.5 font-mono text-xs px-2.5 py-1 rounded-full border ${
        ok ? "bg-own-tint text-own border-own/20" : "bg-invariant-tint text-invariant border-invariant/30"
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-own" : "bg-invariant"}`} />
      {label}
    </span>
  );
}

export function InvoiceReviewPanel({ tenant, resetNonce = 0, onBanner, onWatchRun }: Props) {
  const [cases, setCases] = useState<InvoiceCase[]>([]);
  const [runs, setRuns] = useState<InvoiceRunSummary[]>([]);
  const [selectedCase, setSelectedCase] = useState("CASE-03");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [finding, setFinding] = useState<InvoiceFinding | null>(null);
  const [inboundMail, setInboundMail] = useState<InboundMail | null>(null);
  const [inboundTeams, setInboundTeams] = useState<InboundTeams | null>(null);
  const [turns, setTurns] = useState<JournalTurn[]>([]);
  const [replay, setReplay] = useState<{ model_calls: number; cost_cents: number } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [forceSync, setForceSync] = useState(true);
  const [health, setHealth] = useState<InvoiceHealth | null>(null);
  const [compareIds, setCompareIds] = useState<[string | null, string | null]>([null, null]);
  const [expandedTurns, setExpandedTurns] = useState<Set<number>>(new Set());
  const [flashTurn, setFlashTurn] = useState<number | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [showComparison, setShowComparison] = useState(false);
  const [investigateStartedAt, setInvestigateStartedAt] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const journalRef = useRef<HTMLDivElement>(null);
  const knownRunIdsRef = useRef<Set<string>>(new Set());
  const seededRunsRef = useRef(false);

  const clearSelection = useCallback(() => {
    setActiveRunId(null);
    setFinding(null);
    setInboundMail(null);
    setInboundTeams(null);
    setTurns([]);
    setReplay(null);
    setCompareIds([null, null]);
    setFlashTurn(null);
    onWatchRun(null);
  }, [onWatchRun]);

  const refresh = useCallback(async () => {
    const [c, r] = await Promise.all([fetchInvoiceCases(), fetchInvoiceRuns(tenant)]);
    setCases(c.cases);
    setRuns(r);
    setSelectedCase((prev) => prev || c.cases.find((x) => x.case_id === "CASE-03")?.case_id || c.cases[0]?.case_id || "");

    const ids = new Set(r.map((x) => x.run_id));
    let autoPick: string | null = null;
    if (!seededRunsRef.current) {
      knownRunIdsRef.current = ids;
      seededRunsRef.current = true;
    } else {
      const newcomers = r.filter(
        (x) =>
          (x.arrival_source === "zoho_mail" || x.arrival_source === "teams") &&
          !knownRunIdsRef.current.has(x.run_id)
      );
      knownRunIdsRef.current = ids;
      if (newcomers.length > 0) {
        autoPick = newcomers[0].run_id;
        setReplay(null);
        const door = newcomers[0].arrival_source === "teams" ? "Teams" : "Zoho";
        onBanner(`Live ${door} → ${autoPick}`, "success");
      }
    }

    setActiveRunId((prev) => {
      if (autoPick) {
        onWatchRun(autoPick);
        return autoPick;
      }
      if (prev && !r.some((x) => x.run_id === prev)) {
        setFinding(null);
        setTurns([]);
        setReplay(null);
        onWatchRun(null);
        return null;
      }
      return prev;
    });
  }, [tenant, onWatchRun, onBanner]);

  useEffect(() => {
    knownRunIdsRef.current = new Set();
    seededRunsRef.current = false;
    clearSelection();
    void refresh().catch((e) => onBanner(e instanceof Error ? e.message : "Load failed", "error", false));
  }, [resetNonce]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void refresh().catch((e) => onBanner(e instanceof Error ? e.message : "Load failed", "error", false));
  }, [refresh, onBanner]);

  // Live Zoho / external arrivals — runs list must poll (not only refresh on mount/actions)
  useEffect(() => {
    const id = window.setInterval(() => {
      void refresh().catch(() => {});
    }, 2000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    const load = () =>
      fetchInvoiceHealth()
        .then(setHealth)
        .catch(() =>
          setHealth({
            api: { ok: false, detail: "unreachable" },
            mocks: { ok: false },
            model: { ok: false },
          })
        );
    void load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, []);

  const activeRun = runs.find((r) => r.run_id === activeRunId);
  const investigating =
    !!busy ||
    activeRun?.state === "REVIEWING" ||
    ((activeRun?.arrival_source === "zoho_mail" || activeRun?.arrival_source === "teams") &&
      (activeRun?.state === "QUEUED" || activeRun?.state === "DISPATCHED"));

  useEffect(() => {
    if (investigating) {
      if (!investigateStartedAt) setInvestigateStartedAt(Date.now());
    } else {
      setInvestigateStartedAt(null);
      setElapsedSec(0);
    }
  }, [investigating, investigateStartedAt]);

  useEffect(() => {
    if (!investigateStartedAt) return;
    const id = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - investigateStartedAt) / 1000));
    }, 500);
    return () => window.clearInterval(id);
  }, [investigateStartedAt]);

  useEffect(() => {
    if (!activeRunId) {
      setFinding(null);
      setTurns([]);
      setReplay(null);
      setInboundMail(null);
      setInboundTeams(null);
      return;
    }
    const load = async () => {
      try {
        const j = await fetchInvoiceJournal(activeRunId);
        setTurns(j.turns);
        try {
          setFinding(await fetchInvoiceFinding(activeRunId));
        } catch {
          setFinding(null);
        }
      } catch {
        /* still reviewing */
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 1500);
    return () => window.clearInterval(id);
  }, [activeRunId]);

  useEffect(() => {
    if (!activeRunId) {
      setInboundMail(null);
      setInboundTeams(null);
      return;
    }
    if (activeRun?.arrival_source === "zoho_mail") {
      setInboundTeams(null);
      void fetchRunInboundMail(activeRunId)
        .then(setInboundMail)
        .catch(() => setInboundMail(null));
      return;
    }
    if (activeRun?.arrival_source === "teams") {
      setInboundMail(null);
      void fetchRunInboundTeams(activeRunId)
        .then(setInboundTeams)
        .catch(() => setInboundTeams(null));
      return;
    }
    setInboundMail(null);
    setInboundTeams(null);
  }, [activeRunId, activeRun?.arrival_source]);

  const sortedCases = useMemo(() => {
    const pinned = Object.keys(PINNED_CASES);
    return [...cases].sort((a, b) => {
      const ai = pinned.indexOf(a.case_id);
      const bi = pinned.indexOf(b.case_id);
      if (ai === -1 && bi === -1) return a.case_id.localeCompare(b.case_id);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
  }, [cases]);

  const demoStep = useMemo(() => {
    if (replay) return "replay";
    if (turns.some((t) => t.blocked_by_policy)) return "policy";
    const hasEmail = runs.some((r) => isIngressDoor(r.arrival_source));
    const hasChat = runs.some((r) => r.arrival_source === "chat");
    if (hasEmail && hasChat) return "chat";
    if (hasEmail) return "email";
    return "email";
  }, [runs, turns, replay]);

  const comparePair = useMemo(() => {
    const a = compareIds[0] ? runs.find((r) => r.run_id === compareIds[0]) : null;
    const b = compareIds[1] ? runs.find((r) => r.run_id === compareIds[1]) : null;
    if (a && b) return [a, b] as const;
    // Auto: same document_ref, email/zoho/teams + chat
    for (const r of runs) {
      if (!r.document_ref) continue;
      const email = runs.find((x) => x.document_ref === r.document_ref && isIngressDoor(x.arrival_source));
      const chat = runs.find((x) => x.document_ref === r.document_ref && x.arrival_source === "chat");
      if (email && chat) return [email, chat] as const;
    }
    return null;
  }, [runs, compareIds]);

  const [compareJournals, setCompareJournals] = useState<[JournalTurn[], JournalTurn[]]>([[], []]);
  const [compareFindings, setCompareFindings] = useState<[InvoiceFinding | null, InvoiceFinding | null]>([
    null,
    null,
  ]);

  useEffect(() => {
    if (!comparePair) {
      setCompareJournals([[], []]);
      setCompareFindings([null, null]);
      return;
    }
    void Promise.all([
      fetchInvoiceJournal(comparePair[0].run_id),
      fetchInvoiceJournal(comparePair[1].run_id),
      fetchInvoiceFinding(comparePair[0].run_id).catch(() => null),
      fetchInvoiceFinding(comparePair[1].run_id).catch(() => null),
    ]).then(([j0, j1, f0, f1]) => {
      setCompareJournals([j0.turns, j1.turns]);
      setCompareFindings([f0, f1]);
    });
  }, [comparePair]);

  const run = async (key: string, fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      onBanner(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Error", "error", false);
    } finally {
      setBusy(null);
    }
  };

  const selectRun = (runId: string) => {
    setActiveRunId(runId);
    onWatchRun(runId);
    setReplay(null);
  };

  const toggleComparePin = (runId: string) => {
    setCompareIds(([a, b]) => {
      if (a === runId) return [b, null];
      if (b === runId) return [a, null];
      if (!a) return [runId, null];
      if (!b) return [a, runId];
      return [b, runId];
    });
  };

  const handleEmailIngest = () =>
    run("email", async () => {
      if (!forceSync) await startWorker();
      setReplay(null);
      const result = await ingestInvoiceCase(selectedCase, forceSync);
      const runId = String(result.run_id);
      selectRun(runId);
      onBanner(
        forceSync ? `CASE ${selectedCase} email → ${runId}` : `CASE ${selectedCase} queued → ${runId}`,
        "success"
      );
      await refresh();
    });

  const handleChat = () =>
    run("chat", async () => {
      setReplay(null);
      const result = await chatInvoiceCase(selectedCase);
      const runId = String(result.run_id);
      selectRun(runId);
      onBanner(`Chat door ${selectedCase} → ${runId}`, "success");
      await refresh();
    });

  const handleReplay = () =>
    run("replay", async () => {
      if (!activeRunId) return;
      const r = await fetchInvoiceReplay(activeRunId);
      setTurns(r.turns);
      setFinding(r.finding);
      setReplay({ model_calls: r.model_calls, cost_cents: r.cost_cents });
      onBanner(`Replay — ${r.model_calls} model calls, $${(r.cost_cents / 100).toFixed(2)}`, "info");
    });

  const handlePolicyBlock = () =>
    run("policy", async () => {
      if (!activeRunId) return;
      const r = await demoInvoicePolicyBlock(activeRunId);
      setFlashTurn(r.turn.turn_no);
      const j = await fetchInvoiceJournal(activeRunId);
      setTurns(j.turns);
      setExpandedTurns((prev) => new Set(prev).add(r.turn.turn_no));
      onBanner(`Policy gate blocked — independent of the model`, "info");
      requestAnimationFrame(() => {
        journalRef.current?.querySelector(`[data-turn="${r.turn.turn_no}"]`)?.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
      });
    });

  const toggleExpand = (turnNo: number) => {
    setExpandedTurns((prev) => {
      const next = new Set(prev);
      if (next.has(turnNo)) next.delete(turnNo);
      else next.add(turnNo);
      return next;
    });
  };

  const budget = finding?.budget;

  return (
    <div className="space-y-4">
      {/* A. Health */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs uppercase tracking-wide text-ink-soft">Services</span>
        <HealthPill label="API" ok={!!health?.api.ok} detail={health?.api.detail} />
        <HealthPill
          label={`Mocks ${health?.mocks.url?.includes("8090") ? ":8090" : ""}`.trim()}
          ok={!!health?.mocks.ok}
          detail={health?.mocks.detail}
        />
        <HealthPill
          label={`Model ${health?.model.name || "…"}`}
          ok={!!health?.model.ok}
          detail={health?.model.endpoint_host}
        />
      </div>

      {/* B. Demo steps */}
      <div className="flex flex-wrap gap-2">
        {DEMO_STEPS.map((s) => (
          <span
            key={s.id}
            className={`font-mono text-xs px-3 py-1.5 rounded-full border ${
              demoStep === s.id
                ? "bg-ink text-white border-ink"
                : "bg-white text-ink-soft border-hairline"
            }`}
          >
            {s.label}
          </span>
        ))}
      </div>

      {/* C. Case player */}
      <div className="rounded-xl border border-line bg-white p-4 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm flex flex-col gap-1 min-w-[16rem] flex-1">
            <span className="text-muted">CASE (pinned demos first)</span>
            <select
              className="border border-line rounded-md px-2 py-1.5 font-mono text-sm"
              value={selectedCase}
              onChange={(e) => setSelectedCase(e.target.value)}
            >
              {sortedCases.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id} — {c.document_ref}
                  {PINNED_CASES[c.case_id] ? ` · ${PINNED_CASES[c.case_id]}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm flex items-center gap-2 pb-1.5">
            <input type="checkbox" checked={forceSync} onChange={(e) => setForceSync(e.target.checked)} />
            Sync (skip queue)
          </label>
          <ActionButton loading={busy === "email"} onClick={handleEmailIngest} className="!w-auto px-3">
            Play CASE (email door)
          </ActionButton>
          <ActionButton loading={busy === "chat"} onClick={handleChat} className="!w-auto px-3">
            Ask in chat
          </ActionButton>
          <ActionButton
            variant="danger"
            loading={busy === "policy"}
            onClick={handlePolicyBlock}
            disabled={!activeRunId}
            className="!w-auto px-3"
          >
            Demo: force policy block
          </ActionButton>
          <ActionButton loading={busy === "replay"} onClick={handleReplay} disabled={!activeRunId} className="!w-auto px-3">
            Replay journal
          </ActionButton>
        </div>
        <p className="text-xs text-muted">
          Email → async or sync · chat always sync · agent never sees which door · mocks :8090 · Foundry{" "}
          {health?.model.name || "gpt-5-mini"}
        </p>
        <p className="text-xs text-muted">
          Live Zoho: <span className="font-semibold">attach</span> pack{" "}
          <span className="font-mono">.json</span>/<span className="font-mono">.txt</span>{" "}
          <span className="font-semibold">or paste</span> JSON in the body to{" "}
          <span className="font-mono">aditya.chowdhury@giantleapsystems.com</span> → door{" "}
          <span className="font-mono">zoho</span>. Live Teams 1:1:{" "}
          <span className="font-semibold">paste</span> pack JSON in the chat (prose + JSON OK) → door{" "}
          <span className="font-mono">teams</span>. Unrelated Zoho/Teams text still lands in Invoice Review
          with an <span className="font-mono">exception:not_an_invoice</span> finding (not Sales Lead). No live{" "}
          <span className="font-mono">CASE-XX</span> map — use Play CASE in the UI for fixtures. Bridge :8080 +
          ngrok + Deluge Script B required for Zoho file attach. Use dashboard simulators for Sales Lead demos.
        </p>
        {investigating && (
          <div className="flex items-center gap-2 text-sm bg-own-tint text-own px-3 py-2 rounded-md">
            <span className="inline-block w-3 h-3 border-2 border-own border-t-transparent rounded-full animate-spin" />
            Investigating… {elapsedSec}s · run {activeRunId || "…"}
          </div>
        )}
      </div>

      {/* D. Runs + compare */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-line bg-white p-4">
          <h3 className="font-semibold mb-1">Invoice runs</h3>
          <p className="text-xs text-muted mb-2">Door badges are for you — the agent never receives them.</p>
          <ul className="space-y-1 max-h-72 overflow-auto text-sm">
            {runs.map((r) => (
              <li key={r.run_id}>
                <div
                  className={`w-full text-left px-2 py-1.5 rounded-md hover:bg-gray-50 ${
                    activeRunId === r.run_id ? "bg-own-tint" : ""
                  }`}
                >
                  <button type="button" className="w-full text-left" onClick={() => selectRun(r.run_id)}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{r.run_id}</span>
                      <StatusBadge status={r.state} />
                    </div>
                    <div className="text-xs text-muted truncate mt-0.5">{r.document_ref}</div>
                  </button>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="font-mono text-[10px] uppercase px-1.5 py-0.5 rounded bg-gray-100">
                      door:{doorLabel(r.arrival_source)}
                    </span>
                    <span className="font-mono text-[10px] text-muted">{r.dispatch_route}</span>
                    <button
                      type="button"
                      className="ml-auto text-[10px] font-mono underline text-own"
                      onClick={() => toggleComparePin(r.run_id)}
                    >
                      {compareIds[0] === r.run_id || compareIds[1] === r.run_id ? "unpin" : "pin compare"}
                    </button>
                  </div>
                </div>
              </li>
            ))}
            {runs.length === 0 && <li className="text-muted text-sm">No invoice runs yet</li>}
          </ul>
        </div>

        <div className="rounded-xl border border-line bg-white p-4">
          <h3 className="font-semibold mb-1">Email vs chat compare</h3>
          <p className="text-xs text-muted mb-3">Same document, different doors — tool order can differ; both valid.</p>
          {!comparePair && (
            <p className="text-sm text-muted">
              Run the same CASE via email and chat (or pin two runs) to unlock this panel.
            </p>
          )}
          {comparePair && (
            <div className="grid grid-cols-2 gap-3 text-sm">
              {comparePair.map((r, i) => (
                <div key={r.run_id} className="border border-hairline rounded-md p-2">
                  <div className="font-mono text-xs mb-1">
                    {doorLabel(r.arrival_source)} · {r.run_id}
                  </div>
                  <div className="font-semibold text-sm mb-2">
                    {compareFindings[i]?.verdict || r.state}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {toolOrder(compareJournals[i])
                      .filter((t, idx, arr) => arr.indexOf(t) === idx)
                      .slice(0, 8)
                      .map((t) => (
                        <span key={t} className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-gray-100">
                          {t.replace(/^get_/, "").replace(/^extract_/, "x_")}
                        </span>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* E. Finding */}
      <div className="rounded-xl border border-line bg-white p-4">
        <h3 className="font-semibold mb-2">Finding</h3>
        {!finding && <p className="text-sm text-muted">Select a run or wait for FINDING_READY</p>}
        {finding && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-base font-semibold">{finding.verdict}</span>
              <span className="font-mono text-[10px] uppercase px-1.5 py-0.5 rounded bg-gray-100">
                door:{doorLabel(finding.arrival_source)}
              </span>
              <span className="font-mono text-[10px] text-muted">{finding.dispatch_route}</span>
            </div>
            {inboundMail && (
              <div className="rounded-md border border-line bg-gray-50 px-3 py-2 text-xs space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="font-semibold text-own">Received email (Zoho)</div>
                  {(() => {
                    try {
                      const parsed = inboundMail.invoice_content
                        ? JSON.parse(inboundMail.invoice_content)
                        : null;
                      return parsed?.inbound_kind === "non_invoice" ? (
                        <span className="font-mono text-[10px] uppercase px-1.5 py-0.5 rounded bg-amber-100 text-amber-900">
                          non-invoice
                        </span>
                      ) : null;
                    } catch {
                      return null;
                    }
                  })()}
                </div>
                <div>
                  <span className="text-muted">From:</span> {inboundMail.mail_from || "—"}
                </div>
                <div>
                  <span className="text-muted">Subject:</span> {inboundMail.mail_subject || "—"}
                </div>
                {(inboundMail.attachment_filename || inboundMail.invoice_source) && (
                  <div>
                    <span className="text-muted">Invoice source:</span>{" "}
                    {inboundMail.attachment_filename
                      ? inboundMail.attachment_filename
                      : inboundMail.invoice_source || "body"}
                  </div>
                )}
                {inboundMail.mail_body ? (
                  <pre className="text-muted whitespace-pre-wrap font-sans max-h-28 overflow-y-auto text-[11px]">
                    {inboundMail.mail_body}
                  </pre>
                ) : null}
                {inboundMail.invoice_content ? (
                  (() => {
                    let nonInv = false;
                    try {
                      nonInv =
                        JSON.parse(inboundMail.invoice_content)?.inbound_kind === "non_invoice";
                    } catch {
                      nonInv = false;
                    }
                    if (nonInv) {
                      return (
                        <details className="pt-1">
                          <summary className="cursor-pointer text-muted">
                            Stored extract payload
                          </summary>
                          <pre className="text-muted whitespace-pre-wrap font-mono max-h-32 overflow-y-auto text-[11px] mt-1">
                            {inboundMail.invoice_content}
                          </pre>
                        </details>
                      );
                    }
                    return (
                      <pre className="text-muted whitespace-pre-wrap font-mono max-h-40 overflow-y-auto text-[11px]">
                        {inboundMail.invoice_content}
                      </pre>
                    );
                  })()
                ) : null}
              </div>
            )}
            {inboundTeams && (
              <div className="rounded-md border border-line bg-gray-50 px-3 py-2 text-xs space-y-1">
                <div className="font-semibold text-own">Received message (Teams)</div>
                <div>
                  <span className="text-muted">From:</span> {inboundTeams.teams_from || "—"}
                </div>
                {inboundTeams.teams_text && (
                  <p className="text-muted whitespace-pre-wrap line-clamp-3">{inboundTeams.teams_text}</p>
                )}
              </div>
            )}
            {budget && (
              <div className="grid sm:grid-cols-3 gap-2 text-xs font-mono">
                <div className="bg-gray-50 rounded px-2 py-1.5">
                  <details>
                    <summary className="cursor-pointer list-none underline decoration-dotted decoration-muted underline-offset-2 hover:text-own [&::-webkit-details-marker]:hidden">
                      Turns {budget.turns_used ?? 0}/{budget.turns ?? "—"}
                    </summary>
                    <p className="mt-1 text-[10px] text-muted font-sans normal-case leading-snug no-underline">
                      Turns: each Foundry call in the agent loop. Budget stops when this hits the cap.
                      One reply can request several tools.
                    </p>
                  </details>
                  <div className="h-1 mt-1 bg-gray-200 rounded overflow-hidden">
                    <div
                      className="h-full bg-own"
                      style={{
                        width: `${Math.min(100, ((budget.turns_used ?? 0) / Math.max(1, budget.turns ?? 1)) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
                <div className="bg-gray-50 rounded px-2 py-1.5">
                  ${((budget.usd_spent_cents ?? 0) / 100).toFixed(2)} / $
                  {((budget.usd_cents ?? 0) / 100).toFixed(2)}
                </div>
                <div className="bg-gray-50 rounded px-2 py-1.5">wall ≤ {budget.seconds ?? "—"}s</div>
              </div>
            )}
            <div>
              <span className="text-muted text-xs">Reasoning</span>
              <p className="mt-0.5">{finding.reasoning}</p>
            </div>
            {Array.isArray(finding.checks) && finding.checks.length > 0 && (
              <div>
                <span className="text-muted text-xs">Checks</span>
                <ul className="mt-1 space-y-1">
                  {finding.checks.map((c, i) => {
                    const row = c as { what?: string; result?: string };
                    return (
                      <li key={i} className="border-b border-hairline pb-1">
                        <div className="font-medium">{row.what || `Check ${i + 1}`}</div>
                        <div className="text-xs text-muted">{row.result || JSON.stringify(c)}</div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {finding.policy_ids?.length > 0 && (
              <div className="font-mono text-xs">Policies: {finding.policy_ids.join(", ")}</div>
            )}
            {finding.policy_choice_reason && (
              <div className="text-xs text-muted">
                Policy choice: {finding.policy_choice_reason}
              </div>
            )}
            {finding.uncertainties?.length > 0 && (
              <div>
                <span className="text-muted text-xs">Uncertainties</span>
                <ul className="list-disc pl-4 mt-1">
                  {finding.uncertainties.map((u) => (
                    <li key={u}>{u}</li>
                  ))}
                </ul>
              </div>
            )}
            {finding.raw_text && (
              <div>
                <button
                  type="button"
                  className="text-xs font-mono underline text-own"
                  onClick={() => setShowRaw((v) => !v)}
                >
                  {showRaw ? "Hide" : "Show"} analyst write-up
                </button>
                {showRaw && (
                  <pre className="mt-2 text-xs whitespace-pre-wrap bg-gray-50 p-2 rounded-md max-h-48 overflow-auto">
                    {finding.raw_text}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* G. Replay climax */}
      {replay && (
        <div className="rounded-xl border-2 border-ink bg-white p-5 text-center">
          <div className="font-display text-2xl font-bold">
            {replay.model_calls} model calls · ${(replay.cost_cents / 100).toFixed(2)}
          </div>
          <p className="text-sm text-ink-soft mt-1">Rebuilt from journal only — no Foundry call on replay</p>
        </div>
      )}

      {/* F. Journal */}
      <div className="rounded-xl border border-line bg-white p-4" ref={journalRef}>
        <div className="flex items-start justify-between gap-3 mb-2">
          <h3 className="font-semibold">Journal</h3>
          <details className="text-xs text-muted font-mono text-right max-w-[14rem]">
            <summary className="cursor-pointer list-none underline decoration-dotted underline-offset-2 hover:text-own [&::-webkit-details-marker]:hidden">
              {turns.length} Steps
            </summary>
            <p className="mt-1 text-[10px] font-sans normal-case leading-snug text-left no-underline">
              Steps: one journal row per tool call and the final finding. If the model batches tools in
              one reply, steps can exceed turns.
            </p>
          </details>
        </div>
        <ol className="space-y-2 max-h-96 overflow-auto text-sm">
          {turns.map((t) => {
            const open = expandedTurns.has(t.turn_no) || flashTurn === t.turn_no;
            const resultBlob = JSON.stringify(t.tool_result || {}, null, 2);
            return (
              <li
                key={`${t.turn_no}-${t.decided}-${t.tool_name}`}
                data-turn={t.turn_no}
                className={`border-b border-line pb-2 ${
                  t.blocked_by_policy ? "bg-invariant-tint/40 -mx-2 px-2 rounded" : ""
                } ${flashTurn === t.turn_no ? "ring-2 ring-invariant" : ""}`}
              >
                <button type="button" className="w-full text-left" onClick={() => toggleExpand(t.turn_no)}>
                  <div className="flex gap-2 items-center flex-wrap">
                    <span className="font-mono text-xs text-muted">T{t.turn_no}</span>
                    <span className="font-medium">{t.decided}</span>
                    {t.blocked_by_policy && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-invariant text-white">
                        policy block
                      </span>
                    )}
                    <span className="ml-auto font-mono text-[10px] text-muted">{t.token_cost_cents}¢</span>
                  </div>
                  {t.tool_name && (
                    <div className="font-mono text-xs text-muted mt-0.5">
                      {t.tool_name}({JSON.stringify(t.tool_args)})
                    </div>
                  )}
                </button>
                {open && (
                  <pre className="mt-2 text-[11px] whitespace-pre-wrap bg-gray-50 p-2 rounded max-h-40 overflow-auto">
                    {resultBlob.length > 2500 ? resultBlob.slice(0, 2500) + "\n…(truncated)" : resultBlob}
                  </pre>
                )}
              </li>
            );
          })}
          {turns.length === 0 && <li className="text-muted">No journal turns yet</li>}
        </ol>
      </div>

      {/* H. Comparison table */}
      <div className="rounded-xl border border-line bg-white p-4">
        <button
          type="button"
          className="w-full flex items-center justify-between text-left"
          onClick={() => setShowComparison((v) => !v)}
        >
          <h3 className="font-semibold">Comparison table — Foundry vs what we built</h3>
          <span className="font-mono text-xs text-muted">{showComparison ? "hide" : "show"}</span>
        </button>
        {showComparison && (
          <div className="mt-3 overflow-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline text-left font-mono text-xs text-muted">
                  <th className="py-1 pr-2">§10 piece</th>
                  <th className="py-1 pr-2">Platform gave</th>
                  <th className="py-1">We wrote</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON_ROWS.map((row) => (
                  <tr key={row.piece} className="border-b border-hairline align-top">
                    <td className="py-2 pr-2 font-medium whitespace-nowrap">{row.piece}</td>
                    <td className="py-2 pr-2 text-muted">{row.platform}</td>
                    <td className="py-2">{row.ours}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-muted mt-2">
              Hardest row for talk track: policy gate / broker — platform gave nothing; we built them ourselves.
              Model on this account: {health?.model.name || "gpt-5-mini"} (gpt-4o-mini deprecated).
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
