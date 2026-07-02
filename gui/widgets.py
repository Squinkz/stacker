import math
import os

from PySide6 import QtCore, QtGui, QtWidgets

from .resources import AssetIcon, SplitAssetIcon, ThemeColor, ThemeQColor


class RightAlignedMenuToolButton(QtWidgets.QToolButton):

    def __init__(self, parent = None):
        super().__init__(parent)
        self.popupAbove = False

    def SetPopupAbove(self, popupAbove):
        self.popupAbove = bool(popupAbove)

    def _MenuButtonRect(self):
        option = QtWidgets.QStyleOptionToolButton()
        self.initStyleOption(option)
        return self.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_ToolButton,
            option,
            QtWidgets.QStyle.SubControl.SC_ToolButtonMenu,
            self,
        )

    def _PopupRightAlignedMenu(self):
        menu = self.menu()
        if not menu:
            return False

        menuSize = menu.sizeHint()
        popupX = self.width() - menuSize.width()
        popupY = -menuSize.height() if self.popupAbove else self.height()
        menu.popup(self.mapToGlobal(QtCore.QPoint(popupX, popupY)))
        return True

    def showMenu(self):
        if not self._PopupRightAlignedMenu():
            super().showMenu()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.RightButton and self.menu():
            self.showMenu()
            event.accept()
            return

        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self.popupMode() == QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup
            and self._MenuButtonRect().contains(event.position().toPoint())
            and self._PopupRightAlignedMenu()
        ):
            event.accept()
            return

        super().mousePressEvent(event)


class DownwardComboBox(QtWidgets.QComboBox):

    def showPopup(self):
        super().showPopup()

        view = self.view()
        popup = view.window() if view is not None else None
        if popup is None:
            return

        globalPosition = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        popup.move(globalPosition)


class FolderField(QtWidgets.QWidget):

    textChanged = QtCore.Signal(str)
    pathBrowsed = QtCore.Signal(str)

    def __init__(self, defaultPath = "", parent = None, dialogTitle = "Select Folder"):
        super().__init__(parent)

        self.dialogTitle = dialogTitle
        self.startPath = ""
        self.lineEdit = QtWidgets.QLineEdit(defaultPath)
        self.lineEdit.textChanged.connect(self.textChanged.emit)
        self.button = QtWidgets.QToolButton()
        self.button.setIcon(AssetIcon("folder_open_24dp_E3E3E3.svg"))
        self.button.setToolTip("Browse")
        self.button.clicked.connect(self.Browse)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.lineEdit, 1)
        layout.addWidget(self.button)

    def Browse(self):
        startPath = self.Text() if os.path.isdir(self.Text()) else self.startPath
        if not os.path.isdir(startPath):
            startPath = os.getcwd()
        path = QtWidgets.QFileDialog.getExistingDirectory(self, self.dialogTitle, startPath)
        if path:
            self.lineEdit.setText(path)
            self.pathBrowsed.emit(path)
        return path

    def RefreshIcon(self):
        self.button.setIcon(AssetIcon("folder_open_24dp_E3E3E3.svg"))

    def Text(self):
        return self.lineEdit.text().strip()

    def SetStartPath(self, path):
        self.startPath = path if os.path.isdir(str(path)) else ""

    def SetEnabled(self, enabled):
        self.lineEdit.setEnabled(enabled)
        self.button.setEnabled(enabled)


class FloatSlider(QtWidgets.QWidget):

    valueChanged = QtCore.Signal(float)

    def __init__(
        self,
        value = 0.0,
        parent = None,
        logarithmic = False,
        inverseLogarithmic = False,
        curve = None,
        displayLinearValue = False,
        invertLinearValue = False,
        minimumPositive = 0.001,
        decimals = 2,
    ):
        super().__init__(parent)

        self.logarithmic = logarithmic
        self.inverseLogarithmic = inverseLogarithmic
        self.curve = curve
        self.displayLinearValue = displayLinearValue
        self.invertLinearValue = invertLinearValue
        self.minimumPositive = max(0.000001, float(minimumPositive))
        self.updating = False

        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setMinimumHeight(26)

        self.spinBox = QtWidgets.QDoubleSpinBox()
        self.spinBox.setRange(0.0, 1.0)
        self.spinBox.setSingleStep(10 ** -decimals)
        self.spinBox.setDecimals(decimals)
        self.spinBox.setFixedWidth(96)

        self.slider.valueChanged.connect(self._SliderChanged)
        self.spinBox.valueChanged.connect(self._SpinBoxChanged)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spinBox)

        self.SetValue(value)

    def Value(self):
        return self._ValueFromDisplay(self.spinBox.value())

    def SetValue(self, value):
        value = max(0.0, min(1.0, float(value)))
        displayValue = self._DisplayFromValue(value)
        self.updating = True
        self.spinBox.setValue(displayValue)
        self.slider.setValue(self._SliderFromDisplay(displayValue))
        self.updating = False

    def _DisplayFromValue(self, value):
        if self.displayLinearValue:
            return self._SliderFromValue(value) / max(1, self.slider.maximum())

        if self.invertLinearValue:
            return 1.0 - value

        return value

    def _ValueFromDisplay(self, displayValue):
        displayValue = max(0.0, min(1.0, float(displayValue)))
        if self.displayLinearValue:
            return self._ValueFromSlider(round(displayValue * self.slider.maximum()))

        if self.invertLinearValue:
            return 1.0 - displayValue

        return displayValue

    def _SliderFromDisplay(self, displayValue):
        if self.displayLinearValue:
            return round(max(0.0, min(1.0, float(displayValue))) * self.slider.maximum())

        if self.invertLinearValue:
            return round(max(0.0, min(1.0, float(displayValue))) * self.slider.maximum())

        return self._SliderFromValue(displayValue)

    def _ValueFromSlider(self, sliderValue):
        sliderMaximum = max(1, self.slider.maximum())
        t = max(0.0, min(1.0, sliderValue / sliderMaximum))

        if self.curve == "cubic_out":
            return 1.0 - ((1.0 - t) ** 3)

        if not self.logarithmic and not self.inverseLogarithmic:
            return t

        if sliderValue <= 0:
            return 0.0

        if self.inverseLogarithmic:
            if sliderValue >= sliderMaximum:
                return 1.0

            return 1.0 - math.exp(math.log(self.minimumPositive) * t)

        return math.exp(math.log(self.minimumPositive) * (1.0 - t))

    def _SliderFromValue(self, value):
        sliderMaximum = max(1, self.slider.maximum())
        value = max(0.0, min(1.0, float(value)))

        if self.curve == "cubic_out":
            t = 1.0 - ((1.0 - value) ** (1.0 / 3.0))
            return round(max(0.0, min(1.0, t)) * sliderMaximum)

        if not self.logarithmic and not self.inverseLogarithmic:
            return round(value * sliderMaximum)

        if value <= 0.0:
            return 0

        if self.inverseLogarithmic:
            if value >= 1.0:
                return sliderMaximum

            distanceFromOne = max(self.minimumPositive, 1.0 - value)
            t = math.log(distanceFromOne) / math.log(self.minimumPositive)
            return round(max(0.0, min(1.0, t)) * sliderMaximum)

        value = max(self.minimumPositive, value)
        t = (math.log(value) - math.log(self.minimumPositive)) / -math.log(self.minimumPositive)
        return round(max(0.0, min(1.0, t)) * sliderMaximum)

    def _SliderChanged(self, value):
        if self.updating:
            return

        self.updating = True
        if self.displayLinearValue:
            self.spinBox.setValue(value / max(1, self.slider.maximum()))
        else:
            self.spinBox.setValue(self._ValueFromSlider(value))
        self.updating = False
        self.valueChanged.emit(self.Value())

    def _SpinBoxChanged(self, value):
        if self.updating:
            return

        self.updating = True
        self.slider.setValue(self._SliderFromDisplay(value))
        self.updating = False
        self.valueChanged.emit(self.Value())


class RangeSlider(QtWidgets.QWidget):

    valuesChanged = QtCore.Signal(int, int)
    handleDragStarted = QtCore.Signal(str)
    handleDragEnded = QtCore.Signal(str)

    HANDLE_RADIUS = 8
    TRACK_HEIGHT = 6

    def __init__(self, minimum = 0, maximum = 100, lowerValue = 0, upperValue = 40, parent = None):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = max(minimum, maximum)
        self.lowerValue = lowerValue
        self.upperValue = upperValue
        self.activeHandle = None
        self.displayReversed = False

        self.setMinimumHeight(34)
        self.setMinimumWidth(180)
        self.setMouseTracking(True)
        self.SetRange(self.minimum, self.maximum)
        self.SetValues(lowerValue, upperValue)

    def SetRange(self, minimum, maximum):
        self.minimum = int(minimum)
        self.maximum = max(self.minimum, int(maximum))
        self.SetValues(self.lowerValue, self.upperValue)

    def SetValues(self, lowerValue, upperValue):
        lowerValue = self._ClampValue(lowerValue)
        upperValue = self._ClampValue(upperValue)

        if lowerValue > upperValue:
            lowerValue, upperValue = upperValue, lowerValue

        if self.maximum > self.minimum and lowerValue == upperValue:
            if upperValue == self.maximum:
                lowerValue = upperValue - 1
            else:
                upperValue = lowerValue + 1

        changed = lowerValue != self.lowerValue or upperValue != self.upperValue
        self.lowerValue = lowerValue
        self.upperValue = upperValue
        self.update()

        if changed:
            self.valuesChanged.emit(self.lowerValue, self.upperValue)

    def Values(self):
        return self.lowerValue, self.upperValue

    def SetDisplayReversed(self, reversedDisplay):
        self.displayReversed = bool(reversedDisplay)
        self.update()

    def _ClampValue(self, value):
        return max(self.minimum, min(self.maximum, int(value)))

    def _TrackRect(self):
        margin = self.HANDLE_RADIUS + 2
        y = self.height() // 2
        return QtCore.QRectF(
            margin,
            y - (self.TRACK_HEIGHT / 2),
            max(1, self.width() - (margin * 2)),
            self.TRACK_HEIGHT,
        )

    def _PositionFromValue(self, value):
        track = self._TrackRect()
        span = max(1, self.maximum - self.minimum)
        ratio = (value - self.minimum) / span
        if self.displayReversed:
            ratio = 1.0 - ratio
        return track.left() + (track.width() * ratio)

    def _ValueFromPosition(self, x):
        track = self._TrackRect()
        ratio = (x - track.left()) / track.width()
        ratio = max(0.0, min(1.0, ratio))
        if self.displayReversed:
            ratio = 1.0 - ratio
        value = self.minimum + round(ratio * (self.maximum - self.minimum))
        return self._ClampValue(value)

    def _NearestHandle(self, pos):
        lowerDistance = abs(pos.x() - self._PositionFromValue(self.lowerValue))
        upperDistance = abs(pos.x() - self._PositionFromValue(self.upperValue))
        return "lower" if lowerDistance <= upperDistance else "upper"

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        track = self._TrackRect()
        lowerX = self._PositionFromValue(self.lowerValue)
        upperX = self._PositionFromValue(self.upperValue)
        selectedLeft = min(lowerX, upperX)
        selected = QtCore.QRectF(selectedLeft, track.top(), abs(upperX - lowerX), track.height())

        enabled = self.isEnabled()
        trackColor = "#949494" if enabled else "#303030"
        selectedColor = "#e7e9ee" if enabled else "#777777"
        handleBorderColor = "#f4f4f4" if enabled else "#777777"

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(trackColor))
        painter.drawRoundedRect(track, 3, 3)

        painter.setBrush(QtGui.QColor(selectedColor))
        painter.drawRoundedRect(selected, 3, 3)

        for x in (lowerX, upperX):
            handleRect = QtCore.QRectF(
                x - self.HANDLE_RADIUS,
                (self.height() / 2) - self.HANDLE_RADIUS,
                self.HANDLE_RADIUS * 2,
                self.HANDLE_RADIUS * 2,
            )
            painter.setBrush(QtGui.QColor(selectedColor))
            painter.setPen(QtGui.QPen(QtGui.QColor(handleBorderColor), 1))
            painter.drawEllipse(handleRect)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.activeHandle = self._NearestHandle(event.position())
            self.handleDragStarted.emit(self.activeHandle)
            self._MoveActiveHandle(event.position().x())
            event.accept()

    def mouseMoveEvent(self, event):
        if self.activeHandle:
            self._MoveActiveHandle(event.position().x())
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.activeHandle:
            self.handleDragEnded.emit(self.activeHandle)
        self.activeHandle = None
        event.accept()

    def _MoveActiveHandle(self, x):
        value = self._ValueFromPosition(x)

        if self.activeHandle == "lower":
            self.SetValues(min(value, self.upperValue - 1), self.upperValue)
        elif self.activeHandle == "upper":
            self.SetValues(self.lowerValue, max(value, self.lowerValue + 1))


class RangeField(QtWidgets.QWidget):

    valuesChanged = QtCore.Signal(int, int)
    handleDragStarted = QtCore.Signal(str)
    handleDragEnded = QtCore.Signal(str)

    def __init__(self, parent = None):
        super().__init__(parent)

        self.updating = False
        self.displayReversed = False
        self.startSpinBox = QtWidgets.QSpinBox()
        self.startSpinBox.setRange(0, 100)
        self.startSpinBox.setFixedWidth(84)

        self.slider = RangeSlider(0, 100, 0, 40)

        self.stopSpinBox = QtWidgets.QSpinBox()
        self.stopSpinBox.setRange(0, 100)
        self.stopSpinBox.setFixedWidth(84)

        self.valueLabel = QtWidgets.QLabel()
        self.valueLabel.setMinimumWidth(72)
        self.valueLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.valueLabel.setStyleSheet("color: #b8b8b8;")

        self.startSpinBox.valueChanged.connect(self._SpinBoxesChanged)
        self.stopSpinBox.valueChanged.connect(self._SpinBoxesChanged)
        self.slider.valuesChanged.connect(self._ValuesChanged)
        self.slider.handleDragStarted.connect(self.handleDragStarted.emit)
        self.slider.handleDragEnded.connect(self.handleDragEnded.emit)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.startSpinBox)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.stopSpinBox)
        layout.addWidget(self.valueLabel)

        self._ValuesChanged(*self.slider.Values())

    def AddRightWidget(self, widget):
        self.layout().addWidget(widget, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

    def SetMaximum(self, maximum, useFullRange = False):
        lower, upper = self.slider.Values()
        self.startSpinBox.setRange(0, maximum)
        self.stopSpinBox.setRange(0, maximum)
        self.slider.SetRange(0, maximum)

        if useFullRange:
            lower = 0
            upper = maximum
        elif upper == 0 and maximum > 0:
            upper = maximum
        elif upper > maximum:
            upper = maximum

        if lower > upper:
            lower = upper

        self.slider.SetValues(lower, upper)
        self.setEnabled(maximum > 0)
        self._ValuesChanged(*self.slider.Values())

    def Values(self):
        return self.slider.Values()

    def SetValues(self, lowerValue, upperValue):
        self.slider.SetValues(lowerValue, upperValue)

    def SetDisplayReversed(self, reversedDisplay):
        self.displayReversed = bool(reversedDisplay)
        self.slider.SetDisplayReversed(self.displayReversed)
        self._ValuesChanged(*self.slider.Values())

    def _ValuesChanged(self, lowerValue, upperValue):
        self.updating = True
        if self.displayReversed:
            self.startSpinBox.setValue(upperValue)
            self.stopSpinBox.setValue(lowerValue)
        else:
            self.startSpinBox.setValue(lowerValue)
            self.stopSpinBox.setValue(upperValue)
        self.updating = False
        self.valueLabel.setText(f"{self.startSpinBox.value()} - {self.stopSpinBox.value()}")
        self.valuesChanged.emit(lowerValue, upperValue)

    def _SpinBoxesChanged(self):
        if self.updating:
            return

        if self.displayReversed:
            self.slider.SetValues(self.stopSpinBox.value(), self.startSpinBox.value())
        else:
            self.slider.SetValues(self.startSpinBox.value(), self.stopSpinBox.value())


class PreviewPane(QtWidgets.QWidget):

    viewportChanged = QtCore.Signal(float, QtCore.QPointF)
    emptyClicked = QtCore.Signal()
    contextMenuRequested = QtCore.Signal(object, QtCore.QPoint)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.pixmap = None
        self.placeholderText = "Preview"
        self.emptyActionEnabled = False
        self.emptyIconName = None
        self.emptyIcon = QtGui.QIcon()
        self.emptyColor = None
        self.zoom = 1.0
        self.panOffset = QtCore.QPointF(0.0, 0.0)
        self.isPanning = False
        self.panButton = None
        self.lastPanPosition = QtCore.QPointF()
        self.overlayLines = []
        self.previewTitle = ""
        self.previewMetadata = []
        self.previewWarnings = []
        self.hoverPixel = None
        self.lastMousePosition = None
        self.viewportScaling = "Interpolated"
        self.syncingViewport = False
        self.borderVisible = True
        self.viewportBackgroundOverride = None
        self.showTitle = True
        self.showDimensions = True
        self.showColorSpace = True
        self.showCoordinates = True
        self.showZoom = True
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.WheelFocus)

    def SetEmptyAction(self, enabled, icon = None, text = None, color = None):
        self.emptyActionEnabled = bool(enabled)
        if icon is not None:
            self.emptyIcon = icon
            self.emptyIconName = None
        elif not enabled:
            self.emptyIcon = QtGui.QIcon()
            self.emptyIconName = None
        if text is not None:
            self.placeholderText = text
        self.emptyColor = color
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor if self.emptyActionEnabled else QtCore.Qt.CursorShape.ArrowCursor)
        self.update()

    def SetNeutralPlaceholder(self, text):
        self.emptyActionEnabled = False
        self.emptyIconName = "stacker_E3E3E3.svg"
        self.emptyIcon = AssetIcon(self.emptyIconName)
        self.emptyColor = None
        self.placeholderText = text
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.update()

    def SetEmptyError(self, text):
        self.emptyIconName = "error_24dp_E3E3E3.svg"
        self.SetEmptyAction(False, AssetIcon(self.emptyIconName), text, "ERROR")
        self.emptyIconName = "error_24dp_E3E3E3.svg"
        self.emptyActionEnabled = True
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.update()

    def RefreshEmptyIcon(self):
        if self.emptyIconName:
            self.emptyIcon = AssetIcon(self.emptyIconName)
            self.update()

    def SetViewportState(self, zoom, panOffset):
        self.syncingViewport = True
        self.zoom = float(zoom)
        self.panOffset = QtCore.QPointF(panOffset)
        self.syncingViewport = False
        self._UpdateHoverPixel(self.lastMousePosition)
        self.update()

    def EmitViewportChanged(self):
        if not self.syncingViewport:
            self.viewportChanged.emit(self.zoom, QtCore.QPointF(self.panOffset))

    def SetViewportScaling(self, scaling):
        self.viewportScaling = scaling if scaling in ("Interpolated", "Nearest") else "Interpolated"
        self.update()

    def SetBorderVisible(self, visible):
        self.borderVisible = bool(visible)
        self.update()

    def SetViewportBackgroundOverride(self, value):
        if value is None:
            self.viewportBackgroundOverride = None
        else:
            self.viewportBackgroundOverride = max(0, min(255, int(value)))
        self.update()

    def ViewportBackgroundColor(self):
        if self.viewportBackgroundOverride is None:
            return ThemeQColor("VIEWPORT_BG")
        value = self.viewportBackgroundOverride
        return QtGui.QColor(value, value, value)

    def SetInfoVisibility(self, showTitle, showDimensions, showColorSpace, showCoordinates, showZoom):
        self.showTitle = bool(showTitle)
        self.showDimensions = bool(showDimensions)
        self.showColorSpace = bool(showColorSpace)
        self.showCoordinates = bool(showCoordinates)
        self.showZoom = bool(showZoom)
        self.update()

    def _MetadataCategory(self, line):
        text = self._LineText(line).lower()
        if "dimensions:" in text:
            return "dimensions"
        if text.startswith("color space:") or text.startswith("transfer function:"):
            return "color"
        return "other"

    def _VisibleMetadataLines(self):
        lines = []
        for line in self.previewMetadata:
            category = self._MetadataCategory(line)
            if category == "dimensions" and not self.showDimensions:
                continue
            if category == "color" and not self.showColorSpace:
                continue
            lines.append(line)
        return lines

    def SetOverlayLines(self, lines):
        self.overlayLines = [line for line in lines if line]
        self.update()

    def SetInfoWarningLines(self, lines):
        self.previewWarnings = [line for line in lines if line]
        self.update()

    def _LineText(self, line):
        if isinstance(line, (list, tuple)):
            return "".join(str(segment[0]) for segment in line)
        return str(line)

    def _DrawLineSegments(self, painter, x, baseline, line, defaultColor):
        if not isinstance(line, (list, tuple)):
            painter.setPen(self._SegmentColor(defaultColor))
            painter.drawText(x, baseline, str(line))
            return

        segmentX = x
        metrics = QtGui.QFontMetrics(painter.font())
        for segment in line:
            if isinstance(segment, (list, tuple)):
                text = str(segment[0])
                color = segment[1] if len(segment) > 1 else defaultColor
            else:
                text = str(segment)
                color = defaultColor

            painter.setPen(self._SegmentColor(color))
            painter.drawText(segmentX, baseline, text)
            segmentX += metrics.horizontalAdvance(text)

    def _SegmentColor(self, color):
        if isinstance(color, QtGui.QColor):
            return color
        if isinstance(color, str):
            legacyThemeColors = {
                "#e7e9ee": "OVERLAY_TEXT",
                "#1f1f1f": "OVERLAY_TEXT",
                "#d5a24a": "WARNING",
                "#a86700": "WARNING",
                "#ff5c5c": "ERROR",
                "#b00020": "ERROR",
            }
            if color.lower() in legacyThemeColors:
                return ThemeQColor(legacyThemeColors[color.lower()])
            if color.startswith("#") or color.startswith("rgb"):
                return QtGui.QColor(color)
            return ThemeQColor(color)
        return ThemeQColor("OVERLAY_TEXT")

    def _TintPixmap(self, pixmap, color):
        tinted = QtGui.QPixmap(pixmap.size())
        tinted.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(tinted)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), self._SegmentColor(color))
        painter.end()
        return tinted

    def SetPixmap(self, pixmap, title = None, metadataLines = None):
        self.pixmap = pixmap
        if title is not None:
            self.previewTitle = title
        if metadataLines is not None:
            self.previewMetadata = [line for line in metadataLines if line]
        self._UpdateHoverPixel(self.lastMousePosition)
        self.update()
        self.EmitViewportChanged()

    def Clear(self, text = "Preview"):
        self.pixmap = None
        self.previewTitle = ""
        self.previewMetadata = []
        self.previewWarnings = []
        self.hoverPixel = None
        self.SetNeutralPlaceholder(text)
        self.ResetZoom()

    def ResetZoom(self):
        self.zoom = 1.0
        self.panOffset = QtCore.QPointF(0.0, 0.0)
        self._UpdateHoverPixel(self.lastMousePosition)
        self.update()

    def ZoomBy(self, factor, anchor = None):
        if not self.pixmap or self.pixmap.isNull():
            return

        oldZoom = self.zoom
        self.zoom = max(0.25, min(12.0, self.zoom * float(factor)))
        if self.zoom == oldZoom:
            return

        anchor = QtCore.QPointF(anchor) if anchor is not None else QtCore.QPointF(self.rect().center())
        center = QtCore.QPointF(self.rect().center())
        self.panOffset = anchor - ((anchor - center - self.panOffset) * (self.zoom / oldZoom)) - center
        self._UpdateHoverPixel(self.lastMousePosition)
        self.update()
        self.EmitViewportChanged()

    def wheelEvent(self, event):
        if not self.pixmap or self.pixmap.isNull():
            event.ignore()
            return

        if event.angleDelta().y() > 0:
            factor = 1.15
        else:
            factor = 1.0 / 1.15

        self.ZoomBy(factor, event.position())

        self.lastMousePosition = event.position()
        self._UpdateHoverPixel(event.position())
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self.contextMenuRequested.emit(self, event.globalPosition().toPoint())
            event.accept()
            return

        if (
            self.emptyActionEnabled
            and (not self.pixmap or self.pixmap.isNull())
            and event.button() == QtCore.Qt.MouseButton.LeftButton
        ):
            self.emptyClicked.emit()
            event.accept()
            return

        if not self.pixmap or self.pixmap.isNull():
            super().mousePressEvent(event)
            return

        if event.button() in (QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.MiddleButton):
            self.isPanning = True
            self.panButton = event.button()
            self.lastPanPosition = event.position()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.lastMousePosition = event.position()
        if self.isPanning:
            delta = event.position() - self.lastPanPosition
            self.panOffset += delta
            self.lastPanPosition = event.position()
            self._UpdateHoverPixel(event.position())
            self.update()
            self.EmitViewportChanged()
            event.accept()
            return

        self._UpdateHoverPixel(event.position())
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.isPanning and event.button() == self.panButton:
            self.isPanning = False
            self.panButton = None
            self.unsetCursor()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.ResetZoom()
            self.EmitViewportChanged()
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event):
        self.lastMousePosition = None
        self.hoverPixel = None
        self.update()
        super().leaveEvent(event)

    def _ContentRect(self):
        if self.borderVisible:
            return self.rect().adjusted(1, 1, -1, -1)
        return self.rect()

    def _ImageTargetRect(self, contentRect):
        if not self.pixmap or self.pixmap.isNull():
            return QtCore.QRect()

        width = self.pixmap.width()
        height = self.pixmap.height()
        if width <= 0 or height <= 0:
            return QtCore.QRect()

        fitScale = min(contentRect.width() / width, contentRect.height() / height)
        scale = max(0.01, fitScale * self.zoom)
        targetWidth = max(1, round(width * scale))
        targetHeight = max(1, round(height * scale))
        return QtCore.QRect(
            round(contentRect.center().x() - (targetWidth / 2) + self.panOffset.x()),
            round(contentRect.center().y() - (targetHeight / 2) + self.panOffset.y()),
            targetWidth,
            targetHeight,
        )

    def _UpdateHoverPixel(self, pos):
        self.hoverPixel = None
        if pos is None or not self.pixmap or self.pixmap.isNull():
            return

        targetRect = self._ImageTargetRect(self._ContentRect())
        if targetRect.isNull() or not targetRect.contains(pos.toPoint()):
            return

        xRatio = (pos.x() - targetRect.left()) / targetRect.width()
        yRatio = (pos.y() - targetRect.top()) / targetRect.height()
        x = max(0, min(self.pixmap.width() - 1, int(xRatio * self.pixmap.width())))
        y = max(0, min(self.pixmap.height() - 1, int(yRatio * self.pixmap.height())))
        self.hoverPixel = (x, y)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, self.ViewportBackgroundColor())
        if self.borderVisible:
            painter.setPen(QtGui.QPen(ThemeQColor("FIELD_BG"), 1))
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 5, 5)

        contentRect = self._ContentRect()
        painter.setClipRect(contentRect)

        if not self.pixmap or self.pixmap.isNull():
            if not self.emptyIcon.isNull():
                iconSize = min(116, max(64, min(contentRect.width(), contentRect.height()) // 4))
                iconPixmap = self.emptyIcon.pixmap(iconSize, iconSize)
                if self.emptyColor is not None:
                    iconPixmap = self._TintPixmap(iconPixmap, self.emptyColor)
                iconX = contentRect.center().x() - (iconSize // 2)
                iconY = contentRect.center().y() - iconSize
                painter.setOpacity(0.88 if self.emptyColor is not None else 0.62)
                painter.drawPixmap(iconX, iconY, iconPixmap)
                painter.setOpacity(1.0)
                textRect = QtCore.QRect(
                    contentRect.left(),
                    iconY + iconSize + 12,
                    contentRect.width(),
                    28,
                )
                painter.setPen(self._SegmentColor(self.emptyColor or "PLACEHOLDER_TEXT"))
                painter.drawText(textRect, QtCore.Qt.AlignmentFlag.AlignCenter, self.placeholderText)
            else:
                painter.setPen(ThemeQColor("OVERLAY_TEXT"))
                painter.drawText(contentRect, QtCore.Qt.AlignmentFlag.AlignCenter, self.placeholderText)
            self._DrawOverlay(painter, contentRect)
            return

        targetRect = self._ImageTargetRect(contentRect)
        if targetRect.isNull():
            return

        painter.setRenderHint(
            QtGui.QPainter.RenderHint.SmoothPixmapTransform,
            self.viewportScaling == "Interpolated",
        )
        painter.drawPixmap(targetRect, self.pixmap)
        self._DrawInfoOverlay(painter, contentRect)
        self._DrawOverlay(painter, contentRect)

    def _DrawInfoOverlay(self, painter, contentRect):
        title = self.previewTitle or self.placeholderText
        displayTitle = self.showTitle and bool(title)
        displayWarnings = self.previewWarnings
        displayMetadata = self._VisibleMetadataLines()

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        padding = 8
        spacing = 4
        titleFont = QtGui.QFont(self.font())
        titleFont.setPointSize(titleFont.pointSize() + 3)
        titleFont.setBold(True)
        infoFont = self.font()

        titleMetrics = QtGui.QFontMetrics(titleFont)
        infoMetrics = QtGui.QFontMetrics(infoFont)
        infoParts = []
        if self.hoverPixel:
            coordinateText = f"x: {self.hoverPixel[0]}  y: {self.hoverPixel[1]}"
        else:
            coordinateText = "x: --  y: --"
        if self.showCoordinates:
            infoParts.append(coordinateText)
        if self.showZoom:
            infoParts.append(f"Zoom: {round(self.zoom * 100):d}%")
        infoText = "    ".join(infoParts)
        panDistance = abs(self.panOffset.x()) + abs(self.panOffset.y())
        hintText = "Double click to reset" if abs(self.zoom - 1.0) > 0.001 or panDistance > 0.5 else ""

        lines = []
        if displayTitle:
            lines.append(title)
        lines += displayWarnings
        lines += displayMetadata
        if infoText:
            lines.append(infoText)
        if hintText:
            lines.append(hintText)
        if not lines:
            return

        textWidth = max(
            titleMetrics.horizontalAdvance(title) if displayTitle else 0,
            max((infoMetrics.horizontalAdvance(self._LineText(line)) for line in displayWarnings), default = 0),
            max((infoMetrics.horizontalAdvance(self._LineText(line)) for line in displayMetadata), default = 0),
            infoMetrics.horizontalAdvance(infoText) if infoText else 0,
            infoMetrics.horizontalAdvance(hintText) if hintText else 0,
        )
        infoLineCount = len(displayWarnings) + len(displayMetadata) + (1 if infoText else 0) + (1 if hintText else 0)
        boxHeight = (
            (titleMetrics.height() if displayTitle else 0)
            + (infoMetrics.height() * infoLineCount)
            + (spacing * max(0, len(lines) - 1))
        )
        boxRect = QtCore.QRect(
            contentRect.left() + 12,
            contentRect.top() + 12,
            textWidth + (padding * 2),
            boxHeight + (padding * 2),
        )

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(ThemeQColor("OVERLAY_BG"))
        painter.drawRoundedRect(boxRect, 5, 5)

        x = boxRect.left() + padding
        y = boxRect.top() + padding

        if displayTitle:
            painter.setFont(titleFont)
            painter.setPen(ThemeQColor("OVERLAY_TITLE"))
            painter.drawText(x, y + titleMetrics.ascent(), title)
            y += titleMetrics.height() + spacing

        painter.setFont(infoFont)
        for line in displayWarnings:
            self._DrawLineSegments(painter, x, y + infoMetrics.ascent(), line, ThemeColor("WARNING"))
            y += infoMetrics.height() + spacing

        for line in displayMetadata:
            self._DrawLineSegments(painter, x, y + infoMetrics.ascent(), line, ThemeColor("OVERLAY_TEXT"))
            y += infoMetrics.height() + spacing

        if infoText:
            painter.setPen(ThemeQColor("OVERLAY_TEXT"))
            painter.drawText(x, y + infoMetrics.ascent(), infoText)

        if hintText:
            if infoText:
                y += infoMetrics.height() + spacing
            painter.setPen(ThemeQColor("OVERLAY_TEXT"))
            painter.drawText(x, y + infoMetrics.ascent(), hintText)

    def _DrawOverlay(self, painter, contentRect):
        if not self.overlayLines:
            return

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())
        metrics = QtGui.QFontMetrics(painter.font())
        padding = 8
        spacing = 4
        lineHeight = metrics.height()
        textWidth = max(metrics.horizontalAdvance(line) for line in self.overlayLines)
        boxWidth = textWidth + (padding * 2)
        boxHeight = (lineHeight * len(self.overlayLines)) + (spacing * (len(self.overlayLines) - 1)) + (padding * 2)
        boxRect = QtCore.QRect(
            contentRect.right() - boxWidth - 12,
            contentRect.bottom() - boxHeight - 12,
            boxWidth,
            boxHeight,
        )

        painter.setClipRect(contentRect)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(ThemeQColor("OVERLAY_BG"))
        painter.drawRoundedRect(boxRect, 5, 5)

        painter.setPen(ThemeQColor("OVERLAY_TEXT"))
        y = boxRect.top() + padding + metrics.ascent()
        for line in self.overlayLines:
            painter.drawText(
                QtCore.QRect(boxRect.left() + padding, y - metrics.ascent(), textWidth, lineHeight),
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
                line,
            )
            y += lineHeight + spacing


class FrameScrubber(QtWidgets.QWidget):

    frameChanged = QtCore.Signal(int)
    markRequested = QtCore.Signal(str, int)
    markDragStarted = QtCore.Signal(str)
    markDragEnded = QtCore.Signal()

    HANDLE_WIDTH = 14
    HANDLE_HEIGHT = 18
    MIN_VISIBLE_FRAMES = 30
    HIGHLIGHT_EDGE_HIT_WIDTH = 8

    def __init__(self, parent = None):
        super().__init__(parent)
        self.frameCount = 0
        self.value = 0
        self.viewStart = 0.0
        self.viewEnd = 1.0
        self.highlightStart = None
        self.highlightEnd = None
        self.dragging = False
        self.draggingHighlightEdge = None
        self.panning = False
        self.lastPanX = 0.0
        self.updating = False
        self.fullscreenMode = False
        self.lockedViewRange = None
        self.setMinimumHeight(58)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def SetFullscreenMode(self, enabled):
        self.fullscreenMode = bool(enabled)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, self.fullscreenMode)
        if self.fullscreenMode and self.lockedViewRange is None:
            self.ResetZoom(update = False)
        elif not self.fullscreenMode:
            self.lockedViewRange = None
        self.update()

    def SetFullscreenViewRange(self, start, end):
        if start is None or end is None or self.frameCount <= 0:
            self.lockedViewRange = None
            self.ResetZoom(update = False)
            self.update()
            return

        start = max(0.0, min(float(start), float(max(0, self.frameCount - 1))))
        end = max(0.0, min(float(end), float(max(0, self.frameCount - 1))))
        if start > end:
            start, end = end, start
        self.lockedViewRange = (start, end)
        self.viewStart = start
        self.viewEnd = end
        self.update()

    def SetFrameCount(self, count, resetZoom = True):
        count = max(0, int(count))
        if count == self.frameCount:
            self.SetValue(min(self.value, max(0, count - 1)), emit = False)
            return

        oldValue = self.value
        oldViewStart = self.viewStart
        oldViewEnd = self.viewEnd
        self.frameCount = count
        if not self.fullscreenMode and resetZoom:
            self.ResetZoom(update = False)
            self.SetValue(min(self.value, max(0, count - 1)), emit = False)
        elif not self.fullscreenMode:
            self.value = max(0, min(max(0, count - 1), int(oldValue)))
            self.RestoreViewRange(oldViewStart, oldViewEnd)
        else:
            self.SetValue(min(self.value, max(0, count - 1)), emit = False)
        self.update()

    def RestoreViewRange(self, viewStart, viewEnd):
        if self.frameCount <= 1:
            self.viewStart = 0.0
            self.viewEnd = 1.0
            return

        maxFrame = float(max(1, self.frameCount - 1))
        span = max(1.0, float(viewEnd) - float(viewStart))
        span = min(maxFrame, span)
        self.viewStart = max(0.0, min(float(viewStart), maxFrame - span))
        self.viewEnd = self.viewStart + span

    def SetValue(self, value, emit = False):
        maxValue = max(0, self.frameCount - 1)
        value = max(0, min(maxValue, int(value)))
        changed = value != self.value
        self.value = value
        if not self.fullscreenMode:
            self.EnsureValueVisible()
        self.update()

        if emit and changed and not self.updating:
            self.frameChanged.emit(self.value)

    def SetHighlightRange(self, start, end):
        if start is None or end is None or self.frameCount <= 0:
            self.highlightStart = None
            self.highlightEnd = None
        else:
            self.highlightStart = max(0, min(self.frameCount - 1, int(start)))
            self.highlightEnd = max(0, min(self.frameCount - 1, int(end)))
            if self.highlightStart > self.highlightEnd:
                self.highlightStart, self.highlightEnd = self.highlightEnd, self.highlightStart

        self.update()

    def MinimumVisibleSpan(self):
        return float(min(max(1, self.frameCount - 1), self.MIN_VISIBLE_FRAMES))

    def _TrackRect(self):
        margin = self.HANDLE_WIDTH
        return QtCore.QRectF(
            margin,
            30,
            max(1, self.width() - (margin * 2)),
            20,
        )

    def _PositionFromValue(self, value):
        track = self._TrackRect()
        if self.frameCount <= 1:
            return track.left()

        visibleSpan = max(1e-6, self.viewEnd - self.viewStart)
        ratio = (value - self.viewStart) / visibleSpan
        return track.left() + (track.width() * ratio)

    def _ValueFromPosition(self, x):
        if self.frameCount <= 1:
            return 0

        track = self._TrackRect()
        ratio = (x - track.left()) / track.width()
        ratio = max(0.0, min(1.0, ratio))
        return round(self.viewStart + (ratio * (self.viewEnd - self.viewStart)))

    def FrameAtPosition(self, position):
        return self._ValueFromPosition(position.x())

    def _InputTabActive(self):
        parent = self.window()
        return not hasattr(parent, "viewportTabs") or parent.viewportTabs.currentIndex() == 0

    def _CanEditHighlight(self):
        return (
            self.isEnabled()
            and not self.fullscreenMode
            and self._InputTabActive()
            and self.highlightStart is not None
            and self.highlightEnd is not None
            and self.highlightStart != self.highlightEnd
            and self.frameCount > 0
        )

    def _HighlightEdgeAtPosition(self, position):
        if not self._CanEditHighlight():
            return None

        track = self._TrackRect()
        highlightLeft = max(track.left(), self._PositionFromValue(self.highlightStart))
        highlightRight = min(track.right(), self._PositionFromValue(self.highlightEnd))
        if position.y() < track.top() - 6 or position.y() > track.bottom() + 6:
            return None

        edgeWidth = self.HIGHLIGHT_EDGE_HIT_WIDTH
        leftDistance = abs(position.x() - highlightLeft)
        rightDistance = abs(position.x() - highlightRight)
        if leftDistance <= edgeWidth and leftDistance <= rightDistance:
            return "in"
        if rightDistance <= edgeWidth:
            return "out"
        return None

    def _EmitHighlightEdgeDrag(self, position):
        if not self.draggingHighlightEdge:
            return

        frame = self._ValueFromPosition(position.x())
        self.markRequested.emit(f"drag-{self.draggingHighlightEdge}", frame)

    def ResetZoom(self, update = True):
        self.viewStart = 0.0
        self.viewEnd = float(max(1, self.frameCount - 1))
        if update:
            self.update()

    def EnsureValueVisible(self):
        if self.frameCount <= 1:
            self.ResetZoom(update = False)
            return

        visibleSpan = max(self.MinimumVisibleSpan(), self.viewEnd - self.viewStart)
        maxFrame = self.frameCount - 1
        if self.value < self.viewStart:
            self.viewStart = float(self.value)
            self.viewEnd = self.viewStart + visibleSpan
        elif self.value > self.viewEnd:
            self.viewEnd = float(self.value)
            self.viewStart = self.viewEnd - visibleSpan

        if self.viewStart < 0:
            self.viewStart = 0.0
            self.viewEnd = min(float(maxFrame), self.viewStart + visibleSpan)
        if self.viewEnd > maxFrame:
            self.viewEnd = float(maxFrame)
            self.viewStart = max(0.0, self.viewEnd - visibleSpan)

    def ShiftViewByFrames(self, frameDelta):
        if self.frameCount <= 1:
            return

        visibleSpan = max(self.MinimumVisibleSpan(), self.viewEnd - self.viewStart)
        maxFrame = float(self.frameCount - 1)
        self.viewStart += frameDelta
        self.viewEnd += frameDelta

        if self.viewStart < 0:
            self.viewStart = 0.0
            self.viewEnd = min(maxFrame, visibleSpan)
        if self.viewEnd > maxFrame:
            self.viewEnd = maxFrame
            self.viewStart = max(0.0, self.viewEnd - visibleSpan)

        self.update()

    def ZoomBy(self, factor):
        if self.fullscreenMode or self.frameCount <= 1:
            return

        factor = max(0.05, float(factor))
        center = self.value if self.viewStart <= self.value <= self.viewEnd else (self.viewStart + self.viewEnd) * 0.5
        currentSpan = max(self.MinimumVisibleSpan(), self.viewEnd - self.viewStart)
        maxSpan = float(max(1, self.frameCount - 1))
        newSpan = max(self.MinimumVisibleSpan(), min(maxSpan, currentSpan / factor))
        self.viewStart = center - (newSpan * 0.5)
        self.viewEnd = center + (newSpan * 0.5)

        if self.viewStart < 0:
            self.viewStart = 0.0
            self.viewEnd = min(maxSpan, newSpan)
        if self.viewEnd > maxSpan:
            self.viewEnd = maxSpan
            self.viewStart = max(0.0, self.viewEnd - newSpan)

        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(self.rect())

        if not self.fullscreenMode:
            painter.fillRect(self.rect(), ThemeQColor("SCRUBBER_BG"))
        track = self._TrackRect()

        baseLineY = track.top() + 4
        if not self.fullscreenMode:
            painter.setPen(QtGui.QPen(ThemeQColor("SCRUBBER_LINE"), 1))
            painter.drawLine(QtCore.QPointF(track.left(), baseLineY), QtCore.QPointF(track.right(), baseLineY))

        if (not self.fullscreenMode) and self.highlightStart is not None and self.highlightEnd is not None:
            highlightLeft = max(track.left(), self._PositionFromValue(self.highlightStart))
            highlightRight = min(track.right(), self._PositionFromValue(self.highlightEnd))
            if highlightRight >= highlightLeft:
                highlightRect = QtCore.QRectF(
                    highlightLeft,
                    track.top() + 1,
                    max(1.0, highlightRight - highlightLeft),
                    track.height() - 2,
                )
                painter.setPen(QtGui.QPen(ThemeQColor("OVERLAY_TEXT"), 1))
                highlightColor = ThemeQColor("OVERLAY_TEXT")
                highlightColor.setAlpha(34)
                painter.setBrush(highlightColor)
                painter.drawRoundedRect(highlightRect, 3, 3)
                edgePen = QtGui.QPen(ThemeQColor("OVERLAY_TEXT"), 2)
                painter.setPen(edgePen)
                painter.drawLine(
                    QtCore.QPointF(highlightRect.left(), highlightRect.top() + 3),
                    QtCore.QPointF(highlightRect.left(), highlightRect.bottom() - 3),
                )
                painter.drawLine(
                    QtCore.QPointF(highlightRect.right(), highlightRect.top() + 3),
                    QtCore.QPointF(highlightRect.right(), highlightRect.bottom() - 3),
                )

        if (not self.fullscreenMode) and self.frameCount > 0:
            tickColor = ThemeQColor("SCRUBBER_TICK" if self.isEnabled() else "FIELD_HOVER")
            majorTickColor = ThemeQColor("SCRUBBER_MAJOR_TICK" if self.isEnabled() else "PANEL_BORDER_HOVER")
            textColor = ThemeQColor("OVERLAY_MUTED" if self.isEnabled() else "TEXT_DISABLED")
            visibleStart = max(0, math.floor(self.viewStart))
            visibleEnd = min(self.frameCount - 1, math.ceil(self.viewEnd))
            visibleSpan = max(1.0, self.viewEnd - self.viewStart)
            pixelsPerFrame = track.width() / visibleSpan
            tickStep = max(1, math.ceil(3 / max(0.01, pixelsPerFrame)))
            majorStep = max(tickStep, self._NiceStep(max(1, round(visibleSpan / 10))))
            firstTick = (visibleStart // tickStep) * tickStep

            labelMetrics = QtGui.QFontMetrics(painter.font())
            for frame in range(firstTick, visibleEnd + 1, tickStep):
                x = self._PositionFromValue(frame)
                isMajor = frame % majorStep == 0
                painter.setPen(QtGui.QPen(majorTickColor if isMajor else tickColor, 1))
                tickHeight = 13 if isMajor else 7
                painter.drawLine(QtCore.QPointF(x, baseLineY), QtCore.QPointF(x, baseLineY + tickHeight))

                if isMajor:
                    label = str(frame)
                    labelWidth = labelMetrics.horizontalAdvance(label)
                    labelRect = QtCore.QRectF(x - (labelWidth / 2), 5, labelWidth, 14)
                    if labelRect.left() >= 0 and labelRect.right() <= self.width():
                        painter.setPen(textColor)
                        painter.drawText(labelRect, QtCore.Qt.AlignmentFlag.AlignCenter, label)

        if self.frameCount > 0:
            x = self._PositionFromValue(self.value)
            handleColor = ThemeQColor("SCRUBBER_HANDLE" if self.isEnabled() else "SLIDER_DISABLED")
            handlePen = QtGui.QPen(ThemeQColor("SCRUBBER_HANDLE_BORDER" if self.isEnabled() else "TEXT_DISABLED"), 1)
            painter.setPen(handlePen)
            painter.setBrush(handleColor)

            handleRect = QtCore.QRectF(
                x - (self.HANDLE_WIDTH / 2),
                15,
                self.HANDLE_WIDTH,
                self.HANDLE_HEIGHT,
            )
            painter.drawRoundedRect(handleRect, 4, 4)

            pointer = QtGui.QPainterPath()
            pointer.moveTo(x - 4, handleRect.bottom() - 1)
            pointer.lineTo(x + 4, handleRect.bottom() - 1)
            pointer.lineTo(x, handleRect.bottom() + 5)
            pointer.closeSubpath()
            painter.drawPath(pointer)

            painter.setPen(QtGui.QPen(ThemeQColor("SCRUBBER_HANDLE" if self.isEnabled() else "SLIDER_DISABLED"), 1))
            painter.drawLine(QtCore.QPointF(x, handleRect.bottom() + 5), QtCore.QPointF(x, self.height() - 4))

    def _NiceStep(self, value):
        value = max(1, int(value))
        magnitude = 10 ** int(math.floor(math.log10(value)))
        for multiplier in (1, 2, 5, 10):
            step = magnitude * multiplier
            if step >= value:
                return step
        return magnitude * 10

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            highlightEdge = self._HighlightEdgeAtPosition(event.position())
            if highlightEdge:
                self.draggingHighlightEdge = highlightEdge
                self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
                self.markDragStarted.emit(highlightEdge)
                self._EmitHighlightEdgeDrag(event.position())
                event.accept()
                return

            self.dragging = True
            self.SetValue(self._ValueFromPosition(event.position().x()), emit = True)
            event.accept()
            return

        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            if self.fullscreenMode:
                event.accept()
                return
            self.panning = True
            self.lastPanX = event.position().x()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.draggingHighlightEdge:
            self._EmitHighlightEdgeDrag(event.position())
            event.accept()
            return

        if self.dragging:
            self.SetValue(self._ValueFromPosition(event.position().x()), emit = True)
            event.accept()
            return

        if self.panning:
            trackWidth = max(1.0, self._TrackRect().width())
            deltaPixels = event.position().x() - self.lastPanX
            self.lastPanX = event.position().x()
            visibleSpan = max(self.MinimumVisibleSpan(), self.viewEnd - self.viewStart)
            self.ShiftViewByFrames(-(deltaPixels / trackWidth) * visibleSpan)
            event.accept()
            return

        if self._HighlightEdgeAtPosition(event.position()):
            self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.draggingHighlightEdge and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.draggingHighlightEdge = None
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            self.markDragEnded.emit()
            event.accept()
            return

        if self.dragging and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()
            return

        if self.panning and event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.panning = False
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.frameCount <= 0 or not self.isEnabled():
            event.ignore()
            return

        parent = self.window()
        if hasattr(parent, "viewportTabs") and parent.viewportTabs.currentIndex() != 0:
            event.ignore()
            return

        frame = self.value
        menu = QtWidgets.QMenu(self)
        menu.setObjectName("viewportContextMenu")
        self.AddScrubberMenuButton(menu, SplitAssetIcon("data_array_24dp_E3E3E3.svg", "left"), "Mark In", lambda: self.markRequested.emit("in", frame), shortcutText = "I")
        self.AddScrubberMenuButton(menu, SplitAssetIcon("data_array_24dp_E3E3E3.svg", "right"), "Mark Out", lambda: self.markRequested.emit("out", frame), shortcutText = "O")
        self.AddScrubberMenuButton(menu, "refresh_24dp_E3E3E3.svg", "Clear Range", lambda: self.markRequested.emit("reset", frame), shortcutText = "Alt+X")
        menu.addSeparator()
        self.AddScrubberMenuButton(menu, "zoom_in_24dp_E3E3E3.svg", "Zoom in", lambda: self.ZoomBy(1.25))
        self.AddScrubberMenuButton(menu, "zoom_out_24dp_E3E3E3.svg", "Zoom out", lambda: self.ZoomBy(0.8))
        self.AddScrubberMenuButton(menu, "refresh_24dp_E3E3E3.svg", "Reset zoom", self.ResetZoom)
        menu.exec(event.globalPos())

    def AddScrubberMenuButton(self, menu, icon, text, callback, shortcutText = ""):
        action = QtWidgets.QWidgetAction(menu)
        button = QtWidgets.QPushButton()
        button.setObjectName("viewportMenuItem")
        button.setFlat(True)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setMinimumWidth(250)
        row = QtWidgets.QHBoxLayout(button)
        row.setContentsMargins(12, 0, 14, 0)
        row.setSpacing(14)

        menuIcon = icon if isinstance(icon, QtGui.QIcon) else AssetIcon(icon)
        iconLabel = QtWidgets.QLabel()
        iconLabel.setObjectName("menuIconLabel")
        iconLabel.setFixedSize(18, 18)
        iconLabel.setPixmap(menuIcon.pixmap(18, 18))
        iconLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        textLabel = QtWidgets.QLabel(text)
        textLabel.setObjectName("menuTextLabel")
        textLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        shortcutLabel = QtWidgets.QLabel(shortcutText)
        shortcutLabel.setObjectName("menuShortcutLabel")
        shortcutLabel.setMinimumWidth(24)
        shortcutLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        shortcutLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        row.addWidget(iconLabel, 0)
        row.addWidget(textLabel, 0)
        row.addStretch(1)
        row.addWidget(shortcutLabel, 0)

        def Trigger():
            menu.hide()
            callback()

        button.clicked.connect(Trigger)
        action.setDefaultWidget(button)
        menu.addAction(action)
        return button

    def mouseDoubleClickEvent(self, event):
        if self.fullscreenMode:
            event.accept()
            return

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.ResetZoom()
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        if self.fullscreenMode:
            event.accept()
            return

        if self.frameCount <= 1:
            event.accept()
            return

        oldStart = self.viewStart
        oldEnd = self.viewEnd
        oldSpan = max(self.MinimumVisibleSpan(), oldEnd - oldStart)
        zoomFactor = 0.8 if event.angleDelta().y() > 0 else 1.25
        newSpan = max(self.MinimumVisibleSpan(), min(float(self.frameCount - 1), oldSpan * zoomFactor))

        anchorFrame = self._ValueFromPosition(event.position().x())
        anchorRatio = (event.position().x() - self._TrackRect().left()) / max(1.0, self._TrackRect().width())
        anchorRatio = max(0.0, min(1.0, anchorRatio))

        self.viewStart = float(anchorFrame) - (newSpan * anchorRatio)
        self.viewEnd = self.viewStart + newSpan

        maxFrame = float(self.frameCount - 1)
        if self.viewStart < 0:
            self.viewStart = 0.0
            self.viewEnd = newSpan
        if self.viewEnd > maxFrame:
            self.viewEnd = maxFrame
            self.viewStart = max(0.0, self.viewEnd - newSpan)

        self.update()
        event.accept()

    def leaveEvent(self, event):
        if not self.dragging and not self.draggingHighlightEdge and not self.panning:
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        super().leaveEvent(event)


class ViewportOverlay(QtWidgets.QWidget):

    def __init__(self, contentWidget, overlayWidget, parent = None):
        super().__init__(parent)
        self.contentWidget = contentWidget
        self.overlayWidget = overlayWidget
        self.rightOverlayWidget = None
        self.bottomOverlayWidget = None
        self.overlayMargin = 12

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(contentWidget)

        self.overlayWidget.setParent(self)
        self.overlayWidget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.overlayWidget.raise_()

    def SetRightOverlay(self, widget):
        self.rightOverlayWidget = widget
        self.rightOverlayWidget.setParent(self)
        self.rightOverlayWidget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.rightOverlayWidget.raise_()
        self.PositionOverlay()

    def SetBottomOverlay(self, widget):
        self.bottomOverlayWidget = widget
        self.bottomOverlayWidget.setParent(self)
        self.bottomOverlayWidget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.bottomOverlayWidget.raise_()
        self.PositionOverlay()

    def ClearBottomOverlay(self):
        self.bottomOverlayWidget = None
        self.PositionOverlay()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.PositionOverlay()

    def PositionOverlay(self):
        self.overlayWidget.adjustSize()
        size = self.overlayWidget.sizeHint()
        x = max(0, (self.width() - size.width()) // 2)
        bottomOverlayHeight = 0
        if self.bottomOverlayWidget is not None:
            bottomOverlayHeight = max(self.bottomOverlayWidget.sizeHint().height(), self.bottomOverlayWidget.minimumHeight())
        y = max(0, self.height() - size.height() - bottomOverlayHeight - self.overlayMargin)
        self.overlayWidget.setGeometry(x, y, size.width(), size.height())
        self.overlayWidget.raise_()

        if self.rightOverlayWidget is not None:
            self.rightOverlayWidget.adjustSize()
            rightSize = self.rightOverlayWidget.sizeHint()
            rightWidth = max(rightSize.width(), self.rightOverlayWidget.width())
            rightHeight = max(rightSize.height(), self.rightOverlayWidget.height())
            rightX = max(0, self.width() - rightWidth - self.overlayMargin)
            rightY = self.overlayMargin + 28
            self.rightOverlayWidget.setGeometry(rightX, rightY, rightWidth, rightHeight)
            self.rightOverlayWidget.raise_()

        if self.bottomOverlayWidget is not None:
            bottomHeight = max(self.bottomOverlayWidget.sizeHint().height(), self.bottomOverlayWidget.minimumHeight())
            bottomY = max(0, self.height() - bottomHeight)
            self.bottomOverlayWidget.setGeometry(0, bottomY, self.width(), bottomHeight)
            self.bottomOverlayWidget.raise_()


def ConfigureFormLayout(layout):
    layout.setHorizontalSpacing(14)
    layout.setVerticalSpacing(10)
    layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    layout.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)


def CheckboxField(checkbox):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(0)
    layout.addWidget(checkbox, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    layout.addStretch(1)
    return widget


def LabeledSuffixField(widgetToLabel, suffix):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(widgetToLabel)
    layout.addWidget(QtWidgets.QLabel(suffix))
    layout.addStretch(1)
    return widget


def InlineSpinField(prefix, spinBox, suffix):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(QtWidgets.QLabel(prefix))
    layout.addWidget(spinBox)
    layout.addWidget(QtWidgets.QLabel(suffix))
    layout.addStretch(1)
    return widget


def ResolutionField(widthSpinBox, heightSpinBox):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(widthSpinBox)
    layout.addWidget(QtWidgets.QLabel("x"))
    layout.addWidget(heightSpinBox)
    layout.addStretch(1)
    return widget


def OverrideField(fieldWidget, checkbox):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    layout.addWidget(fieldWidget, 1)
    layout.addWidget(checkbox, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    return widget


def SectionHeading(text):
    label = QtWidgets.QLabel(text)
    label.setStyleSheet("font-size: 11pt; font-weight: 700; padding-top: 4px; padding-bottom: 4px;")

    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    line.setObjectName("sectionHeadingLine")

    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    layout.addWidget(label)
    layout.addWidget(line, 1)
    return widget


def IconButtonText(text):
    return f"  {text}"


def SliderSpinBoxField(slider, spinBox):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(slider, 1)
    layout.addWidget(spinBox)
    return widget


def ButtonComboField(comboBox, button):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(comboBox, 1)
    layout.addWidget(button)
    return widget
def OutputNameTypeField(nameField, typeComboBox, optionsButton):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    dotLabel = QtWidgets.QLabel("_000x.")
    dotLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    widget.sequenceSuffixLabel = dotLabel
    nameField.setMinimumWidth(120)
    typeComboBox.setMinimumWidth(76)
    typeComboBox.setMaximumWidth(120)

    layout.addWidget(nameField, 1)
    layout.addWidget(dotLabel)
    layout.addWidget(typeComboBox, 0)
    layout.addWidget(optionsButton)
    return widget
