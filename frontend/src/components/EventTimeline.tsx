import { type RuntimeEvent } from "../services/api";
import { formatIstTime } from "../utils/datetime";

export function EventTimeline({ events }: { events: RuntimeEvent[] }) {
  if (!events.length) {
    return <p className="text-ink-soft text-sm">No events yet.</p>;
  }

  return (
    <div className="space-y-2 max-h-64 overflow-y-auto">
      {events.map((e) => (
        <div key={e.event_id} className="flex gap-3 text-sm border-b border-hairline pb-2">
          <span className="font-mono text-xs text-ink-soft whitespace-nowrap">
            {formatIstTime(e.timestamp)}
          </span>
          <span className={`font-mono text-xs uppercase ${e.status === "FAILED" ? "text-invariant font-semibold" : "text-own"}`}>
            {e.stage}
          </span>
          <span>{e.action.replace(/_/g, " ")}</span>
          {e.message && <span className="text-ink-soft truncate">— {e.message}</span>}
        </div>
      ))}
    </div>
  );
}
