"""Phase 0 demographic kernel: vital rates, Leslie oracle, and genesis."""

from macro_sim.demographics.kernel import (
    GenesisState,
    MicroDemographicKernel,
    count_alive_by_age,
    create_genesis_population,
)
from macro_sim.demographics.leslie import (
    LeslieDiagnostics,
    LeslieOracle,
    build_leslie_matrix,
    spectral_diagnostics,
    stable_age_distribution,
)
from macro_sim.demographics.multistate import (
    MaritalState,
    MultiStateIndex,
    Sex,
    build_multistate_leslie_matrix,
    calibrate_marital_fertility_curve,
    married_female_share_by_age,
    stable_multistate_distribution,
)
from macro_sim.demographics.rates import Phase0VitalRates, expected_life_at_birth
from macro_sim.demographics.relationships import RelationshipConfig, RelationshipStats, build_genesis_relationships
from macro_sim.demographics.social import SocialDynamicsConfig, SocialHealthStats, social_health_snapshot
from macro_sim.demographics.union import (
    MEDIUM_FAMILY_FORMATION_PROFILE,
    UnionAgeBand,
    UnionTargetProfile,
    partnered_share_by_band,
)
from macro_sim.demographics.visualization import plot_stable_pyramid

__all__ = [
    "GenesisState",
    "LeslieDiagnostics",
    "LeslieOracle",
    "MicroDemographicKernel",
    "MEDIUM_FAMILY_FORMATION_PROFILE",
    "MaritalState",
    "MultiStateIndex",
    "Phase0VitalRates",
    "RelationshipConfig",
    "RelationshipStats",
    "Sex",
    "SocialDynamicsConfig",
    "SocialHealthStats",
    "UnionAgeBand",
    "UnionTargetProfile",
    "build_leslie_matrix",
    "build_genesis_relationships",
    "build_multistate_leslie_matrix",
    "calibrate_marital_fertility_curve",
    "count_alive_by_age",
    "create_genesis_population",
    "expected_life_at_birth",
    "married_female_share_by_age",
    "partnered_share_by_band",
    "plot_stable_pyramid",
    "spectral_diagnostics",
    "social_health_snapshot",
    "stable_age_distribution",
    "stable_multistate_distribution",
]
