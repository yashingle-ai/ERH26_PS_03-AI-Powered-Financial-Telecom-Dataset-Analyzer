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
        {/* Visually hidden until focused. Without it a keyboard user tabs through
            the whole sidebar — 10 nav links plus the dataset and window controls —
            on every page load before reaching the content. */}
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <div className="flex min-h-screen w-full">
          <AppSidebar />
          <SidebarInset className="flex min-w-0 flex-1 flex-col bg-transparent">
            <CaseTopbar />
            {/* tabIndex={-1} so the skip link can move focus here, not just scroll.
                Scrolling alone leaves the next Tab back at the top of the sidebar. */}
            <main id="main-content" tabIndex={-1} className="flex-1 animate-fade-up px-6 py-6">
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
