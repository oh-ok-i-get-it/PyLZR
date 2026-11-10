import sys
from PyQt5.QtWidgets import QApplication

from .core.app_logger import configure_console_logging


def main():
    app = QApplication(sys.argv)
    configure_console_logging()
    from .gui import MainWindow, style  # imported here so QApplication exists before any widget module loads
    style.apply(app)                     # before any window: fonts, palette, stylesheet, plot colours
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
