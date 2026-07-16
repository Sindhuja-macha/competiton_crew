import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  ClipboardList, Search, RefreshCw, Loader2,
  AlertTriangle, Info, Bug, AlertCircle, ZapOff,
  ChevronLeft, ChevronRight, ChevronDown, ChevronUp,
} from "lucide-react";

import { logsApi } from "@/api/client";
import { Button }  from "@/components/ui/button";
import { Input }   from "@/components/ui/input";
import { Badge }   from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn }      from "@/lib/utils";

// ── Helpers ───────────────────────────────────────────────────────────────────
const LEVEL_CONFIG = {
  DEBUG:    { variant: "secondary", icon: Bug,           color: "text-slate-400" },
  INFO:     { variant: "info",      icon: Info,          color: "text-blue-400"  },
  WARNING:  { variant: "warning",   icon: AlertTriangle, color: "text-yellow-400"},
  ERROR:    { variant: "error",     icon: AlertCircle,   color: "text-red-400"   },
  CRITICAL: { variant: "error",     icon: ZapOff,        color: "text-red-500"   },
};

const AGENT_COLORS = {
  orchestrator: "text-purple-400",
  planner:      "text-blue-400",
  research:     "text-cyan-400",
  news:         "text-emerald-400",
  analyst:      "text-yellow-400",
  writer:       "text-orange-400",
  approval:     "text-pink-400",
};

function levelConfig(level) {
  return LEVEL_CONFIG[level?.toUpperCase()] ?? LEVEL_CONFIG.INFO;
}

// ── Log Row ───────────────────────────────────────────────────────────────────
function LogRow({ log, index }) {
  const [expanded, setExpanded] = useState(false);
  const { icon: Icon, color, variant } = levelConfig(log.level);
  const hasDetails = log.details && Object.keys(log.details).length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 3 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.02 }}
      className="border-b border-border/30 last:border-0"
    >
      <div
        className={cn(
          "flex items-start gap-3 px-4 py-3 hover:bg-white/[0.02] transition-colors",
          hasDetails && "cursor-pointer"
        )}
        onClick={() => hasDetails && setExpanded(e => !e)}
      >
        {/* Level icon */}
        <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-md mt-0.5", color, "bg-current/10")}>
          <Icon className={cn("h-3.5 w-3.5", color)} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={variant} className="text-[10px] px-1.5 py-0">{log.level}</Badge>
            {log.agent_name && (
              <span className={cn("text-[11px] font-semibold", AGENT_COLORS[log.agent_name] ?? "text-muted-foreground")}>
                [{log.agent_name}]
              </span>
            )}
            <span className="text-xs text-foreground/80 flex-1">{log.message}</span>
          </div>
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground/60">
            <span>{new Date(log.created_at).toLocaleString()}</span>
            {log.report_id && (
              <span className="font-mono">report:{log.report_id.slice(0, 8)}…</span>
            )}
          </div>
        </div>

        {/* Expand toggle */}
        {hasDetails && (
          <div className="shrink-0 text-muted-foreground">
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </div>
        )}
      </div>

      {/* Details expansion */}
      {expanded && hasDetails && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="px-4 pb-3 pl-14"
        >
          <pre className="text-[11px] text-muted-foreground bg-muted/30 rounded-lg p-3 overflow-x-auto font-mono whitespace-pre-wrap">
            {JSON.stringify(log.details, null, 2)}
          </pre>
        </motion.div>
      )}
    </motion.div>
  );
}

// ── Main Audit Logs Page ──────────────────────────────────────────────────────
export default function AuditLogs() {
  const [logs, setLogs]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [levelFilter, setLevelFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [page, setPage]         = useState(1);
  const [meta, setMeta]         = useState({ total: 0, pages: 1 });

  const PAGE_SIZE = 50;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (levelFilter) params.level = levelFilter;
      if (agentFilter) params.agent_name = agentFilter;
      const data = await logsApi.list(params);
      setLogs(data.items ?? []);
      setMeta({ total: data.total, pages: data.pages });
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [page, levelFilter, agentFilter]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  // Client-side text filter
  const filtered = logs.filter(l => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      l.message.toLowerCase().includes(q) ||
      (l.agent_name ?? "").toLowerCase().includes(q) ||
      (l.report_id ?? "").toLowerCase().includes(q)
    );
  });

  // Level counts for the summary row
  const levelCounts = logs.reduce((acc, l) => {
    acc[l.level] = (acc[l.level] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6 animate-fade-in">
      {/* ── Level summary badges ─────────────────────────────────── */}
      <div className="flex flex-wrap gap-2">
        {Object.entries(LEVEL_CONFIG).map(([level, { variant, icon: Icon }]) => (
          <button
            key={level}
            onClick={() => { setLevelFilter(l => l === level ? "" : level); setPage(1); }}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium border transition-all",
              levelFilter === level
                ? "bg-primary/20 border-primary/40 text-primary"
                : "glass glass-hover border-border/50"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {level}
            <span className="ml-1 opacity-70">({levelCounts[level] ?? 0})</span>
          </button>
        ))}
      </div>

      {/* ── Toolbar ─────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search messages…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <select
            value={agentFilter}
            onChange={e => { setAgentFilter(e.target.value); setPage(1); }}
            className="h-10 rounded-lg border border-border bg-muted/50 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">All Agents</option>
            {["orchestrator","planner","research","news","analyst","writer","approval"].map(a => (
              <option key={a} value={a}>{a.charAt(0).toUpperCase() + a.slice(1)}</option>
            ))}
          </select>
        </div>
        <Button variant="outline" size="sm" onClick={() => { setPage(1); fetchLogs(); }} className="gap-2 shrink-0">
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {/* ── Log table ───────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-primary" />
            Audit Log
          </CardTitle>
          <CardDescription>
            {meta.total} total entries · Page {page} of {meta.pages}
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-center">
              <ClipboardList className="h-10 w-10 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">No log entries found</p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                {search || levelFilter || agentFilter
                  ? "Try adjusting the filters"
                  : "Logs will appear here when agents run"}
              </p>
            </div>
          ) : (
            <ScrollArea className="max-h-[600px]">
              <div className="divide-y divide-transparent">
                {filtered.map((log, i) => (
                  <LogRow key={log.id} log={log} index={i} />
                ))}
              </div>
            </ScrollArea>
          )}

          {/* Pagination */}
          {meta.pages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-border/50">
              <p className="text-xs text-muted-foreground">
                {meta.total} total entries
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline" size="sm"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1 || loading}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-xs text-muted-foreground px-2">
                  {page} / {meta.pages}
                </span>
                <Button
                  variant="outline" size="sm"
                  onClick={() => setPage(p => Math.min(meta.pages, p + 1))}
                  disabled={page >= meta.pages || loading}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
