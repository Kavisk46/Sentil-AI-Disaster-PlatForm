import { Badge } from "@/components/ui/badge";
import { PROVENANCE_STYLE, type ProvenanceCategory } from "@/lib/data-provenance";
import { cn } from "@/lib/utils";

export interface ProvenanceBadgeProps {
  category: ProvenanceCategory;
  className?: string;
}

/**
 * A small, consistent marker distinguishing what a responder is looking
 * at: observed / predicted / calculated / AI-generated (see
 * `lib/data-provenance.ts`). The full explanation is available on hover
 * via the native `title` attribute rather than a new Tooltip primitive.
 */
export function ProvenanceBadge({ category, className }: ProvenanceBadgeProps) {
  const style = PROVENANCE_STYLE[category];
  return (
    <Badge
      variant="outline"
      title={style.description}
      className={cn(style.className, "text-[10px] tracking-wide uppercase", className)}
    >
      {style.code}
    </Badge>
  );
}
