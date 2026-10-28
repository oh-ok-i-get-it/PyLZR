# ANSI terminal color and formatting escape codes (only the ones in use).

# Foreground colors
BLUE   = '\033[34m'
GREEN  = '\033[32m'
RED    = '\033[31m'
YELLOW = '\033[33m'
PURPLE = '\033[35m'
CYAN   = '\033[36m'
WHITE  = '\033[37m'
BLACK  = '\033[30m'

# Background colors
REDB   = '\033[41m'
GREENB = '\033[42m'
CYANB  = '\033[46m'

# Text formatting
B    = '\033[1m'
BOFF = '\033[22m'
I    = '\033[3m'
IOFF = '\033[23m'

RESET = '\033[0m'

__all__ = [
    'BLUE', 'GREEN', 'RED', 'YELLOW', 'PURPLE', 'CYAN', 'WHITE', 'BLACK',
    'REDB', 'GREENB', 'CYANB',
    'B', 'BOFF', 'I', 'IOFF', 'RESET',
]
