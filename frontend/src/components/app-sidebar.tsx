import { Link, useRouterState } from "@tanstack/react-router";
import {
  FolderSearch,
  Upload,
  LayoutDashboard,
  Clock,
  Share2,
  Users,
  ShieldAlert,
  FileText,
  Settings,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";

const nav = [
  { section: "Case", items: [
    { title: "Investigations", url: "/investigations", icon: FolderSearch },
    { title: "Overview", url: "/overview", icon: LayoutDashboard },
    { title: "Upload & Ingest", url: "/upload", icon: Upload },
  ]},
  { section: "Analysis", items: [
    { title: "Timeline", url: "/timeline", icon: Clock },
    { title: "Network graph", url: "/network", icon: Share2 },
    { title: "Entities", url: "/entities", icon: Users },
    { title: "Detections", url: "/detections", icon: ShieldAlert },
  ]},
  { section: "Output", items: [
    { title: "Reports", url: "/reports", icon: FileText },
    { title: "Settings", url: "/settings", icon: Settings },
  ]},
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const pathname = useRouterState({ select: (r) => r.location.pathname });

  return (
    <Sidebar collapsible="icon" className="border-r">
      <SidebarHeader className="border-b border-sidebar-border">
        <Link to="/investigations" className="flex items-center gap-2.5 px-2 py-2">
          <div className="relative flex h-8 w-8 items-center justify-center rounded bg-primary/15 ring-1 ring-primary/40">
            <span className="text-mono text-sm font-bold text-primary">ई</span>
            <span className="pulse-ring absolute inset-0 rounded" aria-hidden />
          </div>
          {!collapsed && (
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-wide">ERakshak</div>
              <div className="text-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Forensic Intel · v1.4
              </div>
            </div>
          )}
        </Link>
      </SidebarHeader>

      <SidebarContent>
        {nav.map((group) => (
          <SidebarGroup key={group.section}>
            <SidebarGroupLabel className="text-mono text-[10px] uppercase tracking-[0.2em]">
              {group.section}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const active = pathname === item.url;
                  return (
                    <SidebarMenuItem key={item.title}>
                      <SidebarMenuButton asChild isActive={active} tooltip={item.title}>
                        <Link to={item.url} className="flex items-center gap-2">
                          <item.icon className="h-4 w-4" />
                          <span>{item.title}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border">
        {!collapsed ? (
          <div className="px-2 py-2 text-mono text-[10px] leading-relaxed text-muted-foreground">
            <div>TZ · Asia/Kolkata</div>
            <div>Window W = 10m · Deterministic fusion</div>
          </div>
        ) : (
          <div className="px-2 py-2 text-mono text-[10px] text-muted-foreground">IST</div>
        )}
      </SidebarFooter>
    </Sidebar>
  );
}
