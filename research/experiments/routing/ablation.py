"""Ablation configuration — a single `AblationFlags` object selects which
SentinelAI signal(s) feed into routing edge cost, covering this
milestone's baselines A-D and ablation study A-E without any code change
(see `load_ablation_config()` and `research/configs/*.json`).
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AblationFlags:
    use_damage: bool
    use_road_risk: bool
    use_hazard: bool


# Experimental baselines A-D (see the Milestone 10 spec's "EXPERIMENTAL
# BASELINES" section).
SHORTEST_PATH = AblationFlags(use_damage=False, use_road_risk=False, use_hazard=False)
DAMAGE_AWARE = AblationFlags(use_damage=True, use_road_risk=False, use_hazard=False)
RISK_AWARE = AblationFlags(use_damage=False, use_road_risk=True, use_hazard=False)
FULL_SENTINELAI = AblationFlags(use_damage=True, use_road_risk=True, use_hazard=True)

# Ablation study A-E. B/C/D/E deliberately reuse the flags above where
# they coincide with a named baseline — the baseline comparison and the
# ablation study are conceptually different experiments that happen to
# share configurations today, given SentinelAI has exactly two real
# signals (damage, road risk) and one inert placeholder (hazard).
ABLATION_A_NONE = SHORTEST_PATH
ABLATION_B_DAMAGE_ONLY = DAMAGE_AWARE
ABLATION_C_ROAD_RISK_ONLY = RISK_AWARE
ABLATION_D_DAMAGE_AND_RISK = AblationFlags(use_damage=True, use_road_risk=True, use_hazard=False)
ABLATION_E_FULL_WITH_HAZARD = FULL_SENTINELAI

NAMED_CONFIGURATIONS: dict[str, AblationFlags] = {
    "shortest_path": SHORTEST_PATH,
    "damage_aware": DAMAGE_AWARE,
    "risk_aware": RISK_AWARE,
    "full_sentinelai": FULL_SENTINELAI,
    "ablation_a_none": ABLATION_A_NONE,
    "ablation_b_damage_only": ABLATION_B_DAMAGE_ONLY,
    "ablation_c_road_risk_only": ABLATION_C_ROAD_RISK_ONLY,
    "ablation_d_damage_and_risk": ABLATION_D_DAMAGE_AND_RISK,
    "ablation_e_full_with_hazard": ABLATION_E_FULL_WITH_HAZARD,
}


def load_ablation_config(path: str | Path) -> tuple[str, AblationFlags]:
    """Loads one `research/configs/*.json` file —
    `{"name": "...", "ablation": {"use_damage": bool, "use_road_risk": bool, "use_hazard": bool}}`
    — into `(name, AblationFlags)`. Selecting a different configuration is
    always a new/edited JSON file, never a code change.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ablation = data["ablation"]
    return data["name"], AblationFlags(
        use_damage=bool(ablation["use_damage"]),
        use_road_risk=bool(ablation["use_road_risk"]),
        use_hazard=bool(ablation["use_hazard"]),
    )
