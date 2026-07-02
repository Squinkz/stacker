import time
import traceback

import numpy as np
from PySide6 import QtCore, QtGui

from render import blend as bnc
from render.renderer import BlendAndExport, RenderCancelled


class RenderWorker(QtCore.QObject):

    progress = QtCore.Signal(int, int)
    fps = QtCore.Signal(float)
    remaining = QtCore.Signal(float)
    preview = QtCore.Signal(QtGui.QImage, bool)
    log = QtCore.Signal(str)
    finished = QtCore.Signal()
    cancelled = QtCore.Signal()
    error = QtCore.Signal(str)

    def __init__(self, settings, cancelEvent, pauseEvent, previewOnly = False):
        super().__init__()
        self.settings = settings
        self.cancelEvent = cancelEvent
        self.pauseEvent = pauseEvent
        self.previewOnly = previewOnly
        self.lastPreviewTime = 0.0
        self.blendInLinear = bool(settings.get("render", {}).get("blendInLinear", True))

    def _PreviewOptions(self):
        previewSettings = self.settings.get("preview", {})
        previewEnabled = previewSettings.get("enabled", True)
        previewScale = max(1, int(previewSettings.get("scale", 1)))
        previewDisplayScale = 1 if self.previewOnly else previewScale
        previewFps = max(0.1, float(previewSettings.get("fps", 1.0)))
        return previewEnabled, previewDisplayScale, 1.0 / previewFps

    @QtCore.Slot()
    def Run(self):
        try:
            BlendAndExport(
                self.settings,
                onProgress = self.progress.emit,
                onFps = self.fps.emit,
                onRemaining = self.remaining.emit,
                onPreview = self.EmitPreview,
                onLog = self.log.emit,
                shouldCancel = self.cancelEvent.is_set,
                shouldPause = self.pauseEvent.is_set,
                printToConsole = False,
                exportFrames = not self.previewOnly,
                writeLog = not self.previewOnly,
            )
        except RenderCancelled:
            self.cancelled.emit()
        except Exception:
            self.error.emit(traceback.format_exc())
        else:
            self.finished.emit()

    def EmitPreview(self, rgb, force = False):
        previewEnabled, previewScale, previewInterval = self._PreviewOptions()
        if not previewEnabled and not self.previewOnly:
            return

        now = time.time()
        displayFrame = force or now - self.lastPreviewTime >= previewInterval
        if not self.previewOnly and not displayFrame:
            return

        if displayFrame:
            self.lastPreviewTime = now
        previewRgb = np.ascontiguousarray(rgb[::previewScale, ::previewScale, :])
        if self.blendInLinear:
            displayRgb = bnc.LinearToTransferUint8(previewRgb, bnc.TRANSFER_SRGB)
        else:
            displayRgb = bnc.LinearToTransferUint8(previewRgb, bnc.TRANSFER_LINEAR)
        displayRgb = np.ascontiguousarray(displayRgb)
        height, width, _ = displayRgb.shape
        image = QtGui.QImage(
            displayRgb.data,
            width,
            height,
            displayRgb.strides[0],
            QtGui.QImage.Format.Format_RGB888,
        ).copy()
        self.preview.emit(image, displayFrame)
