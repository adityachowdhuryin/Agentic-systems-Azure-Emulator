import type { ReactNode } from "react";

interface ActionButtonProps {
  loading?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger";
  className?: string;
  children: ReactNode;
}

export function ActionButton({
  loading = false,
  disabled = false,
  onClick,
  variant = "primary",
  className = "",
  children,
}: ActionButtonProps) {
  const base = "w-full py-2 rounded font-medium text-sm transition-opacity disabled:opacity-50 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-own text-white hover:opacity-90",
    secondary: "border border-own text-own hover:bg-own-tint",
    danger: "border border-invariant text-invariant hover:bg-invariant-tint",
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      className={`${base} ${variants[variant]} ${className}`}
    >
      {loading ? (
        <span className="inline-flex items-center justify-center gap-2">
          <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          Working…
        </span>
      ) : (
        children
      )}
    </button>
  );
}
