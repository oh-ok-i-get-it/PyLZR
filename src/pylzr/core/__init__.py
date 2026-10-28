from . import config, text_styles
from .config import *  # noqa: F403 — re-export every config constant

__all__ = [*config.__all__, 'text_styles']
