# Kept free of GUI/audio imports so `import pylzr` is cheap; the app is
# started from __main__.main().
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('pylzr')
except PackageNotFoundError:   # running from a source tree that isn't installed
    __version__ = 'unknown'

__all__ = ['__version__']
