"use client";

import { Radio, Cpu } from "lucide-react";

import { DemoModeToggle } from "@/components/command-center/demo-mode-toggle";
import { ThemeToggle } from "@/components/theme-toggle";
import { useApiHealth } from "@/hooks/use-api-health";
import { useModelStatus } from "@/hooks/use-model-status";

/** Milestone F4: real model readiness, distinct from general API
 * connectivity (`useApiHealth`, below) — a healthy API can still have a
 * disabled or not-yet-loaded model, and this must never be conflated
 * with "API is down." */
function ModelStatusIndicator() {
  const { data, isPending, isError } = useModelStatus();

  if (isPending) {
    return (
      <span className="text-muted-foreground flex items-center gap-1.5 text-xs" role="status">
        <Cpu className="size-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">Model:</span> Checking...
      </span>
    );
  }

  if (isError || !data) {
    return (
      <span className="text-destructive flex items-center gap-1.5 text-xs" role="status">
        <Cpu className="size-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">Model:</span> Unknown
      </span>
    );
  }

  // Milestone F5: the worker's actual lifecycle state, not just a
  // loaded/not-loaded boolean — "loading" (a real, 40-150s CLIP cold
  // start on a fresh worker) reads very differently from "failed" or
  // "disabled", and never as a generic API-connectivity problem.
  const label = {
    STARTING: "Starting...",
    MODEL_LOADING: "Loading...",
    READY: `Ready (${data.status.model_name})`,
    UNAVAILABLE: "Disabled",
    FAILED: data.error ? `Failed: ${data.error}` : "Failed",
  }[data.lifecycle_state];
  const tone = {
    STARTING: "text-muted-foreground",
    MODEL_LOADING: "text-amber-400",
    READY: "text-emerald-400",
    UNAVAILABLE: "text-muted-foreground",
    FAILED: "text-destructive",
  }[data.lifecycle_state];

  return (
    <span className={`flex items-center gap-1.5 text-xs ${tone}`} role="status" title={label}>
      <Cpu className="size-3.5" aria-hidden="true" />
      <span className="hidden sm:inline">Model:</span>{" "}
      <span className="max-w-32 truncate sm:max-w-48">{label}</span>
    </span>
  );
}

export function TopBar() {
  const { data, isPending, isError } = useApiHealth();
  const connectionLabel = isPending ? "Checking..." : isError ? "Offline" : (data?.status ?? "Unknown");
  const connectionTone = isError ? "text-destructive" : isPending ? "text-muted-foreground" : "text-emerald-400";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-background/80 px-4 backdrop-blur-md">
      <nav aria-label="Primary" className="flex items-center gap-3">
        <span className="text-sm font-semibold tracking-wide">SentinelAI</span>
        <span className="text-muted-foreground hidden text-xs sm:inline">
          3D Disaster Command Center
        </span>
      </nav>

      <div className="flex items-center gap-4">
        <DemoModeToggle />
        <span className={`flex items-center gap-1.5 text-xs ${connectionTone}`} role="status">
          <Radio className="size-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">API:</span> {connectionLabel}
        </span>
        <ModelStatusIndicator />
        <ThemeToggle />
      </div>
    </header>
  );
}
