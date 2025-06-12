import sys
from PyQt5.QtWidgets import QApplication
from .gui import PyLZR

def main():
    app = QApplication(sys.argv)
    window = PyLZR()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
