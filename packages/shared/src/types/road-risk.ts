/** Mirrors `apps/api/app/schemas/road_risk.py`. */

import type { AnalysisStatus } from "./analysis";
import type { RoadEdge } from "./roads";

export interface RoadRiskResponse {
  analysis_id: string;
  status: AnalysisStatus;
  available: boolean;
  reason: string | null;
  edges: RoadEdge[];
}
