import { useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { Bell, Wifi, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { healthApi } from "@/api/client";

const PAGE_TITLES = {
  "/":          { title: "Dashboard",  subtitle: "Monitor and run competitive intelligence workflows" },
  "/reports":   { title: "Reports",    subtitle: "View all generated intelligence reports" },
  "/analytics": { title: "Analytics",  subtitle: "Visual insights and trends" },
  "/logs":      { title: "Audit Logs", subtitle: "Full activity trail for all agent executions" },
  "/settings":  { title: "Settings",   subtitle: "Configure API keys and preferences" },
};

export default function Topbar() {
  const { pathname } = useLocation();
  const [apiStatus, setApiStatus] = useState("checking"); // checking | online | offline
  const page = PAGE_TITLES[pathname] || { title: "Dashboard", subtitle: "" };

  useEffect(() => {
    const check = async () => {
      try {
        await healthApi.check();
        setApiStatus("online");
      } catch {
        setApiStatus("offline");
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <motion.header
      initial={{ y: -10, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className="fixed top-0 right-0 left-64 h-16 z-30 flex items-center justify-between px-6 glass border-b border-border/50"
    >
      {/* ── Page title ──────────────────────────────────────────────── */}
      <div>
        <h1 className="text-base font-semibold text-foreground leading-none">
          {page.title}
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5">{page.subtitle}</p>
      </div>

      {/* ── Right actions ───────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        {/* API status indicator */}
        <div className="flex items-center gap-2 glass rounded-full px-3 py-1.5">
          {apiStatus === "online" ? (
            <>
              <Wifi className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-xs text-emerald-400 font-medium">API Online</span>
            </>
          ) : apiStatus === "offline" ? (
            <>
              <WifiOff className="h-3.5 w-3.5 text-red-400" />
              <span className="text-xs text-red-400 font-medium">API Offline</span>
            </>
          ) : (
            <>
              <div className="h-3.5 w-3.5 rounded-full bg-yellow-400/50 animate-pulse" />
              <span className="text-xs text-yellow-400 font-medium">Checking…</span>
            </>
          )}
        </div>

        {/* Notification bell placeholder */}
        <button className="glass glass-hover h-9 w-9 rounded-lg flex items-center justify-center relative">
          <Bell className="h-4 w-4 text-muted-foreground" />
        </button>

        {/* Avatar */}
        <div className="h-9 w-9 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
          <span className="text-xs font-bold text-primary">CI</span>
        </div>
      </div>
    </motion.header>
  );
}
