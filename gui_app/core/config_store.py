import copy
import json


def build_gui_config_update(
    config,
    *,
    always_on_top,
    compact_mode,
    window_size,
    window_position,
):
    next_config = copy.deepcopy(config)
    gui_config = dict(next_config.get("gui", {}))
    gui_config.update(
        {
            "always_on_top": always_on_top,
            "compact_mode": compact_mode,
            "window_size": window_size,
            "window_position": window_position,
        }
    )
    next_config["gui"] = gui_config
    return next_config


def write_config(path, config):
    with open(path, "w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)
        config_file.write("\n")
