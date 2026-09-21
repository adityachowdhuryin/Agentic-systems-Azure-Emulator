import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { EventTimeline } from "../components/EventTimeline";
import { InboundMailPanel } from "../components/InboundMailPanel";
import { InboundTeamsPanel } from "../components/InboundTeamsPanel";
import { PipelineAnimation } from "../components/PipelineAnimation";
import { StatusBadge } from "../components/StatusBadge";
import { getPollingInterval, usePolling } from "../hooks/usePolling";
import { fetchRun, fetchRunEvents, fetchRunInboundMail, fetchRunInboundTeams } from "../services/api";
import { formatIst } from "../utils/datetime";

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>();

  const fetchRunStable = useCallback(() => fetchRun(runId!), [runId]);
  const fetchEventsStable = useCallback(() => fetchRunEvents(runId!), [runId]);
  const fetchMailStable = useCallback(() => fetchRunInboundMail(runId!), [runId]);
  const fetchTeamsStable = useCallback(() => fetchRunInboundTeams(runId!), [runId]);

  const { data: run } = usePolling(fetchRunStable, [runId], 3000, !!runId);
  const pollInterval = getPollingInterval(run?.state);
  const { data: events } = usePolling(fetchEventsStable, [runId], pollInterval, !!runId);
  const { data: inboundMail } = usePolling(fetchMailStable, [runId], pollInterval, !!runId);
  const { data: inboundTeams } = usePolling(fetchTeamsStable, [runId], pollInterval, !!runId);

  if (!runId) return null;

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <Link to="/" className="text-own text-sm font-mono">← Dashboard</Link>
      <h1 className="font-display text-2xl font-bold mt-4">Run Detail</h1>

      {run && (
        <div className="bg-white border border-hairline rounded-md p-6 mt-4 grid md:grid-cols-2 gap-4 font-mono text-sm">
          <div>Run ID: {run.run_id}</div>
          <div>Lead ID: {run.lead_id}</div>
          <div>Tenant: {run.tenant_id}</div>
          <div>Source: {run.source}</div>
          <div>Trigger: {run.trigger_type}</div>
          <div>Owner: {run.owner}</div>
          <div>State: <StatusBadge status={run.state} /></div>
          <div>Correlation: {run.correlation_id}</div>
          <div>Created: {formatIst(run.created_at)}</div>
        </div>
      )}

      {inboundMail && (
        <div className="mt-6">
          <InboundMailPanel mail={inboundMail} />
        </div>
      )}

      {inboundTeams && (
        <div className="mt-6">
          <InboundTeamsPanel message={inboundTeams} />
        </div>
      )}

      <div className="bg-white border border-hairline rounded-md p-6 mt-6">
        <h2 className="font-display font-semibold mb-4">Band A Pipeline</h2>
        <PipelineAnimation events={events || []} />
      </div>

      <div className="bg-white border border-hairline rounded-md p-6 mt-6">
        <h2 className="font-display font-semibold mb-4">Event Timeline</h2>
        <EventTimeline events={events || []} />
      </div>
    </div>
  );
}
