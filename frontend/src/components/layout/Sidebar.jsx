import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  FileText,
  BarChart3,
  ClipboardList,
  Settings,
  Zap,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";

const navItems = [
  { to: "/",         label: "Dashboard",  icon: LayoutDashboard },
  { to: "/reports",  label: "Reports",    icon: FileText },
  { to: "/analytics",label: "Analytics",  icon: BarChart3 },
  { to: "/logs",     label: "Audit Logs", icon: ClipboardList },
  { to: "/settings", label: "Settings",   icon: Settings },
];

export default function Sidebar() {
  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.3 }}
      className="fixed left-0 top-0 h-screen w-64 z-40 flex flex-col glass border-r border-border/50"
    >
      {/* ── Logo ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-6 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/20 shadow-glow-sm">
          <Zap className="h-5 w-5 text-primary" />
        </div>
        <div>
          <p className="text-sm font-bold leading-none text-foreground">CI Briefing</p>
          <p className="text-xs text-muted-foreground mt-0.5">Intelligence Crew</p>
        </div>
      </div>

      <Separator className="mx-4 w-auto" />

      {/* ── Navigation ────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
          Main Menu
        </p>
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "nav-link group",
                isActive && "active"
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cn("h-4 w-4 shrink-0", isActive ? "text-primary" : "text-muted-foreground")} />
                <span className="flex-1">{label}</span>
                {isActive && (
                  <ChevronRight className="h-3.5 w-3.5 text-primary/60" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── Footer ────────────────────────────────────────────────── */}
      <div className="px-4 py-4 border-t border-border/50">
        <div className="glass rounded-lg p-3 text-center">
          <p className="text-[10px] text-muted-foreground/60 font-medium">
            Powered by LangGraph
          </p>
          <p className="text-[10px] text-muted-foreground/40 mt-0.5">
            v1.0.0
          </p>
        </div>
      </div>
    </motion.aside>
  );
}
