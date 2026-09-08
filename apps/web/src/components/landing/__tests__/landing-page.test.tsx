import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { LandingPage } from "@/components/landing/landing-page";
import { useIncidentStore } from "@/store/incident-store";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

// See the identical rationale in `upload-dropzone.test.tsx` — jsdom has
// no real Blob-URL implementation.
beforeAll(() => {
  URL.createObjectURL = vi.fn(() => "blob:mock-preview-url");
  URL.revokeObjectURL = vi.fn();
});

// Same rationale as `command-center.test.tsx`'s map stub — no real WebGL
// context in jsdom, and this test exercises the landing page's own
// upload/navigation logic, not MapLibre.
vi.mock("@/components/map/command-map-loader", () => ({
  CommandMapLoader: () => <div data-testid="hero-map-stub" />,
}));

afterEach(() => {
  push.mockClear();
  useIncidentStore.setState({ activeAnalysisId: null, isDemoMode: false });
});

function renderLandingPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LandingPage />
    </QueryClientProvider>,
  );
}

describe("LandingPage", () => {
  it("renders no dashboard chrome (no demo-mode switch, no API status)", () => {
    renderLandingPage();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByText(/^API:/)).not.toBeInTheDocument();
  });

  it("choosing the live demo sets demo mode and navigates to the dashboard", () => {
    renderLandingPage();
    fireEvent.click(screen.getByRole("button", { name: /view live demo/i }));

    expect(useIncidentStore.getState().isDemoMode).toBe(true);
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("a successful upload sets the active analysis id and navigates to the dashboard", async () => {
    // `apiUpload` (the only API-client function on the upload path) uses
    // `XMLHttpRequest`, not `fetch`, so it needs its own fake — see the
    // identical rationale in `lib/__tests__/api-client.test.ts`.
    class FakeXHR {
      static instances: FakeXHR[] = [];
      upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
      onerror: (() => void) | null = null;
      onload: (() => void) | null = null;
      status = 0;
      statusText = "";
      responseText = "";
      open = vi.fn();
      send = vi.fn(() => {
        this.status = 201;
        this.responseText = JSON.stringify({
          analysis_id: "new-analysis-id",
          status: "uploaded",
          filename: "aerial.png",
        });
        this.onload?.();
      });
      constructor() {
        FakeXHR.instances.push(this);
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXHR as unknown as typeof XMLHttpRequest);

    renderLandingPage();
    const dropzone = screen.getByRole("button", { name: /upload a satellite or disaster image/i });
    const input = dropzone.querySelector("input[type=file]") as HTMLInputElement;
    const file = new File(["x"], "aerial.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard"));
    expect(useIncidentStore.getState().activeAnalysisId).toBe("new-analysis-id");

    vi.unstubAllGlobals();
  });
});
