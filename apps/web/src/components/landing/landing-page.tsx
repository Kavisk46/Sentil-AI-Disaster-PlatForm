"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { PlayCircle, ShieldAlert } from "lucide-react";

import { LandingHeroMap } from "@/components/landing/landing-hero-map";
import { LandingTopBar } from "@/components/landing/landing-top-bar";
import { LandingUpload } from "@/components/landing/landing-upload";
import { Button } from "@/components/ui/button";
import { useUploadAnalysis } from "@/hooks/use-analysis";
import { useIncidentStore } from "@/store/incident-store";

/**
 * Stage 1 of the flow (`docs/architecture/frontend.md`, "Landing page and
 * hero map"): hero + upload only, no dashboard chrome. A successful
 * upload — or choosing the live demo — sets the relevant
 * `incident-store.ts` state and navigates to `/dashboard`, which
 * continues to work exactly as it always has (and remains directly
 * loadable on its own: with no active analysis and demo mode off, it
 * shows its existing inline upload prompt, so this page is never the
 * only way in).
 */
export function LandingPage() {
  const router = useRouter();
  const setActiveAnalysisId = useIncidentStore((state) => state.setActiveAnalysisId);
  const setDemoMode = useIncidentStore((state) => state.setDemoMode);
  const upload = useUploadAnalysis();
  const [uploadProgress, setUploadProgress] = React.useState<number | null>(null);

  const handleFileSelected = (file: File) => {
    setUploadProgress(null);
    upload.mutate(
      { file, onProgress: (loaded, total) => setUploadProgress(total > 0 ? loaded / total : null) },
      {
        onSuccess: (result) => {
          if (result.ok) {
            setActiveAnalysisId(result.data.analysis_id);
            router.push("/dashboard");
          }
        },
      },
    );
  };

  const handleViewDemo = () => {
    setDemoMode(true);
    router.push("/dashboard");
  };

  return (
    <div className="relative flex min-h-full flex-1 flex-col">
      <div className="absolute inset-0">
        <LandingHeroMap />
        {/* Scrim so hero text/upload stay readable over the map in both
            themes — a plain gradient, not a motion effect. */}
        <div className="from-background via-background/70 absolute inset-0 bg-gradient-to-b to-transparent" />
      </div>

      <div className="relative z-10 flex flex-1 flex-col">
        <LandingTopBar />

        <main className="flex flex-1 flex-col items-center justify-center gap-8 px-4 py-16 text-center">
          <div className="flex flex-col items-center gap-3">
            <span className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
              <ShieldAlert className="size-3.5" aria-hidden="true" />
              AI disaster-response command center
            </span>
            <h1 className="text-hero text-4xl sm:text-6xl">SentinelAI</h1>
            <p className="text-hero-sub text-muted-foreground max-w-xl text-base sm:text-lg">
              Upload disaster imagery to get damage intelligence, risk assessment, and rescue
              routing in one operational workspace.
            </p>
          </div>

          <LandingUpload
            isUploading={upload.isPending}
            uploadProgress={uploadProgress}
            uploadErrorMessage={upload.isError ? upload.error.message : null}
            onFileSelected={handleFileSelected}
          />

          <Button variant="ghost" size="sm" onClick={handleViewDemo}>
            <PlayCircle className="size-4" />
            View live demo instead
          </Button>
        </main>
      </div>
    </div>
  );
}
