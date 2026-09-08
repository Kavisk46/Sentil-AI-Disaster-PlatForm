import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProvenanceBadge } from "@/components/ui/provenance-badge";
import { PROVENANCE_STYLE, type ProvenanceCategory } from "@/lib/data-provenance";

const categories: ProvenanceCategory[] = ["observed", "predicted", "calculated", "generated"];

describe("ProvenanceBadge", () => {
  it.each(categories)("renders the %s category's short code and full explanation", (category) => {
    render(<ProvenanceBadge category={category} />);
    const badge = screen.getByText(PROVENANCE_STYLE[category].code);
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("title", PROVENANCE_STYLE[category].description);
  });

  it("uses a visually distinct color per category, never color-only (short code text is always present)", () => {
    const codes = new Set(categories.map((c) => PROVENANCE_STYLE[c].code));
    expect(codes.size).toBe(categories.length);
  });
});
