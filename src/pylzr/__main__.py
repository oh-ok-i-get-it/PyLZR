import sys
from PyQt5.QtWidgets import QApplication

from .core.app_logger import configure_console_logging


def main():
    app = QApplication(sys.argv)
    configure_console_logging()
    from .gui import MainWindow  # imported here so QApplication exists before any widget module loads
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
