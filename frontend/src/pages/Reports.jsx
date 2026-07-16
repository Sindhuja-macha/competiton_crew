import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText, Search, RefreshCw, Trash2, Eye,
  ChevronRight, Clock, CheckCircle2, XCircle, Loader2,
  TrendingUp, TrendingDown, Target, Shield, ExternalLink,
  X, Newspaper, Lightbulb, BarChart3, BookOpen,
  ShieldCheck, ShieldAlert, FileCheck, AlertTriangle,
  Download, DollarSign,
} from "lucide-react";

import { reportsApi } from "@/api/client";
import { Button }      from "@/components/ui/button";
import { Input }       from "@/components/ui/input";
import { Badge }       from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ScrollArea }  from "@/components/ui/scroll-area";
import { Separator }   from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn }          from "@/lib/utils";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function statusVariant(s) {
  return { pending: "pending", running: "running", completed: "completed", failed: "failed" }[s] ?? "secondary";
}
function statusIcon(s) {
  return {
    pending:   <Clock className="h-3.5 w-3.5" />,
    running:   <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    completed: <CheckCircle2 className="h-3.5 w-3.5" />,
    failed:    <XCircle className="h-3.5 w-3.5" />,
  }[s] ?? <Clock className="h-3.5 w-3.5" />;
}

const SWOT_CONFIG = [
  { key: "strengths",     label: "Strengths",     icon: TrendingUp,   cls: "swot-strengths",     iconCls: "text-emerald-400" },
  { key: "weaknesses",    label: "Weaknesses",    icon: TrendingDown, cls: "swot-weaknesses",    iconCls: "text-red-400"     },
  { key: "opportunities", label: "Opportunities", icon: Target,       cls: "swot-opportunities", iconCls: "text-blue-400"    },
  { key: "threats",       label: "Threats",       icon: Shield,       cls: "swot-threats",       iconCls: "text-yellow-400"  },
];

// ── Markdown renderer — converts [Read Source](url) into clickable links ─────
// Replaces raw whitespace-pre-wrap which shows URLs as plain clipped text.
function MarkdownRenderer({ content }) {
  if (!content) return null;
  return (
    <div className="prose prose-sm prose-invert max-w-none break-words overflow-x-hidden
                    [&_a]:text-primary [&_a]:underline [&_a:hover]:opacity-80
                    [&_p]:text-foreground/80 [&_p]:leading-relaxed [&_p]:mb-2
                    [&_ul]:space-y-1 [&_li]:text-foreground/80 [&_li]:text-sm
                    [&_strong]:text-foreground [&_h1]:text-base [&_h2]:text-sm
                    [&_code]:bg-muted [&_code]:px-1 [&_code]:rounded">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Open all links in new tab safely
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer"
               className="text-primary underline hover:opacity-80 break-all">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ── Governance Panel ─────────────────────────────────────────────────────────
function GovernancePanel({ report }) {
  const dropped    = report.uncited_claims_dropped?.length ?? 0;
  const adversarial = report.adversarial_flags?.length ?? 0;
  const verified   = report.fact_check_passed ?? 0;
  const single     = report.fact_check_failed ?? 0;
  const kept       = report.cited_claims?.length ?? 0;
  const total      = kept + dropped;
  const pctCited   = total > 0 ? Math.round((kept / total) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: "Claims kept",      value: kept,       color: "text-emerald-400" },
          { label: "Uncited dropped",  value: dropped,    color: dropped > 0 ? "text-orange-400" : "text-muted-foreground" },
          { label: "Fact-checked ✓",   value: verified,   color: "text-blue-400" },
          { label: "Single-source",    value: single,     color: "text-yellow-400" },
          { label: "Adversarial flags",value: adversarial,color: adversarial > 0 ? "text-red-400" : "text-muted-foreground" },
          { label: "% claims cited",   value: `${pctCited}%`, color: pctCited === 100 ? "text-emerald-400" : "text-yellow-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="p-2 rounded-lg bg-muted/30 border border-border/50">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={cn("text-lg font-bold", color)}>{value}</p>
          </div>
        ))}
      </div>

      {/* Peer review result */}
      <div className={cn(
        "flex items-start gap-2 p-3 rounded-lg border text-sm",
        report.peer_review_passed
          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
          : "bg-yellow-500/10 border-yellow-500/30 text-yellow-400"
      )}>
        {report.peer_review_passed
          ? <ShieldCheck className="h-4 w-4 shrink-0 mt-0.5" />
          : <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />}
        <div>
          <p className="font-medium">{report.peer_review_passed ? "Peer review passed" : "Peer review issues"}</p>
          {report.peer_review_note && (
            <p className="text-xs opacity-80 mt-0.5">{report.peer_review_note}</p>
          )}
          {report.peer_review_issues?.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {report.peer_review_issues.map((iss, i) => (
                <li key={i} className="text-xs opacity-80">• {iss}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Budget usage */}
      {report.run_metadata?.budget && (
        <div className="p-3 rounded-lg bg-muted/20 border border-border/50 text-xs space-y-1">
          <p className="font-semibold text-muted-foreground uppercase tracking-wider mb-2">Budget Usage</p>
          {[
            ["Sources attempted", report.run_metadata.budget.sources_attempted, report.run_metadata.budget.max_sources],
            ["Steps used",        report.run_metadata.budget.steps_used,        report.run_metadata.budget.max_steps],
          ].map(([label, used, max]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-muted-foreground">{label}</span>
              <span className={cn("font-medium", used >= max ? "text-red-400" : "text-foreground")}>
                {used ?? "–"} / {max ?? "–"}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Failed sources */}
      {report.run_metadata?.failed_sources?.length > 0 && (
        <div className="p-3 rounded-lg bg-orange-500/10 border border-orange-500/30 text-xs">
          <p className="text-orange-400 font-medium mb-1 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" /> Unreachable sources (skipped)
          </p>
          {report.run_metadata.failed_sources.map((url, i) => (
            <p key={i} className="text-orange-300/70 truncate">• {url}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Briefing Section display ─────────────────────────────────────────────────
function BriefingSectionBlock({ section }) {
  if (!section?.content) return <p className="text-sm text-muted-foreground">Not available.</p>;
  return (
    <div className="space-y-3 w-full overflow-x-hidden">
      <div className="break-words overflow-x-hidden">
        <MarkdownRenderer content={section.content} />
      </div>
      {section.cited_claims?.length > 0 && (
        <details className="group">
          <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground transition-colors list-none flex items-center gap-1">
            <FileCheck className="h-3 w-3" />
            {section.cited_claims.length} cited claim{section.cited_claims.length !== 1 ? "s" : ""}
            <ChevronRight className="h-3 w-3 group-open:rotate-90 transition-transform" />
          </summary>
          <ul className="mt-2 space-y-1.5 pl-4">
            {section.cited_claims.map((c, i) => (
              <li key={i} className="text-xs text-foreground/70 break-words">
                <span className={cn(
                  "inline-block w-2 h-2 rounded-full mr-1.5",
                  c.verified ? "bg-emerald-400" : "bg-yellow-400"
                )} />
                {c.claim}
                {c.source_url && (
                  <a href={c.source_url} target="_blank" rel="noopener noreferrer"
                    className="ml-1.5 text-primary hover:underline break-all">
                    [{c.source_title || "source"}]
                  </a>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}


// ── Report Detail slide-over ─────────────────────────────────────────────────
function ReportDetail({ report, onClose }) {
  const [full, setFull]     = useState(report);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!report?.id) return;
    setLoading(true);
    reportsApi.get(report.id).then(setFull).catch(() => {}).finally(() => setLoading(false));
  }, [report?.id]);

  const topicDisplay = full.topic || full.competitor_name || "Unknown";

  return (
    <motion.div
      initial={{ x: "100%", opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: "100%", opacity: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="fixed top-0 right-0 h-screen w-full max-w-2xl z-50 glass border-l border-border/50 flex flex-col overflow-x-hidden"
    >
      {/* Header */}
      <div className="flex items-start justify-between p-6 border-b border-border/50 shrink-0">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold truncate">{topicDisplay}</h2>
          <p className="text-sm text-muted-foreground">{full.industry} · {full.region}</p>
          {full.competitor_name && full.competitor_name !== full.topic && (
            <p className="text-xs text-muted-foreground mt-0.5">Competitor: {full.competitor_name}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-3">
          <Badge variant={statusVariant(full.status)}>
            {statusIcon(full.status)}
            <span className="ml-1">{full.status}</span>
          </Badge>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : (
        <ScrollArea className="flex-1 overflow-x-hidden">
          <div className="p-6 space-y-6 w-full overflow-x-hidden break-words">
            <Tabs defaultValue="briefing">
              <TabsList className="w-full grid grid-cols-6">
                <TabsTrigger value="briefing">Briefing</TabsTrigger>
                <TabsTrigger value="pricing">Pricing</TabsTrigger>
                <TabsTrigger value="swot">SWOT</TabsTrigger>
                <TabsTrigger value="governance">Governance</TabsTrigger>
                <TabsTrigger value="news">News</TabsTrigger>
                <TabsTrigger value="sources">Sources</TabsTrigger>
              </TabsList>

              {/* ── Briefing tab: 3 required sections ── */}
              <TabsContent value="briefing" className="space-y-5 mt-4">
                {full.status !== "completed" ? (
                  <p className="text-sm text-muted-foreground">Briefing not yet generated.</p>
                ) : (
                  <>
                    {/* Section 1 */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm font-semibold">
                        <BookOpen className="h-4 w-4 text-primary" />
                        {full.briefing_section_pricing?.title || "Competitor Pricing & Product Moves"}
                      </div>
                      <BriefingSectionBlock section={full.briefing_section_pricing} />
                    </div>
                    <Separator />
                    {/* Section 2 */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm font-semibold">
                        <BarChart3 className="h-4 w-4 text-primary" />
                        {full.briefing_section_market?.title || "Market Signals & Trends"}
                      </div>
                      <BriefingSectionBlock section={full.briefing_section_market} />
                    </div>
                    <Separator />
                    {/* Section 3 */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm font-semibold">
                        <Lightbulb className="h-4 w-4 text-primary" />
                        {full.briefing_section_exec?.title || "Executive Summary & Recommendation"}
                      </div>
                      <BriefingSectionBlock section={full.briefing_section_exec} />
                    </div>

                    {/* Metadata footer */}
                    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground pt-2">
                      <span>Created: {new Date(full.created_at).toLocaleString()}</span>
                      {full.duration_seconds && (
                        <span>Duration: {full.duration_seconds.toFixed(1)}s</span>
                      )}
                      {full.sources_succeeded != null && (
                        <span>Sources used: {full.sources_succeeded}</span>
                      )}
                    </div>

                    {/* Export buttons */}
                    <div className="flex gap-2 flex-wrap pt-1">
                      <a href={`${BASE_URL}/api/v1/reports/${full.id}/export/pdf`} target="_blank" rel="noopener noreferrer">
                        <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                          <Download className="h-3.5 w-3.5" /> PDF
                        </Button>
                      </a>
                      <a href={`${BASE_URL}/api/v1/reports/${full.id}/export/markdown`} target="_blank" rel="noopener noreferrer">
                        <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                          <Download className="h-3.5 w-3.5" /> Markdown
                        </Button>
                      </a>
                    </div>
                  </>
                )}
              </TabsContent>

              {/* ── Pricing Analysis tab ── */}
              <TabsContent value="pricing" className="mt-4 space-y-4 w-full overflow-x-hidden">
                {full.status !== "completed" ? (
                  <p className="text-sm text-muted-foreground">Pricing data not yet available.</p>
                ) : (
                  <>
                    {/* Pricing section from writer briefing */}
                    {full.briefing_section_pricing?.content && (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm font-semibold">
                          <DollarSign className="h-4 w-4 text-primary" />
                          Competitor Pricing & Product Moves
                        </div>
                        <div className="break-words overflow-x-hidden w-full">
                          <MarkdownRenderer content={full.briefing_section_pricing.content} />
                        </div>
                      </div>
                    )}
                    {/* Raw pricing summary from research */}
                    {full.pricing_summary && (
                      <>
                        {full.briefing_section_pricing?.content && (
                          <div className="border-t border-border/40 pt-4" />
                        )}
                        <div className="space-y-2">
                          <div className="flex items-center gap-2 text-sm font-semibold">
                            <BarChart3 className="h-4 w-4 text-primary" />
                            Raw Pricing Intelligence
                          </div>
                          <div className="break-words overflow-x-hidden w-full p-3 rounded-lg bg-muted/20 border border-border/40">
                            <MarkdownRenderer content={full.pricing_summary} />
                          </div>
                        </div>
                      </>
                    )}
                    {!full.briefing_section_pricing?.content && !full.pricing_summary && (
                      <p className="text-sm text-muted-foreground">
                        No pricing data was captured for this run. Try a more specific topic or competitor.
                      </p>
                    )}
                  </>
                )}
              </TabsContent>

              {/* ── Governance tab ── */}
              <TabsContent value="governance" className="mt-4">
                {full.status === "completed"
                  ? <GovernancePanel report={full} />
                  : <p className="text-sm text-muted-foreground">Governance data not yet available.</p>
                }
              </TabsContent>

              {/* ── SWOT tab ── */}
              <TabsContent value="swot" className="mt-4">
                {full.swot_analysis ? (
                  <div className="grid grid-cols-2 gap-3">
                    {SWOT_CONFIG.map(({ key, label, icon: Icon, cls, iconCls }) => (
                      <div key={key} className={cn("rounded-lg border p-3", cls)}>
                        <div className="flex items-center gap-2 mb-2">
                          <Icon className={cn("h-3.5 w-3.5", iconCls)} />
                          <span className="text-xs font-semibold uppercase tracking-wider">{label}</span>
                        </div>
                        <ul className="space-y-1">
                          {(full.swot_analysis[key] || []).map((item, i) => (
                            <li key={i} className="text-xs text-foreground/70 flex items-start gap-1.5 break-words overflow-x-hidden">
                              <ChevronRight className="h-3 w-3 shrink-0 mt-0.5 opacity-50" />
                              <span className="break-words overflow-x-hidden">
                                <MarkdownRenderer content={item} />
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No SWOT data available.</p>
                )}
              </TabsContent>

              {/* ── News tab ── */}
              <TabsContent value="news" className="mt-4 space-y-3">
                {full.latest_news?.length > 0 ? full.latest_news.map((item, i) => (
                  <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                    className="glass glass-hover rounded-lg p-3 block group">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium group-hover:text-primary transition-colors">{item.title}</p>
                      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground group-hover:text-primary" />
                    </div>
                    <div className="flex items-center gap-2 mt-1.5">
                      <Badge variant="info" className="text-[10px]">{item.source}</Badge>
                      {item.published_at && (
                        <span className="text-[10px] text-muted-foreground">{new Date(item.published_at).toLocaleDateString()}</span>
                      )}
                    </div>
                    {item.summary && <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2">{item.summary}</p>}
                  </a>
                )) : <p className="text-sm text-muted-foreground">No news articles available.</p>}
              </TabsContent>

              {/* ── Sources tab ── */}
              <TabsContent value="sources" className="mt-4 space-y-2">
                {full.sources?.length > 0 ? full.sources.map((s, i) => (
                  <a key={i} href={s.url} target="_blank" rel="noopener noreferrer"
                    className="glass glass-hover rounded-lg p-3 flex items-center gap-3 group block">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                      <ExternalLink className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{s.title}</p>
                      <p className="text-xs text-muted-foreground truncate">{s.url}</p>
                    </div>
                    <Badge variant="secondary" className="text-[10px] shrink-0">{s.source}</Badge>
                  </a>
                )) : <p className="text-sm text-muted-foreground">No sources available.</p>}
              </TabsContent>
            </Tabs>
          </div>
        </ScrollArea>
      )}
    </motion.div>
  );
}


// ── Reports List Page ────────────────────────────────────────────────────────
export default function Reports() {
  const [reports, setReports]           = useState([]);
  const [loading, setLoading]           = useState(true);
  const [search, setSearch]             = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage]                 = useState(1);
  const [meta, setMeta]                 = useState({ total: 0, pages: 1 });
  const [selected, setSelected]         = useState(null);
  const [deleting, setDeleting]         = useState(null);
  const PAGE_SIZE = 10;

  const fetchReports = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (statusFilter) params.status = statusFilter;
      const data = await reportsApi.list(params);
      setReports(data.items ?? []);
      setMeta({ total: data.total, pages: data.pages });
    } catch {
      setReports([]);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => { fetchReports(); }, [fetchReports]);

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this report permanently?")) return;
    setDeleting(id);
    try {
      await reportsApi.delete(id);
      setReports(prev => prev.filter(r => r.id !== id));
      if (selected?.id === id) setSelected(null);
    } catch { /* ignore */ }
    finally { setDeleting(null); }
  };

  const filtered = reports.filter(r => {
    const q = search.toLowerCase();
    return (
      (r.topic || "").toLowerCase().includes(q) ||
      (r.competitor_name || "").toLowerCase().includes(q) ||
      r.industry.toLowerCase().includes(q) ||
      r.region.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search topic, competitor, industry…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <select
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
            className="h-10 rounded-lg border border-border bg-muted/50 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">All Status</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <Button variant="outline" size="sm" onClick={fetchReports} className="gap-2 shrink-0">
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Total",     value: meta.total,                                               variant: "secondary" },
          { label: "Completed", value: reports.filter(r => r.status === "completed").length,     variant: "success"   },
          { label: "Running",   value: reports.filter(r => r.status === "running").length,       variant: "info"      },
          { label: "Failed",    value: reports.filter(r => r.status === "failed").length,        variant: "error"     },
        ].map(({ label, value, variant }) => (
          <Card key={label}>
            <CardContent className="pt-4 pb-4">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="text-2xl font-bold mt-1">
                <Badge variant={variant}>{value}</Badge>
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            Intelligence Briefings
          </CardTitle>
          <CardDescription>{meta.total} briefings total</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-center">
              <FileText className="h-10 w-10 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">No briefings found</p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                {search ? "Try a different search term" : "Run your first intelligence briefing from the Dashboard"}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-border/50">
              {filtered.map((report) => {
                const topicDisplay = report.topic || report.competitor_name || "Unknown";
                return (
                  <motion.div
                    key={report.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex items-center gap-4 px-6 py-4 hover:bg-muted/30 transition-colors group"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium truncate">{topicDisplay}</p>
                        {/* Governance badges */}
                        {report.status === "completed" && (
                          <>
                            {report.peer_review_passed === true && (
                              <span title="Peer review passed" className="text-emerald-400">
                                <ShieldCheck className="h-3.5 w-3.5" />
                              </span>
                            )}
                            {report.peer_review_passed === false && (
                              <span title="Peer review issues" className="text-yellow-400">
                                <ShieldAlert className="h-3.5 w-3.5" />
                              </span>
                            )}
                            {report.fact_check_passed > 0 && (
                              <span className="text-[10px] text-blue-400 flex items-center gap-0.5">
                                <FileCheck className="h-3 w-3" />{report.fact_check_passed}
                              </span>
                            )}
                          </>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {report.industry} · {report.region}
                        {report.competitor_name && report.competitor_name !== report.topic &&
                          ` · ${report.competitor_name}`}
                      </p>
                      <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                        <span>{new Date(report.created_at).toLocaleDateString()}</span>
                        {report.duration_seconds && (
                          <span>{report.duration_seconds.toFixed(1)}s</span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={statusVariant(report.status)} className="shrink-0">
                        {statusIcon(report.status)}
                        <span className="ml-1">{report.status}</span>
                      </Badge>
                      <Button
                        variant="ghost" size="icon-sm"
                        onClick={() => setSelected(report)}
                        title="View details"
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost" size="icon-sm"
                        onClick={() => handleDelete(report.id)}
                        disabled={deleting === report.id}
                        className="text-destructive hover:text-destructive"
                        title="Delete"
                      >
                        {deleting === report.id
                          ? <Loader2 className="h-4 w-4 animate-spin" />
                          : <Trash2 className="h-4 w-4" />}
                      </Button>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {meta.pages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button
            variant="outline" size="sm"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {meta.pages}
          </span>
          <Button
            variant="outline" size="sm"
            onClick={() => setPage(p => Math.min(meta.pages, p + 1))}
            disabled={page === meta.pages}
          >
            Next
          </Button>
        </div>
      )}

      {/* Detail panel overlay */}
      <AnimatePresence>
        {selected && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
              onClick={() => setSelected(null)}
            />
            <ReportDetail report={selected} onClose={() => setSelected(null)} />
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
