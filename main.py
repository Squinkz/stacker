import sys

from PySide6 import QtGui, QtWidgets

from gui.main_window import MainWindow
from gui.resources import BuildStyle, ThemeAppIconPath, ThemeName


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle("dark_fire"))
    appIcon = QtGui.QIcon(ThemeAppIconPath("dark_fire"))
    app.setWindowIcon(appIcon)
    window = MainWindow()
    activeIcon = QtGui.QIcon(ThemeAppIconPath(ThemeName()))
    app.setWindowIcon(activeIcon)
    window.setWindowIcon(activeIcon)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
