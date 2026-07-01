"""Dataset generation platform: export scenarios to CSV / JSON / graph / report.

This package is also the default on-disk output location for generated
datasets (see ``red_team.core.config.RedTeamConfig.output_dir``).
"""

from red_team.datasets.exporter import DatasetExporter

__all__ = ["DatasetExporter"]
