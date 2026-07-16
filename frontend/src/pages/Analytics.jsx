import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend, RadarChart, Radar,
  PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from "recharts";
import { Loader2, BarChart3, TrendingUp, Clock, Zap } from "lucide-react";

import { reportsApi, executionsApi } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ── Chart theme colours ──────────────────────────────────────────────────────
const COLORS = {
  primary:    "#818cf8",
  success:    "#34d399",
  warning:    "#fbbf24",
  danger:     "#f87171",
  info:       "#60a5fa",
  muted:      "#475569",
  purple:     "#c084fc",
};

const STATUS_COLORS = {
  completed: COLORS.success,
  running:   COLORS.info,
  pending:   COLORS.warning,
  failed:    COLORS.danger,
};

const AGENT_COLORS = {
  planner:  COLORS.primary,
  research: COLORS.info,
  news:     COLORS.purple,
  analyst:  COLORS.success,
  writer:   COLORS.warning,
  approval: COLORS.danger,
};

// ── Custom tooltip ────────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass rounded-lg p-3 border border-border/50 shadow-glass">
      {label && <p className="text-xs text-muted-foreground mb-1">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} className="text-sm font-medium" style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" ? p.value.toFixed(1) : p.value}
          {p.name?.includes("Duration") ? "s" : ""}
        </p>
      ))}
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, icon: Icon, color, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
    >
      <Card>
        <CardContent className="pt-5 pb-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className={cn("text-2xl font-bold mt-1", color)}>{value}</p>
              {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
            </div>
            <div className={cn("h-10 w-10 rounded-xl flex items-center justify-center bg-current/10", color)}>
              <Icon className={cn("h-5 w-5", color)} />
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

// ── Main Analytics Page ───────────────────────────────────────────────────────
export default function Analytics() {
  const [reports, setReports]     = useState([]);
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [rData, eData] = await Promise.all([
          reportsApi.list({ page: 1, page_size: 100 }),
          executionsApi.list({ page: 1, page_size: 500 }),
        ]);
        setReports(rData.items ?? []);
        setExecutions(eData.items ?? []);
      } catch {
        setReports([]);
        setExecutions([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  // ── Derived data ─────────────────────────────────────────────────────────

  // Status distribution for pie chart
  const statusData = Object.entries(
    reports.reduce((acc, r) => {
      acc[r.status] = (acc[r.status] || 0) + 1;
      return acc;
    }, {})
  ).map(([name, value]) => ({ name, value }));

  // Reports per day (last 7 days)
  const now = new Date();
  const dailyData = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now);
    d.setDate(d.getDate() - (6 - i));
    const key = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const dayReports = reports.filter(r => {
      const rd = new Date(r.created_at);
      return rd.toDateString() === d.toDateString();
    });
    return {
      date: key,
      total: dayReports.length,
      completed: dayReports.filter(r => r.status === "completed").length,
      failed:    dayReports.filter(r => r.status === "failed").length,
    };
  });

  // Agent performance — average duration per agent
  const agentPerf = Object.entries(
    executions
      .filter(e => e.duration_seconds != null)
      .reduce((acc, e) => {
        if (!acc[e.agent_name]) acc[e.agent_name] = { total: 0, count: 0 };
        acc[e.agent_name].total += e.duration_seconds;
        acc[e.agent_name].count += 1;
        return acc;
      }, {})
  ).map(([agent, { total, count }]) => ({
    agent: agent.charAt(0).toUpperCase() + agent.slice(1),
    avgDuration: parseFloat((total / count).toFixed(2)),
    runs: count,
    fill: AGENT_COLORS[agent] ?? COLORS.muted,
  }));

  // Radar chart data for agent success rates
  const agentRadar = Object.entries(
    executions.reduce((acc, e) => {
      if (!acc[e.agent_name]) acc[e.agent_name] = { completed: 0, total: 0 };
      acc[e.agent_name].total += 1;
      if (e.status === "completed") acc[e.agent_name].completed += 1;
      return acc;
    }, {})
  ).map(([agent, { completed, total }]) => ({
    agent: agent.charAt(0).toUpperCase() + agent.slice(1),
    successRate: total ? Math.round((completed / total) * 100) : 0,
  }));

  // Summary stats
  const completedReports = reports.filter(r => r.status === "completed");
  const avgDuration = completedReports.length
    ? (completedReports.reduce((s, r) => s + (r.duration_seconds ?? 0), 0) / completedReports.length).toFixed(1)
    : "—";
  const successRate = reports.length
    ? Math.round((completedReports.length / reports.length) * 100)
    : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* ── Summary stats ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Reports"     value={reports.length}              icon={BarChart3}   color="text-primary"      delay={0}    />
        <StatCard label="Success Rate"      value={`${successRate}%`}           icon={TrendingUp}  color="text-emerald-400"  delay={0.05} />
        <StatCard label="Avg Duration"      value={`${avgDuration}s`}           icon={Clock}       color="text-blue-400"     delay={0.10} />
        <StatCard label="Total Agent Runs"  value={executions.length}           icon={Zap}         color="text-purple-400"   delay={0.15} />
      </div>

      {/* ── Charts row 1 ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Reports per day */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Reports — Last 7 Days</CardTitle>
              <CardDescription>Daily report generation activity</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={dailyData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend wrapperStyle={{ fontSize: "12px" }} />
                  <Bar dataKey="completed" name="Completed" fill={COLORS.success} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="failed"    name="Failed"    fill={COLORS.danger}  radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>

        {/* Status distribution */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Status Distribution</CardTitle>
              <CardDescription>Breakdown of all report statuses</CardDescription>
            </CardHeader>
            <CardContent>
              {statusData.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[220px] text-center">
                  <BarChart3 className="h-8 w-8 text-muted-foreground/30 mb-2" />
                  <p className="text-sm text-muted-foreground">No data yet</p>
                </div>
              ) : (
                <div className="flex items-center gap-6">
                  <ResponsiveContainer width="60%" height={220}>
                    <PieChart>
                      <Pie
                        data={statusData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={85}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {statusData.map((entry) => (
                          <Cell key={entry.name} fill={STATUS_COLORS[entry.name] ?? COLORS.muted} />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="space-y-2">
                    {statusData.map(({ name, value }) => (
                      <div key={name} className="flex items-center gap-2">
                        <div className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS_COLORS[name] ?? COLORS.muted }} />
                        <span className="text-xs text-muted-foreground capitalize">{name}</span>
                        <span className="text-xs font-semibold ml-auto">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* ── Charts row 2 ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Agent average duration */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Agent Avg Duration (seconds)</CardTitle>
              <CardDescription>Time each agent takes on average</CardDescription>
            </CardHeader>
            <CardContent>
              {agentPerf.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[220px]">
                  <p className="text-sm text-muted-foreground">No execution data yet</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={agentPerf} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="agent" tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} width={60} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="avgDuration" name="Avg Duration" radius={[0, 4, 4, 0]}>
                      {agentPerf.map((entry) => (
                        <Cell key={entry.agent} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Agent success rate radar */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Agent Success Rate (%)</CardTitle>
              <CardDescription>Reliability of each agent in the pipeline</CardDescription>
            </CardHeader>
            <CardContent>
              {agentRadar.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[220px]">
                  <p className="text-sm text-muted-foreground">No execution data yet</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <RadarChart data={agentRadar} cx="50%" cy="50%" outerRadius={80}>
                    <PolarGrid stroke="rgba(255,255,255,0.08)" />
                    <PolarAngleAxis dataKey="agent" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 9 }} />
                    <Radar
                      name="Success Rate"
                      dataKey="successRate"
                      stroke={COLORS.primary}
                      fill={COLORS.primary}
                      fillOpacity={0.2}
                    />
                    <Tooltip content={<CustomTooltip />} />
                  </RadarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* ── Trends line chart ─────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Report Activity Trend</CardTitle>
            <CardDescription>Total vs completed reports over the last 7 days</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={dailyData} margin={{ top: 5, right: 20, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: "12px" }} />
                <Line type="monotone" dataKey="total"     name="Total"     stroke={COLORS.primary} strokeWidth={2} dot={{ fill: COLORS.primary, r: 3 }} />
                <Line type="monotone" dataKey="completed" name="Completed" stroke={COLORS.success} strokeWidth={2} dot={{ fill: COLORS.success, r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
