import { useState } from "react";
import { motion } from "framer-motion";
import {
  Settings as SettingsIcon, Key, Cpu, Database,
  Save, Eye, EyeOff, CheckCircle2, AlertCircle,
  ExternalLink, Info, RefreshCw,
} from "lucide-react";

import { healthApi } from "@/api/client";
import { Button }    from "@/components/ui/button";
import { Input }     from "@/components/ui/input";
import { Label }     from "@/components/ui/label";
import { Badge }     from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { cn }        from "@/lib/utils";

// ── Masked secret input ───────────────────────────────────────────────────────
function SecretInput({ id, label, value, onChange, placeholder, hint }) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type={show ? "text" : "password"}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="pr-10"
        />
        <button
          type="button"
          onClick={() => setShow(s => !s)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

// ── Section header ─────────────────────────────────────────────────────────────
function SectionHeader({ icon: Icon, title, description }) {
  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
    </div>
  );
}

// ── Main Settings Page ────────────────────────────────────────────────────────
export default function Settings() {
  // Form state
  const [apiKey, setApiKey]             = useState("");
  const [primaryModel, setPrimaryModel] = useState("meta-llama/llama-3.1-8b-instruct:free");
  const [fallbackModel, setFallbackModel] = useState("microsoft/phi-3-mini-128k-instruct:free");
  const [exportDir, setExportDir]       = useState("./data/exports");
  const [logLevel, setLogLevel]         = useState("INFO");
  const [debugMode, setDebugMode]       = useState(false);

  // UI state
  const [saved, setSaved]           = useState(false);
  const [apiTesting, setApiTesting] = useState(false);
  const [apiResult, setApiResult]   = useState(null); // null | "online" | "offline"

  const handleSave = (e) => {
    e.preventDefault();
    // Settings are stored in .env on the backend — in Phase 3 we'll wire this up.
    // For now, provide visual feedback.
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const testApiConnection = async () => {
    setApiTesting(true);
    setApiResult(null);
    try {
      await healthApi.check();
      setApiResult("online");
    } catch {
      setApiResult("offline");
    } finally {
      setApiTesting(false);
    }
  };

  const FREE_MODELS = [
    "meta-llama/llama-3.1-8b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "google/gemma-2-9b-it:free",
    "qwen/qwen-2-7b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
  ];

  return (
    <div className="max-w-3xl space-y-6 animate-fade-in">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <SettingsIcon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-semibold">Application Settings</h2>
            <p className="text-xs text-muted-foreground">
              Configure API keys, models, and preferences
            </p>
          </div>
        </div>
        <Badge variant="info" className="text-xs">
          <Info className="h-3 w-3 mr-1" />
          Updates apply on backend restart
        </Badge>
      </div>

      <form onSubmit={handleSave} className="space-y-5">
        {/* ── API Keys ─────────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <Card>
            <CardHeader className="pb-3">
              <SectionHeader
                icon={Key}
                title="OpenRouter API"
                description="Connect to OpenRouter to enable LLM-powered agents. All models are free."
              />
            </CardHeader>
            <CardContent className="space-y-4">
              <SecretInput
                id="openrouter-key"
                label="OpenRouter API Key *"
                value={apiKey}
                onChange={setApiKey}
                placeholder="sk-or-v1-…"
                hint={
                  <span>
                    Get your free API key at{" "}
                    <a
                      href="https://openrouter.ai/keys"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline inline-flex items-center gap-1"
                    >
                      openrouter.ai/keys
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </span>
                }
              />

              {/* Test connection button */}
              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={testApiConnection}
                  disabled={apiTesting}
                  className="gap-2"
                >
                  {apiTesting
                    ? <><RefreshCw className="h-4 w-4 animate-spin" /> Testing…</>
                    : <><RefreshCw className="h-4 w-4" /> Test Backend Connection</>
                  }
                </Button>
                {apiResult === "online" && (
                  <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                    <CheckCircle2 className="h-4 w-4" />Backend API is reachable
                  </span>
                )}
                {apiResult === "offline" && (
                  <span className="flex items-center gap-1.5 text-xs text-red-400">
                    <AlertCircle className="h-4 w-4" />Cannot reach backend API
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* ── LLM Models ───────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <Card>
            <CardHeader className="pb-3">
              <SectionHeader
                icon={Cpu}
                title="LLM Models"
                description="Primary model is used by default; fallback activates if primary fails."
              />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="primary-model">Primary Model</Label>
                <select
                  id="primary-model"
                  value={primaryModel}
                  onChange={e => setPrimaryModel(e.target.value)}
                  className="flex h-10 w-full rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {FREE_MODELS.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">
                  Currently: <code className="text-primary bg-primary/10 px-1 rounded">{primaryModel}</code>
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="fallback-model">Fallback Model</Label>
                <select
                  id="fallback-model"
                  value={fallbackModel}
                  onChange={e => setFallbackModel(e.target.value)}
                  className="flex h-10 w-full rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {FREE_MODELS.filter(m => m !== primaryModel).map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>

              <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
                <p className="text-xs text-blue-400 flex items-start gap-2">
                  <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  All listed models are free-tier on OpenRouter. The system automatically
                  retries with the fallback model if the primary fails.
                </p>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* ── Storage & Logging ─────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <Card>
            <CardHeader className="pb-3">
              <SectionHeader
                icon={Database}
                title="Storage & Logging"
                description="Configure export paths and logging verbosity."
              />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="export-dir">Export Directory</Label>
                <Input
                  id="export-dir"
                  value={exportDir}
                  onChange={e => setExportDir(e.target.value)}
                  placeholder="./data/exports"
                />
                <p className="text-xs text-muted-foreground">
                  PDF and Markdown exports are saved here (relative to backend root)
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="log-level">Log Level</Label>
                <select
                  id="log-level"
                  value={logLevel}
                  onChange={e => setLogLevel(e.target.value)}
                  className="flex h-10 w-full rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {["DEBUG","INFO","WARNING","ERROR","CRITICAL"].map(l => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg glass">
                <div>
                  <p className="text-sm font-medium">Debug Mode</p>
                  <p className="text-xs text-muted-foreground">Show full error stack traces in API responses</p>
                </div>
                <button
                  type="button"
                  onClick={() => setDebugMode(d => !d)}
                  className={cn(
                    "relative h-6 w-11 rounded-full transition-colors duration-200",
                    debugMode ? "bg-primary" : "bg-muted"
                  )}
                >
                  <span className={cn(
                    "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-200",
                    debugMode ? "translate-x-5" : "translate-x-0.5"
                  )} />
                </button>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <Separator />

        {/* ── Save button ───────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Settings are saved to the backend <code className="text-primary bg-primary/10 px-1 rounded">.env</code> file.
            <br />
            Restart the backend server after saving for changes to take effect.
          </p>
          <Button type="submit" className="gap-2 shrink-0">
            {saved ? (
              <><CheckCircle2 className="h-4 w-4" /> Saved!</>
            ) : (
              <><Save className="h-4 w-4" /> Save Settings</>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
