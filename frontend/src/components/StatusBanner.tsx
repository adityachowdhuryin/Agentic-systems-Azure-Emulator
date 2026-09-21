import { useEffect } from "react";

export type BannerType = "success" | "error" | "info";

interface StatusBannerProps {
  message: string;
  type: BannerType;
  onDismiss?: () => void;
  autoDismissMs?: number;
}

const styles: Record<BannerType, string> = {
  success: "bg-own-tint border-own text-own",
  error: "bg-invariant-tint border-invariant text-invariant",
  info: "bg-white border-hairline text-ink-soft",
};

export function StatusBanner({ message, type, onDismiss, autoDismissMs }: StatusBannerProps) {
  useEffect(() => {
    if (!onDismiss || !autoDismissMs || type === "error") return;
    const id = setTimeout(onDismiss, autoDismissMs);
    return () => clearTimeout(id);
  }, [message, type, onDismiss, autoDismissMs]);

  if (!message) return null;

  return (
    <div className={`border rounded-md px-4 py-3 mb-4 font-mono text-sm flex justify-between items-start gap-4 ${styles[type]}`}>
      <span>{message}</span>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="text-xs opacity-70 hover:opacity-100 shrink-0">
          Dismiss
        </button>
      )}
    </div>
  );
}
