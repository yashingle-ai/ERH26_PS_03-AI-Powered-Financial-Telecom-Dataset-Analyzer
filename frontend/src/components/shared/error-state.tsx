import { AlertTriangle, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ErrorState({
  message = "Something went wrong",
  onRetry,
  className = "",
}: {
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-[color:var(--risk-high)]/40 bg-[color:var(--risk-high)]/10 p-4 ${className}`}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--risk-high)]" />
        <div className="min-w-0 flex-1">
          <div className="text-sm text-[color:var(--risk-high)]">{message}</div>
          {onRetry && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onRetry}
              className="mt-2 gap-1.5 text-mono text-[11px] uppercase tracking-widest text-[color:var(--risk-high)] hover:bg-[color:var(--risk-high)]/10"
            >
              <RefreshCcw className="h-3 w-3" /> Retry
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
