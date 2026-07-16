import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, Loader2, CheckCircle2, XCircle, Clock,
  TrendingUp, TrendingDown, Newspaper,
  ExternalLink, AlertTriangle, ChevronRight, Play,
  BarChart3, Lightbulb, Target, Shield, Wifi, WifiOff,
  FileCheck, ShieldCheck, ShieldAlert, BookOpen, Download,
  Settings2,
} from "lucide-react";

import { reportsApi, streamApi } from "@/api/client";
import { Button }      from "@/components/ui/button";
import { Input }       from "@/components/ui/input";
import { Label }       from "@/components/ui/label";
import { Badge }       from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress }    from "@/components/ui/progress";
import { ScrollArea }  from "@/components/ui/scroll-area";
import { Skeleton }    from "@/components/ui/skeleton";
import { cn }          from "@/lib/utils";

// ── Constants ────────────────────────────────────────────────────────────────
const AGENT_STEPS = [
  { key: "planner",     label: "Planner",      desc: "Creating execution plan" },
  { key: "research",    label: "Research",     desc: "Gathering sources & data" },
  { key: "news",        label: "News",         desc: "Fetching latest articles" },
  { key: "analyst",     label: "Analyst",      desc: "Extracting cited intelligence" },
  { key: "fact_check",  label: "Fact-Check",   desc: "Cross-verifying 2+ sources" },
  { key: "writer",      label: "Writer",       desc: "Generating 3-section briefing" },
  { key: "peer_review", label: "Peer Review",  desc: "Quality & citation gate" },
  { key: "approval",    label: "Approval",     desc: "Final sign-off" },
];

const SWOT_CONFIG = [
  { key: "strengths",     label: "Strengths",     icon: TrendingUp,   cls: "swot-strengths",     iconCls: "text-emerald-400" },
  { key: "weaknesses",    label: "Weaknesses",    icon: TrendingDown, cls: "swot-weaknesses",    iconCls: "text-red-400"     },
  { key: "opportunities", label: "Opportunities", icon: Target,       cls: "swot-opportunities", iconCls: "text-blue-400"    },
  { key: "threats",       label: "Threats",       icon: Shield,       cls: "swot-threats",       iconCls: "text-yellow-400"  },
];

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function statusVariant(s) {
  return { pending: "pending", running: "running", completed: "completed", failed: "failed" }[s] ?? "secondary";
}

// ── Small reusable components ────────────────────────────────────────────────
function AgentStepItem({ step, execution, index }) {
  const status = execution?.status ?? "queued";
  const Icon =
    status === "completed" ? CheckCircle2 :
    status === "failed"    ? XCircle      :
    status === "running"   ? Loader2      : Clock;

  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className={cn(
        "flex items-center gap-3 p-3 rounded-lg border transition-all duration-300",
        `agent-step-${status}`
      )}
    >
      <div className="flex h-8 w-8 items-center justify-center rounded-full border border-current/30">
        <Icon className={cn("h-4 w-4", status === "running" && "animate-spin")} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium leading-none">{step.label}</p>
        <p className="text-xs text-muted-foreground mt-0.5 truncate">{step.desc}</p>
      </div>
      {execution?.duration_seconds != null && (
        <span className="text-xs text-muted-foreground shrink-0">
          {execution.duration_seconds.toFixed(1)}s
        </span>
      )}
    </motion.div>
  );
}

function StreamIndicator({ connected }) {
  if (connected === null) return null;
  return (
    <div className={cn(
      "flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border",
      connected
        ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
        : "text-yellow-400 border-yellow-500/30 bg-yellow-500/10"
    )}>
      {connected ? <><Wifi className="h-3 w-3" /> Live</> : <><WifiOff className="h-3 w-3" /> Polling</>}
    </div>
  );
}

function GovernanceBadge({ report }) {
  if (!report || report.status !== "completed") return null;
  const passed = report.peer_review_passed;
  const dropped = report.uncited_claims_dropped?.length ?? 0;
  const adversarial = report.adversarial_flags?.length ?? 0;
  const verified = report.fact_check_passed ?? 0;

  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <span className={cn(
        "flex items-center gap-1 px-2 py-0.5 rounded-full border font-medium",
        passed
          ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
          : "text-yellow-400 border-yellow-500/30 bg-yellow-500/10"
      )}>
        {passed ? <ShieldCheck className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
        Peer {passed ? "Passed" : "Issues"}
      </span>
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-full border text-blue-400 border-blue-500/30 bg-blue-500/10">
        <FileCheck className="h-3 w-3" /> {verified} verified
      </span>
      {dropped > 0 && (
        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full border text-orange-400 border-orange-500/30 bg-orange-500/10">
          <ShieldAlert className="h-3 w-3" /> {dropped} uncited dropped
        </span>
      )}
      {adversarial > 0 && (
        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full border text-red-400 border-red-500/30 bg-red-500/10">
          <AlertTriangle className="h-3 w-3" /> {adversarial} adversarial
        </span>
      )}
    </div>
  );
}

function BriefingSection({ section, index }) {
  if (!section?.content) return null;
  const icons = [BookOpen, BarChart3, Lightbulb];
  const Icon = icons[index] ?? BookOpen;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-4 w-4 text-primary" />
          {section.title}
          {section.cited_claims?.length > 0 && (
            <Badge variant="secondary" className="text-[10px] ml-auto">
              {section.cited_claims.length} claims
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-sm text-foreground/80 leading-relaxed whitespace-pre-wrap">
          {section.content}
        </div>
      </CardContent>
    </Card>
  );
}


// ── Main Dashboard Component ─────────────────────────────────────────────────
export default function Dashboard() {
  const [form, setForm] = useState({
    topic: "",
    competitor_name: "",
    industry: "",
    region: "",
    max_sources: 15,
    max_steps: 50,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [errors, setErrors]         = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [activeReport, setActiveReport] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [progress, setProgress]     = useState(0);
  const [streamConnected, setStreamConnected] = useState(null);
  const [loadingResult, setLoadingResult] = useState(false);

  const esRef   = useRef(null);
  const pollRef = useRef(null);

  const stopStream = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    clearInterval(pollRef.current);
    setStreamConnected(null);
  }, []);

  useEffect(() => () => stopStream(), [stopStream]);

  const calcProgress = (execs) => {
    if (!execs?.length) return 0;
    const done = execs.filter(e => e.status === "completed" || e.status === "failed").length;
    return Math.round((done / AGENT_STEPS.length) * 100);
  };

  const fetchFullReport = useCallback(async (id) => {
    setLoadingResult(true);
    try {
      const full = await reportsApi.get(id);
      setActiveReport(full);
    } catch { /* ignore */ }
    finally { setLoadingResult(false); }
  }, []);

  const startFallbackPoll = useCallback((reportId) => {
    clearInterval(pollRef.current);
    setStreamConnected(false);
    const poll = async () => {
      try {
        const [statusData, execData] = await Promise.all([
          reportsApi.getStatus(reportId),
          fetch(`${BASE_URL}/api/v1/executions/report/${reportId}`).then(r => r.json()),
        ]);
        setActiveReport(prev => ({ ...prev, status: statusData.status, error_message: statusData.error_message }));
        const execs = execData.items ?? [];
        setExecutions(execs);
        setProgress(calcProgress(execs));
        if (statusData.status === "completed" || statusData.status === "failed") {
          clearInterval(pollRef.current);
          fetchFullReport(reportId);
        }
      } catch { /* keep retrying */ }
    };
    poll();
    pollRef.current = setInterval(poll, 2500);
  }, [fetchFullReport]);

  const startStream = useCallback((reportId) => {
    stopStream();
    try {
      const es = streamApi.openStatusStream(reportId, {
        onStatus: ({ report, executions: execs }) => {
          setStreamConnected(true);
          setActiveReport(prev => ({ ...prev, ...report }));
          setExecutions(execs ?? []);
          setProgress(calcProgress(execs));
        },
        onDone: () => { setStreamConnected(false); fetchFullReport(reportId); },
        onError: () => { setStreamConnected(false); startFallbackPoll(reportId); },
        onTimeout: () => setStreamConnected(false),
      });
      esRef.current = es;
    } catch { startFallbackPoll(reportId); }
  }, [stopStream, fetchFullReport, startFallbackPoll]);

  const validate = () => {
    const e = {};
    if (!form.topic.trim())    e.topic    = "Topic is required";
    if (!form.industry.trim()) e.industry = "Industry is required";
    if (!form.region.trim())   e.region   = "Region is required";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    stopStream();
    setSubmitting(true);
    setActiveReport(null);
    setExecutions([]);
    setProgress(0);
    setErrors({});
    try {
      const payload = {
        topic: form.topic.trim(),
        industry: form.industry.trim(),
        region: form.region.trim(),
        max_sources: Number(form.max_sources),
        max_steps: Number(form.max_steps),
      };
      if (form.competitor_name.trim()) payload.competitor_name = form.competitor_name.trim();
      const report = await reportsApi.create(payload);
      setActiveReport(report);
      startStream(report.id);
    } catch (err) {
      setErrors({ submit: err.message });
    } finally {
      setSubmitting(false);
    }
  };

  const isRunning      = activeReport?.status === "running" || activeReport?.status === "pending";
  const isDone         = activeReport?.status === "completed";
  const isFailed       = activeReport?.status === "failed";
  const completedSteps = executions.filter(e => e.status === "completed").length;
  const runningSteps   = executions.filter(e => e.status === "running").length;
  const topicDisplay   = activeReport?.topic || activeReport?.competitor_name || "";


  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: "Active Agents",    value: runningSteps,   icon: Loader2,      color: "text-blue-400" },
          { label: "Completed Steps",  value: completedSteps, icon: CheckCircle2, color: "text-emerald-400" },
          { label: "Overall Progress", value: `${progress}%`, icon: BarChart3,    color: "text-primary" },
        ].map(({ label, value, icon: Icon, color }) => (
          <Card key={label}>
            <CardContent className="pt-4 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className={cn("text-2xl font-bold mt-1", color)}>{value}</p>
                </div>
                <Icon className={cn("h-8 w-8 opacity-20", color)} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Input Form */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-4 w-4 text-primary" />
              New Intelligence Briefing
            </CardTitle>
            <CardDescription>Topic-based competitive intelligence run</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Topic — primary field */}
              <div className="space-y-1.5">
                <Label htmlFor="topic">Intelligence Topic *</Label>
                <Input
                  id="topic"
                  placeholder="e.g. EV pricing 2025, cloud AI market"
                  value={form.topic}
                  onChange={e => setForm(f => ({ ...f, topic: e.target.value }))}
                  className={errors.topic ? "border-destructive" : ""}
                  disabled={submitting || isRunning}
                />
                {errors.topic
                  ? <p className="text-xs text-destructive">{errors.topic}</p>
                  : <p className="text-xs text-muted-foreground">Market topic or question to research</p>
                }
              </div>

              {/* Competitor — optional */}
              <div className="space-y-1.5">
                <Label htmlFor="competitor_name">Competitor Focus <span className="text-muted-foreground">(optional)</span></Label>
                <Input
                  id="competitor_name"
                  placeholder="e.g. Tesla, OpenAI, Stripe"
                  value={form.competitor_name}
                  onChange={e => setForm(f => ({ ...f, competitor_name: e.target.value }))}
                  disabled={submitting || isRunning}
                />
                <p className="text-xs text-muted-foreground">Narrow focus to a specific company</p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="industry">Industry *</Label>
                <Input
                  id="industry"
                  placeholder="e.g. Electric Vehicles, AI, FinTech"
                  value={form.industry}
                  onChange={e => setForm(f => ({ ...f, industry: e.target.value }))}
                  className={errors.industry ? "border-destructive" : ""}
                  disabled={submitting || isRunning}
                />
                {errors.industry && <p className="text-xs text-destructive">{errors.industry}</p>}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="region">Region *</Label>
                <Input
                  id="region"
                  placeholder="e.g. North America, Europe, Global"
                  value={form.region}
                  onChange={e => setForm(f => ({ ...f, region: e.target.value }))}
                  className={errors.region ? "border-destructive" : ""}
                  disabled={submitting || isRunning}
                />
                {errors.region && <p className="text-xs text-destructive">{errors.region}</p>}
              </div>

              {/* Advanced / budget controls */}
              <button
                type="button"
                onClick={() => setShowAdvanced(v => !v)}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <Settings2 className="h-3.5 w-3.5" />
                {showAdvanced ? "Hide" : "Show"} advanced (budget caps)
              </button>
              {showAdvanced && (
                <div className="space-y-3 p-3 rounded-lg bg-muted/30 border border-border/50">
                  <div className="space-y-1.5">
                    <Label htmlFor="max_sources" className="text-xs">Max Sources (3–50)</Label>
                    <Input
                      id="max_sources"
                      type="number"
                      min={3} max={50}
                      value={form.max_sources}
                      onChange={e => setForm(f => ({ ...f, max_sources: e.target.value }))}
                      disabled={submitting || isRunning}
                      className="h-8 text-sm"
                    />
                    <p className="text-xs text-muted-foreground">Runaway guard: caps source gathering</p>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="max_steps" className="text-xs">Max Steps (10–200)</Label>
                    <Input
                      id="max_steps"
                      type="number"
                      min={10} max={200}
                      value={form.max_steps}
                      onChange={e => setForm(f => ({ ...f, max_steps: e.target.value }))}
                      disabled={submitting || isRunning}
                      className="h-8 text-sm"
                    />
                    <p className="text-xs text-muted-foreground">Runaway guard: caps total workflow steps</p>
                  </div>
                </div>
              )}

              {errors.submit && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/30">
                  <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
                  <p className="text-xs text-destructive">{errors.submit}</p>
                </div>
              )}

              <Button type="submit" className="w-full" disabled={submitting || isRunning}>
                {submitting ? <><Loader2 className="h-4 w-4 animate-spin" />Starting…</>
                : isRunning  ? <><Loader2 className="h-4 w-4 animate-spin" />Running…</>
                : <><Play className="h-4 w-4" />Run Intelligence Briefing</>}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Agent Pipeline Panel */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Loader2 className={cn("h-4 w-4 text-primary", isRunning && "animate-spin")} />
                  Agent Pipeline
                </CardTitle>
                <CardDescription>
                  {activeReport
                    ? `${topicDisplay} — ${activeReport.industry} — ${activeReport.region}`
                    : "Submit the form to start a briefing run"}
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <StreamIndicator connected={streamConnected} />
                {activeReport && (
                  <Badge variant={statusVariant(activeReport.status)}>{activeReport.status}</Badge>
                )}
              </div>
            </div>
            {isRunning && (
              <div className="mt-3 space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Progress</span><span>{progress}%</span>
                </div>
                <Progress value={progress} />
              </div>
            )}
          </CardHeader>
          <CardContent>
            {!activeReport ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="h-16 w-16 rounded-full bg-muted/30 flex items-center justify-center mb-4">
                  <Search className="h-7 w-7 text-muted-foreground/50" />
                </div>
                <p className="text-sm text-muted-foreground">No active run</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Enter a topic and click Run</p>
              </div>
            ) : (
              <div className="space-y-2">
                {AGENT_STEPS.map((step, i) => (
                  <AgentStepItem
                    key={step.key}
                    step={step}
                    execution={executions.find(e => e.agent_name === step.key)}
                    index={i}
                  />
                ))}
                {isFailed && activeReport.error_message && (
                  <div className="mt-3 p-3 rounded-lg bg-destructive/10 border border-destructive/30 flex items-start gap-2">
                    <XCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                    <p className="text-xs text-destructive">{activeReport.error_message}</p>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>


      {/* Loading skeleton */}
      <AnimatePresence>
        {loadingResult && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-4">
            <Skeleton className="h-32 w-full" />
            <div className="grid grid-cols-2 gap-4">
              <Skeleton className="h-48 w-full" />
              <Skeleton className="h-48 w-full" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Results section */}
      <AnimatePresence>
        {isDone && !loadingResult && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            transition={{ duration: 0.4 }}
            className="space-y-6"
          >
            {/* Governance summary bar */}
            <Card className="border-primary/20 bg-primary/5">
              <CardContent className="pt-4 pb-4">
                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider shrink-0">
                    Governance
                  </span>
                  <GovernanceBadge report={activeReport} />
                  {activeReport.duration_seconds && (
                    <span className="text-xs text-muted-foreground sm:ml-auto shrink-0">
                      Completed in {activeReport.duration_seconds.toFixed(1)}s
                    </span>
                  )}
                </div>
                {activeReport.warnings?.length > 0 && (
                  <div className="mt-3 space-y-1">
                    {activeReport.warnings.slice(0, 3).map((w, i) => (
                      <p key={i} className="text-xs text-yellow-400 flex items-start gap-1.5">
                        <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />{w}
                      </p>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 3 Required Briefing Sections */}
            {(activeReport.briefing_section_pricing ||
              activeReport.briefing_section_market ||
              activeReport.briefing_section_exec) && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                  <BookOpen className="h-4 w-4" /> Intelligence Briefing
                </h3>
                {[
                  activeReport.briefing_section_pricing,
                  activeReport.briefing_section_market,
                  activeReport.briefing_section_exec,
                ].map((sec, i) => sec && <BriefingSection key={i} section={sec} index={i} />)}
              </div>
            )}

            {/* SWOT + Recommendations */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {activeReport.swot_analysis && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Target className="h-4 w-4 text-primary" /> SWOT Analysis
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-3">
                      {SWOT_CONFIG.map(({ key, label, icon: Icon, cls, iconCls }) => (
                        <div key={key} className={cn("rounded-lg border p-3", cls)}>
                          <div className="flex items-center gap-2 mb-2">
                            <Icon className={cn("h-3.5 w-3.5", iconCls)} />
                            <span className="text-xs font-semibold uppercase tracking-wider">{label}</span>
                          </div>
                          <ul className="space-y-1">
                            {(activeReport.swot_analysis[key] || []).map((item, i) => (
                              <li key={i} className="text-xs text-foreground/70 flex items-start gap-1.5">
                                <ChevronRight className="h-3 w-3 shrink-0 mt-0.5 opacity-50" />{item}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {activeReport.recommendations?.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Lightbulb className="h-4 w-4 text-primary" /> Recommendations
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ScrollArea className="max-h-64">
                      <ul className="space-y-2">
                        {activeReport.recommendations.map((rec, i) => (
                          <motion.li
                            key={i}
                            initial={{ opacity: 0, x: -8 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: i * 0.07 }}
                            className="flex items-start gap-2 p-2.5 rounded-lg bg-primary/5 border border-primary/10"
                          >
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary text-[10px] font-bold mt-0.5">
                              {i + 1}
                            </span>
                            <span className="text-sm text-foreground/80 leading-snug">{rec}</span>
                          </motion.li>
                        ))}
                      </ul>
                    </ScrollArea>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Latest News */}
            {activeReport.latest_news?.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Newspaper className="h-4 w-4 text-primary" /> Latest News
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {activeReport.latest_news.map((item, i) => (
                      <motion.a
                        key={i}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        initial={{ opacity: 0, scale: 0.96 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: i * 0.06 }}
                        className="glass glass-hover rounded-lg p-3 group cursor-pointer block"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-foreground/90 leading-snug line-clamp-2 group-hover:text-primary transition-colors">
                            {item.title}
                          </p>
                          <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground mt-0.5 group-hover:text-primary" />
                        </div>
                        <div className="flex items-center gap-2 mt-2">
                          <Badge variant="info" className="text-[10px]">{item.source}</Badge>
                          {item.published_at && (
                            <span className="text-[10px] text-muted-foreground">
                              {new Date(item.published_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                        {item.summary && (
                          <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2">{item.summary}</p>
                        )}
                      </motion.a>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Export buttons */}
            <div className="flex items-center gap-3 flex-wrap">
              <a
                href={`${BASE_URL}/api/v1/reports/${activeReport.id}/export/pdf`}
                target="_blank" rel="noopener noreferrer"
              >
                <Button variant="outline" size="sm" className="gap-2">
                  <Download className="h-4 w-4" /> Export PDF
                </Button>
              </a>
              <a
                href={`${BASE_URL}/api/v1/reports/${activeReport.id}/export/markdown`}
                target="_blank" rel="noopener noreferrer"
              >
                <Button variant="outline" size="sm" className="gap-2">
                  <Download className="h-4 w-4" /> Export Markdown
                </Button>
              </a>
              <span className="text-xs text-muted-foreground">
                {activeReport.fact_check_passed ?? 0} claims cross-verified · {activeReport.uncited_claims_dropped?.length ?? 0} uncited dropped
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
