import sys
from PyQt5.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)
    from .gui import PyLZR  # imported here so QApplication exists before any widget module loads
    window = PyLZR()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
