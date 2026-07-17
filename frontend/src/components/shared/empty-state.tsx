import { Inbox } from "lucide-react";

export function EmptyState({
  icon: Icon = Inbox,
  title = "No data",
  description = "Nothing to display yet.",
  className = "",
  children,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title?: string;
  description?: string;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={`flex min-h-[24vh] flex-col items-center justify-center gap-3 text-center ${className}`}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-muted/40">
        <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
      <div>
        <div className="text-sm font-medium text-foreground">{title}</div>
        <div className="mt-1 max-w-sm text-[13px] text-muted-foreground">
          {description}
        </div>
      </div>
      {children}
    </div>
  );
}
