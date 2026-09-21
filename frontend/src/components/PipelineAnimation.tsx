import { memo } from "react";
import { type RuntimeEvent } from "../services/api";

const STAGES = [
  { id: "INGRESS", label: "01 Ingress Edge", desc: "The doorway. Accepts the arrival, validates the envelope, stores the raw event, and acknowledges quickly." },
  { id: "ADMISSION", label: "02 Admission Control", desc: "Decides whether this request may proceed and on whose behalf." },
  { id: "RUN_MANAGER", label: "03 Run Manager", desc: "Turns the admitted request into a system-owned run that can be tracked." },
  { id: "DISPATCHER", label: "04 Dispatcher", desc: "Chooses how the run should proceed." },
  { id: "MESSAGE_TRANSPORT", label: "05 Message Transport", desc: "Durably carries asynchronous work to another process." },
];

interface Props {
  events: RuntimeEvent[];
}

function PipelineAnimationInner({ events }: Props) {
  const stageStatus = (stageId: string) => {
    const stageEvents = events.filter((e) => e.stage === stageId);
    if (stageEvents.some((e) => e.status === "FAILED")) return "failed";
    if (stageEvents.length > 0) return "done";
    return "pending";
  };

  const doneCount = STAGES.filter((s) => stageStatus(s.id) === "done").length;
  const packetPos = Math.max(0, doneCount - 1);
  const bandBDone = events.some((e) => e.stage === "BAND_B" && e.action === "handed_off");

  return (
    <div className="relative">
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-6">
        {STAGES.map((stage) => {
          const status = stageStatus(stage.id);
          return (
            <div
              key={stage.id}
              className={`rounded-md border-2 p-3 ${
                status === "done"
                  ? "border-own bg-own-tint"
                  : status === "failed"
                  ? "border-invariant bg-invariant-tint"
                  : "border-hairline bg-white opacity-70"
              }`}
            >
              <div className="font-mono text-xs text-own font-semibold">{stage.label.split(" ")[0]}</div>
              <div className="font-display font-semibold text-sm mt-1">{stage.label.slice(3)}</div>
              <p className="text-xs text-ink-soft mt-2">{stage.desc}</p>
              <div className="mt-2 font-mono text-xs">
                {events
                  .filter((e) => e.stage === stage.id)
                  .map((e) => (
                    <div key={e.event_id} className={e.status === "FAILED" ? "text-invariant" : "text-own"}>
                      ✓ {e.action.replace(/_/g, " ")}
                    </div>
                  ))}
              </div>
            </div>
          );
        })}
      </div>

      {doneCount > 0 && !bandBDone && (
        <div
          className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-own shadow-lg transition-[left] duration-300 ease-out hidden md:block"
          style={{ left: `${Math.min(packetPos, 4) * 20 + 8}%` }}
        />
      )}

      <div
        className={`mt-4 rounded-md border-2 p-4 text-center ${
          bandBDone ? "border-own bg-ink text-white" : "border-dashed border-hairline bg-white"
        }`}
      >
        <div className="font-display font-semibold">BAND B — Reasoning &amp; Action</div>
        <p className={`text-sm mt-1 ${bandBDone ? "text-own-tint" : "text-ink-soft"}`}>
          {bandBDone
            ? "Handed off. Band A does not reason about lead quality."
            : events.some((e) => e.stage === "MESSAGE_TRANSPORT")
              ? "Waiting for async handoff via Message Transport (Worker ON)…"
              : events.some((e) => e.action === "sync_selected")
                ? "Sync path — handing off to Band B without Message Transport…"
                : "Waiting for Dispatcher to choose Sync or Async…"}
        </p>
      </div>
    </div>
  );
}

export const PipelineAnimation = memo(PipelineAnimationInner);
