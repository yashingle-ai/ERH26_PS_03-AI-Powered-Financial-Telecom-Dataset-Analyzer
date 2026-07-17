import { SidebarTrigger } from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Search, ChevronDown, Bell, LogOut, User, KeyRound } from "lucide-react";

import { Link, useNavigate } from "@tanstack/react-router";
import { useDatasets } from "@/hooks/use-investigation-data";
import { useInvestigation } from "@/lib/investigation-context";
import { clearSession, getUsername } from "@/lib/auth";
import { toast } from "sonner";
import type { ReactNode } from "react";

export function CaseTopbar() {
  const nav = useNavigate();
  const { dataset, setDataset } = useInvestigation();
  const { data } = useDatasets();
  const datasets = data?.datasets || (dataset ? [dataset] : []);
  const username = getUsername() || "analyst";
  const initials = username.slice(0, 2).toUpperCase();

  const signOut = () => {
    clearSession();
    nav({ to: "/login" });
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/70 px-4 backdrop-blur">
      <SidebarTrigger className="text-muted-foreground" />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-2 pl-2 pr-2 hover:bg-accent">
            <span className="text-mono text-[11px] font-medium text-primary">
              {(dataset || "—").toUpperCase()}
            </span>
            <span className="hidden max-w-[280px] truncate text-sm text-foreground md:inline">
              Active dataset
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-[360px]">
          <DropdownMenuLabel className="text-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Switch dataset
          </DropdownMenuLabel>
          {datasets.map((ds) => (
            <DropdownMenuItem
              key={ds}
              onClick={() => {
                setDataset(ds);
                nav({ to: "/overview" });
              }}
              className="flex flex-col items-start gap-0.5 py-2"
            >
              <div className="flex w-full items-center justify-between">
                <span className="text-mono text-[11px] text-primary">{ds.toUpperCase()}</span>
                <span className="text-mono text-[10px] uppercase text-muted-foreground">
                  {ds === dataset ? "active" : "ready"}
                </span>
              </div>
              <span className="line-clamp-1 text-sm">datasets/raw/{ds}</span>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link to="/investigations">All investigations →</Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <button
        onClick={() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }))}
        aria-label="Search entities and pages"
        className="relative ml-2 hidden h-9 items-center gap-2 rounded-md border border-border bg-surface px-3 text-left md:flex max-w-md flex-1"
      >
        <Search className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-mono text-[13px] text-muted-foreground/60">
          Search entities, pages…
        </span>
        <kbd className="text-mono ml-auto rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          ⌘K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="relative h-9 w-9"
          aria-label="Notifications"
          onClick={() => toast.message("No unread notifications", { description: "You are up to date with case activity." })}
        >
          <Bell className="h-4 w-4" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-2" aria-label="User menu">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/20 text-mono text-[11px] text-primary">
                {initials}
              </span>
              <span className="hidden text-left leading-tight md:block">
                <span className="block text-[12px] text-foreground">{username}</span>
                <span className="text-mono block text-[10px] text-muted-foreground">
                  Analyst · API
                </span>
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem onClick={() => toast.message("User profile details coming soon")}><User className="mr-2 h-4 w-4" />Profile</DropdownMenuItem>
            <DropdownMenuItem onClick={() => toast.message("API token management coming soon")}><KeyRound className="mr-2 h-4 w-4" />API tokens</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={signOut}>
              <LogOut className="mr-2 h-4 w-4" />Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="text-mono text-[10px] uppercase tracking-[0.3em] text-primary/80">
          {eyebrow}
        </div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
