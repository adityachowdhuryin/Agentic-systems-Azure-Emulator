import { useEffect, useState } from "react";

const STORAGE_COLLAPSED = "band-a-demo-guide-collapsed";
const STORAGE_CHECKED = "band-a-demo-guide-checked";

export interface DemoStep {
  id: string;
  title: string;
  action: string;
  say: string;
  expect: string;
  tab?: "zoho" | "teams" | "scheduler" | "admission" | "queue" | "header";
  optional?: boolean;
}

export const DEMO_STEPS: DemoStep[] = [
  {
    id: "1",
    title: "Live Zoho Mail",
    action: "Send mail to the monitor address (ngrok + bridge running)",
    say: "Real email enters Band A the same way as a CRM webhook — watch the inbound email panel.",
    expect: "New Zoho Mail run + Received Email panel; pipeline animates",
    tab: "zoho",
    optional: true,
  },
  {
    id: "2",
    title: "Live Teams bot",
    action: "Message Band A Sales Bot → qualify a lead (or View prompts)",
    say: "Salesperson asks in Teams — sync path through the same admission controls.",
    expect: "Sync run + Received Message panel; optional ingestion-logs card",
    tab: "teams",
    optional: true,
  },
  {
    id: "3",
    title: "Scheduler happy-path ingest",
    action: "Scheduler → Happy path catalog → Ingest selected (Teams + Zoho), or Start timer",
    say: "Fictional samples use the real webhook adapters — Teams sync, Zoho async.",
    expect: "New runs; timer pauses when samples run out",
    tab: "scheduler",
  },
  {
    id: "4a",
    title: "Admission: invalid auth",
    action: "Scheduler → Admission failure demos → Invalid auth → Run",
    say: "Bad identity is rejected before a run exists.",
    expect: "Rejected banner; rejected=true, no run",
    tab: "scheduler",
  },
  {
    id: "4b",
    title: "Admission: tenant mismatch",
    action: "Scheduler → Admission failure demos → Tenant mismatch → Run",
    say: "Token tenant must match the request tenant.",
    expect: "Rejected banner; no run",
    tab: "scheduler",
  },
  {
    id: "4c",
    title: "Admission: duplicate event_id",
    action: "Scheduler → Admission failure demos → Duplicate event_id → Run",
    say: "Same event_id twice is idempotent — same run_id, not a new ticket.",
    expect: "Duplicate banner; same run_id both times",
    tab: "scheduler",
  },
  {
    id: "4d",
    title: "Admission: active run blocked",
    action: "Scheduler → Admission failure demos → Active run blocked → Run",
    say: "A second request while the lead still has a QUEUED run is rejected. Demo auto-stops Worker if needed.",
    expect: "Rejected banner; timeline on existing QUEUED run",
    tab: "scheduler",
  },
  {
    id: "4e",
    title: "Admission: quota exceeded",
    action: "Scheduler → Admission failure demos → Quota exceeded → Run",
    say: "Tenant active-run budget is full — admission refuses new work.",
    expect: "Rejected banner; Reset afterward to clear fill runs",
    tab: "scheduler",
  },
  {
    id: "5",
    title: "Queue backlog",
    action: "Queue → Worker OFF → create work (Zoho/samples) → Worker ON",
    say: "Band A finishes at the queue; Band B drains when available.",
    expect: "Pending rises, then drains when worker restarts",
    tab: "queue",
  },
  {
    id: "6",
    title: "Reset player + demo",
    action: "Scheduler → Reset player + demo (or Header → Reset Demo)",
    say: "Clear simulator and sample-player data; live Zoho Mail / Teams stay.",
    expect: "Samples unused again; live runs preserved",
    tab: "scheduler",
  },
];

interface DemoGuidePanelProps {
  onGoToTab?: (tab: "zoho" | "teams" | "scheduler") => void;
}

export function DemoGuidePanel({ onGoToTab }: DemoGuidePanelProps) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(STORAGE_COLLAPSED) === "true");
  const [checked, setChecked] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_CHECKED) || "{}");
    } catch {
      return {};
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_COLLAPSED, String(collapsed));
  }, [collapsed]);

  useEffect(() => {
    localStorage.setItem(STORAGE_CHECKED, JSON.stringify(checked));
  }, [checked]);

  const toggleStep = (id: string) => {
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const resetChecklist = () => {
    setChecked({});
    localStorage.removeItem(STORAGE_CHECKED);
  };

  const doneCount = DEMO_STEPS.filter((s) => checked[s.id]).length;

  return (
    <section className="bg-white border-2 border-own rounded-md mb-8 overflow-hidden">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-3 bg-own-tint text-left"
      >
        <div>
          <span className="font-display font-semibold text-own">Demo Guide</span>
          <span className="ml-3 font-mono text-xs text-ink-soft">
            {doneCount}/{DEMO_STEPS.length} steps · live Zoho/Teams + Scheduler
          </span>
        </div>
        <span className="font-mono text-xs text-own">{collapsed ? "Show" : "Hide"}</span>
      </button>

      {!collapsed && (
        <div className="p-4 space-y-4">
          <p className="text-sm text-ink-soft">
            Dual-track presenter checklist: optional live bridges first, then Scheduler happy path and
            all five admission demos. Legacy Test Admission buttons remain as a fallback.
          </p>
          <ol className="space-y-3">
            {DEMO_STEPS.map((step) => (
              <li
                key={step.id}
                className={`border rounded-md p-3 ${checked[step.id] ? "border-own bg-own-tint/50 opacity-80" : "border-hairline"}`}
              >
                <label className="flex gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!checked[step.id]}
                    onChange={() => toggleStep(step.id)}
                    className="mt-1"
                  />
                  <div className="flex-1 text-sm">
                    <div className="font-display font-semibold">
                      {step.id}. {step.title}
                      {step.optional ? (
                        <span className="ml-2 font-mono text-xs font-normal text-ink-soft">optional</span>
                      ) : null}
                    </div>
                    <div className="mt-1">
                      <span className="font-mono text-xs text-own">Click:</span> {step.action}
                      {step.tab && ["zoho", "teams", "scheduler"].includes(step.tab) && onGoToTab && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            onGoToTab(step.tab as "zoho" | "teams" | "scheduler");
                          }}
                          className="ml-2 text-xs text-own underline"
                        >
                          Go to tab
                        </button>
                      )}
                    </div>
                    <div className="mt-1 text-ink-soft">
                      <span className="font-mono text-xs">Say:</span> {step.say}
                    </div>
                    <div className="mt-1 text-ink-soft">
                      <span className="font-mono text-xs">Expect:</span> {step.expect}
                    </div>
                  </div>
                </label>
              </li>
            ))}
          </ol>
          <button
            type="button"
            onClick={resetChecklist}
            className="text-xs font-mono text-ink-soft border border-hairline px-3 py-1 rounded hover:bg-paper"
          >
            Reset checklist
          </button>
        </div>
      )}
    </section>
  );
}
