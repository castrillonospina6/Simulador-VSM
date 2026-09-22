"""Punto de entrada del Simulador VSM."""
import sys

from PyQt5.QtWidgets import QApplication

from vsm.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Simulador VSM")
    win = MainWindow()
    win.resize(1440, 860)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
