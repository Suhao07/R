"""Local, file-first research management and review hub.

The package indexes existing research evidence without taking ownership of the
underlying training, benchmark, or annotation contracts.
"""

from .config import HubConfig, load_config

__all__ = ("HubConfig", "load_config")
