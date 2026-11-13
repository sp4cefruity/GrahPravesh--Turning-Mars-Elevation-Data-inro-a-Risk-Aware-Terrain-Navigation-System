"""Data stage. The pipeline calls `load_terrain(config)` (see `pipeline.STAGES`)."""
from odyssey.data.dem import load_tile
from odyssey.data.scene import build_scene

DEFAULT_TILE = "T1"


def load_scene(config):
    """Returns (TerrainGrid, SceneTruth). The truth is for evaluation only, never for the planner."""
    # shortcut: PipelineConfig has no tile_id yet (Udit owns it), so fall back to DEFAULT_TILE.
    tile = load_tile(getattr(config, "tile_id", DEFAULT_TILE))
    return build_scene(tile, seed=config.seeds.data, noise_level=config.noise_level)


def load_terrain(config):
    return load_scene(config)[0]
