export function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ADMITTED: "bg-own-tint text-own",
    QUEUED: "bg-blue-50 text-blue-800",
    HANDED_OFF: "bg-ink text-white",
    REVIEWING: "bg-blue-50 text-blue-800",
    FINDING_READY: "bg-ink text-white",
    REJECTED: "bg-invariant-tint text-invariant",
    FAILED: "bg-invariant-tint text-invariant",
    SUSPENDED: "bg-yellow-50 text-yellow-800",
    DISPATCHED: "bg-own-tint text-own",
  };
  return (
    <span className={`font-mono text-xs px-2 py-0.5 rounded-full ${colors[status] || "bg-gray-100 text-gray-700"}`}>
      {status}
    </span>
  );
}
