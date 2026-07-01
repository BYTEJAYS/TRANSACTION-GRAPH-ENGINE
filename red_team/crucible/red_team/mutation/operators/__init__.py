from red_team.mutation.operators.topology import (
    add_hop, fan_out_collector, insert_abandoned_node,
    insert_merchant_node, create_bipartite_split,
)
from red_team.mutation.operators.timing import (
    time_dilation, add_dormancy_period, jitter_timing, festival_timing,
)
from red_team.mutation.operators.amounts import (
    just_under_threshold, amount_noise, pyramid_amounts,
)
from red_team.mutation.operators.channels import (
    channel_hop, upi_app_diversity,
)
from red_team.mutation.operators.accounts import (
    age_the_accounts, reduce_velocity, geographic_spread,
)
from red_team.mutation.operators.structural import (
    recognized_pattern_verification, cash_out_disguise, layered_mixing,
)
from red_team.mutation.operators.advanced import (
    mule_hub_creator, cycle_extender, threshold_fragmenter,
    ghost_node_injector, dormant_activator,
)

ALL_OPERATORS = [
    add_hop, fan_out_collector, insert_abandoned_node, insert_merchant_node, create_bipartite_split,
    time_dilation, add_dormancy_period, jitter_timing, festival_timing,
    just_under_threshold, amount_noise, pyramid_amounts,
    channel_hop, upi_app_diversity,
    age_the_accounts, reduce_velocity, geographic_spread,
    recognized_pattern_verification, cash_out_disguise, layered_mixing,
    # Advanced operators from real Indian fraud case intelligence
    mule_hub_creator, cycle_extender, threshold_fragmenter,
    ghost_node_injector, dormant_activator,
]

# Starting weights — updated by learning/operator_weights.py after prophecy hits
DEFAULT_OPERATOR_WEIGHTS: dict[str, float] = {op.__name__: 1.0 for op in ALL_OPERATORS}
DEFAULT_OPERATOR_WEIGHTS["recognized_pattern_verification"] = 0.3  # highest danger, lowest default
DEFAULT_OPERATOR_WEIGHTS["layered_mixing"] = 0.6
DEFAULT_OPERATOR_WEIGHTS["cash_out_disguise"] = 0.7
DEFAULT_OPERATOR_WEIGHTS["add_hop"] = 1.2
DEFAULT_OPERATOR_WEIGHTS["festival_timing"] = 1.3  # proven high-value in Indian context
DEFAULT_OPERATOR_WEIGHTS["age_the_accounts"] = 1.4  # bypasses hard gate threshold
DEFAULT_OPERATOR_WEIGHTS["insert_abandoned_node"] = 1.3
# Advanced operators — higher weights because they derive from real confirmed fraud
DEFAULT_OPERATOR_WEIGHTS["mule_hub_creator"] = 1.8
DEFAULT_OPERATOR_WEIGHTS["ghost_node_injector"] = 2.0  # cash gap = no digital trace
DEFAULT_OPERATOR_WEIGHTS["dormant_activator"] = 1.6
DEFAULT_OPERATOR_WEIGHTS["threshold_fragmenter"] = 1.5
DEFAULT_OPERATOR_WEIGHTS["cycle_extender"] = 1.4
