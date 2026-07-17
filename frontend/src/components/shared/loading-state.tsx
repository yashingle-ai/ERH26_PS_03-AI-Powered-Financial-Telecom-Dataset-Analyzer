import { Loader2 } from "lucide-react";

export function LoadingState({
  message = "Loading…",
  className = "",
}: {
  message?: string;
  className?: string;
}) {
  return (
    <div
      className={`flex min-h-[40vh] items-center justify-center gap-2 text-muted-foreground ${className}`}
    >
      <Loader2 className="h-5 w-5 animate-spin" />
      {message}
    </div>
  );
}
