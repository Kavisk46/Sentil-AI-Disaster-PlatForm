"use client";

import { Radio } from "lucide-react";

import { DemoModeToggle } from "@/components/command-center/demo-mode-toggle";
import { ThemeToggle } from "@/components/theme-toggle";
import { useApiHealth } from "@/hooks/use-api-health";

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
        <ThemeToggle />
      </div>
    </header>
  );
}
