import { type InboundTeams } from "../services/api";
import { formatIst } from "../utils/datetime";

export function InboundTeamsPanel({ message }: { message: InboundTeams }) {
  return (
    <section className="bg-white border border-hairline rounded-md p-4">
      <h2 className="font-display font-semibold mb-3">Received Message (Teams)</h2>
      <dl className="grid md:grid-cols-2 gap-x-6 gap-y-2 font-mono text-sm mb-4">
        <div>
          <dt className="text-ink-soft text-xs uppercase">From</dt>
          <dd className="break-all">{message.teams_from || "—"}</dd>
        </div>
        <div>
          <dt className="text-ink-soft text-xs uppercase">Channel</dt>
          <dd className="break-all">{message.teams_channel || "—"}</dd>
        </div>
        <div>
          <dt className="text-ink-soft text-xs uppercase">Conversation</dt>
          <dd className="break-all text-xs">{message.conversation_id || "—"}</dd>
        </div>
        <div>
          <dt className="text-ink-soft text-xs uppercase">Received</dt>
          <dd>{message.received_at ? formatIst(message.received_at) : "—"}</dd>
        </div>
      </dl>
      <div className="border border-hairline rounded-md bg-paper p-3 max-h-72 overflow-y-auto">
        <pre className="text-sm whitespace-pre-wrap font-sans">{message.teams_text || "(empty message)"}</pre>
      </div>
    </section>
  );
}
