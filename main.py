import sys


def Main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--numba-warmup":
        from gui.worker import NumbaWarmupWorker
        from render import blend as bnc

        blendFunctionName = sys.argv[2] if len(sys.argv) >= 3 else ""
        blendFunction = getattr(bnc, blendFunctionName, None) if blendFunctionName else None
        if blendFunctionName and not callable(blendFunction):
            print(f"Unknown blend function: {blendFunctionName}", file = sys.stderr)
            return 2

        errors = []
        worker = NumbaWarmupWorker(blendFunction)
        worker.error.connect(errors.append)
        worker.Run()
        if errors:
            print(errors[-1], file = sys.stderr)
            return 1
        return 0

    from PySide6 import QtGui, QtWidgets

    from gui.main_window import MainWindow
    from gui.resources import BuildStyle, ThemeAppIconPath, ThemeName

    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle("dark_ice"))
    appIcon = QtGui.QIcon(ThemeAppIconPath("dark_ice"))
    app.setWindowIcon(appIcon)
    window = MainWindow()
    activeIcon = QtGui.QIcon(ThemeAppIconPath(ThemeName()))
    app.setWindowIcon(activeIcon)
    window.setWindowIcon(activeIcon)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(Main())
