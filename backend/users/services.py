# Re-export all game service functions for backward-compatibility
from game.services import (
    _record_node_visit,
    record_game_history,
    process_submit,
    target_attack,
    establish_node_relation,
    remove_node_relation,
    clear_map_data,
)

__all__ = [
    "_record_node_visit",
    "record_game_history",
    "process_submit",
    "target_attack",
    "establish_node_relation",
    "remove_node_relation",
    "clear_map_data",
]
