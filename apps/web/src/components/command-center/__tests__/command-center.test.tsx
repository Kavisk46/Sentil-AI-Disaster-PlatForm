import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommandCenter } from "@/components/command-center/command-center";
import { useIncidentStore } from "@/store/incident-store";

// The real map renders a WebGL canvas via a dynamically-imported
// `maplibre-gl`, neither of which exist in jsdom — stubbed out so this test
// exercises the command center's own data-flow/layout logic, not MapLibre
// (which has no useful behavior to assert on outside a real browser).
vi.mock("@/components/map/command-map-loader", () => ({
  CommandMapLoader: () => <div data-testid="map-stub" />,
}));

afterEach(() => {
  useIncidentStore.setState({
    activeAnalysisId: null,
    isDemoMode: false,
    routeStart: null,
    routeDestination: null,
  });
});

function renderCommandCenter() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CommandCenter />
    </QueryClientProvider>,
  );
}

describe("CommandCenter", () => {
  it("empty state: shows the upload dropzone and no severity yet when idle", () => {
    renderCommandCenter();
    expect(screen.getByRole("button", { name: /upload a satellite or disaster image/i })).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("demo mode: renders demo data end-to-end without disabling the map/panels", () => {
    useIncidentStore.setState({ isDemoMode: true });
    renderCommandCenter();

    expect(screen.getByText("Demo mode")).toBeInTheDocument();
    // Demo severity is "high" — see lib/demo/demo-data.ts.
    expect(screen.getByText(/HIGH/)).toBeInTheDocument();
    expect(screen.getByText("AI-Generated Incident Briefing")).toBeInTheDocument();
  });

  it("applies a responsive grid (single column on mobile, two columns from lg:) to the main layout", () => {
    const { container } = renderCommandCenter();
    const grid = container.querySelector(".grid");
    expect(grid).not.toBeNull();
    expect(grid?.className).toContain("grid-cols-1");
    expect(grid?.className).toMatch(/lg:grid-cols-/);
  });
});
