import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { CaseTopbar } from "@/components/case-topbar";
import { InvestigationProvider } from "@/lib/investigation-context";
import { CommandPalette } from "@/components/command-palette";
import { InvestigationBar } from "@/components/investigation-bar";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import { isAuthenticated } from "@/lib/auth";

export const Route = createFileRoute("/_app")({
  beforeLoad: () => {
    if (typeof window !== "undefined" && !isAuthenticated()) {
      throw redirect({ to: "/login" });
    }
  },
  component: AppLayout,
});

function AppLayout() {
  useKeyboardShortcuts();

  return (
    <InvestigationProvider>
      <SidebarProvider defaultOpen>
        <div className="flex min-h-screen w-full">
          <AppSidebar />
          <SidebarInset className="flex min-w-0 flex-1 flex-col bg-transparent">
            <CaseTopbar />
            <main className="flex-1 animate-fade-up px-6 py-6">
              <Outlet />
            </main>
          </SidebarInset>
        </div>
        <CommandPalette />
        <InvestigationBar />
      </SidebarProvider>
    </InvestigationProvider>
  );
}
