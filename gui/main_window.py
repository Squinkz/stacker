import os
import re
import html
import threading
from collections import OrderedDict

from PySide6 import QtCore, QtGui, QtWidgets

from .config import BLEND_MODES, INPUT_TYPES, OUTPUT_TYPES
from .metadata import (
    DimensionsLine, IsUnknownTransferFunction, ReadImageDimensions, ReadImageMetadata,
    TransferFunctionLine, TransferOverrideLine,
)
from .resources import (
    AppRoot, AssetIcon, BuildStyle, SplitAssetIcon,
    StatusAssetIcon, ThemeAboutLogoPath, ThemeAppIconPath, ThemeAssetPath, ThemeBaseName, ThemeColor,
    ThemeDisplayNames, ThemeName, ThemeQColor,
)
from .widgets import (
    ButtonComboField, CheckboxField, ClickDismissFilter, ConfigureFormLayout, ContextSubmenuController, FolderField,
    DownwardComboBox, FloatSlider, IconButtonText, OverrideField,
    OutputNameTypeField, RangeField, ResolutionField, RightAlignedMenuToolButton, SectionHeading,
    SliderSpinBoxField, ViewportOverlay, PreviewPane, FrameScrubber,
)
from .presets import PresetMixin
from .project import ProjectMixin
from .worker import RenderWorker
from render.renderer import CanonicalFileType, FileTypeExtensions, ResizeFilterNames, TransferFunctionNames

APP_NAME = "Stacker"
APP_VERSION = "0.1.0"
APP_RELEASE_DATE = "Unreleased"
APP_COPYRIGHT = "2026 Dieter Stassen"
APP_DESCRIPTION = (
    "Stacker blends image sequences into trails, motion effects, and experimental composites; "
    "from classic star trails to motion extraction and fixed-length stack blends."
)
APP_GITHUB_URL = "https://github.com/Squinkz"
APP_ISSUES_URL = "https://github.com/Squinkz/stacker/issues"
FILE_INFO_DIALOG_WIDTH = 640
FILE_INFO_VALUE_WIDTH = 430


from .file_list import (
    ACTIVE_ROLE, ENTRY_ID_ROLE, FILENAME_ROLE,
    InputFileListDelegate, InputFileListModel, InputFileListView,
)


class MainWindow(PresetMixin, ProjectMixin, QtWidgets.QMainWindow):
    IO_LABEL_WIDTH = 112
    BLEND_LABEL_WIDTH = 92

    def __init__(self):
        super().__init__()

        self.thread = None
        self.worker = None
        self.cancelEvent = None
        self.pauseEvent = None
        self.previewPixmap = None
        self.currentRunIsPreview = False
        self.pendingExportAfterCancel = False
        self.quitAfterRenderCancel = False
        self.renderQuitDialog = None
        self.renderLogDialog = None
        self.renderLogText = None
        self.renderLogLines = []
        self.runActive = False
        self.activeSettings = None
        self.currentProjectPath = None
        self.projectDirty = False
        self.suppressProjectDirty = True
        self.suppressUndoCapture = False
        self.pendingUndoTransactionSnapshot = None
        self.lastProjectSnapshot = None
        self.undoKeyWidgets = set()
        self.spinBoxUndoWidgets = set()
        self.spinBoxMouseUndoActive = False
        self.pendingUndoSection = None
        self.undoSectionBySnapshotKey = {}
        self.undoStack = []
        self.redoStack = []
        self.undoStackLimit = 100
        self.cleanProjectSnapshot = None
        self.lastProjectPresetIdentity = None
        self.exportMode = "sequence"
        self.stackMemoryExceeded = False
        self.inputFileEntries = []
        self.nextInputEntryId = 1
        self.inputPreviewFilenames = []
        self.disabledInputFilenames = set()
        self.removedInputFilenames = set()
        self.missingInputFilenames = set()
        self.rescaleWarningInputFilenames = set()
        self.transferWarningInputFilenames = set()
        self.inputDimensionCache = {}
        self.inputMetadataCache = {}
        self.inputHasMixedDimensions = False
        self.previewRangeStopWhileDragging = False
        self.scrubberTrimDragStartRange = None
        self.suppressRangePreview = False
        self.suppressInputFileSelectionSync = False
        self.inputSyncSuspendedByViewport = False
        self.inputSyncRestoreChecked = False
        self.renderSyncPreviousChecked = False
        self.renderSyncActive = False
        self.activeRenderEntryIds = []
        self.lastInputBrowserDirectory = ""
        self.fileListContextEntryId = None
        self.pendingInputFileListRow = None
        self.pendingInputFileListScroll = None
        self.pendingInputSelectionEntryIds = None
        self.removePendingEventFilterActive = False
        self.currentInputPreviewFile = None
        self.currentInputPreviewEntryId = None
        self.manualInputViewportEntryId = None
        self.currentOutputPreviewFile = None
        self.previewCache = []
        self.previewDecodedCache = OrderedDict()
        self.currentPreviewCacheIndex = None
        self.previewCacheBytes = 0
        self.previewCacheLimitReached = False
        self.currentRenderFrame = 0
        self.currentRenderFrameCount = 0
        self.previewFrameCount = "range"
        self.overlayShowDimensions = False
        self.overlayShowColorSpace = False
        self.overlayShowCoordinates = True
        self.overlayShowZoom = True
        self.overlayShowFrameIndex = True
        self.overlayShowImageIndex = True
        self.viewportBackgroundOverride = None
        self.viewportOnlyMode = False
        self.savedSplitterSizes = None
        self.scrubberPlaybackTimer = QtCore.QTimer(self)
        self.scrubberPlaybackTimer.timeout.connect(self.AdvanceScrubberPlayback)

        self.setWindowTitle("Stacker")
        self._BuildUi()
        self.UpdateScrubberPlaybackInterval()
        self._BuildShortcuts()
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.LoadUiConfig()
        self.UpdateInputSyncForViewportTab()
        self.ConnectProjectDirtySignals()
        self.suppressProjectDirty = False
        self.ResetUndoHistory(clean = not self.projectDirty)
        self.UpdateProjectTitle()
        self.statusBar().hide()

    def _BuildShortcuts(self):
        self.previousFrameShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Left), self)
        self.previousFrameShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.previousFrameShortcut.activated.connect(lambda: self.StepActiveFrame(-1, wrap = True))

        self.nextFrameShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Right), self)
        self.nextFrameShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.nextFrameShortcut.activated.connect(lambda: self.StepActiveFrame(1, wrap = True))

        self.fullscreenShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F11), self)
        self.fullscreenShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.fullscreenShortcut.activated.connect(self.ToggleViewportOnlyMode)

        self.fullscreenLetterShortcut = QtGui.QShortcut(QtGui.QKeySequence("F"), self)
        self.fullscreenLetterShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.fullscreenLetterShortcut.activated.connect(self.ToggleViewportOnlyMode)

        self.playbackShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Space), self)
        self.playbackShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.playbackShortcut.activated.connect(self.ToggleScrubberPlayback)

        self.markInShortcut = QtGui.QShortcut(QtGui.QKeySequence("I"), self)
        self.markInShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.markInShortcut.activated.connect(lambda: self.MarkCurrentScrubberFrame("in"))

        self.markOutShortcut = QtGui.QShortcut(QtGui.QKeySequence("O"), self)
        self.markOutShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.markOutShortcut.activated.connect(lambda: self.MarkCurrentScrubberFrame("out"))

        self.resetRangeShortcut = QtGui.QShortcut(QtGui.QKeySequence("Alt+X"), self)
        self.resetRangeShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.resetRangeShortcut.activated.connect(self.ResetTrimRange)

        self.undoShortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Undo, self)
        self.undoShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.undoShortcut.activated.connect(self.UndoProjectAction)

        self.redoShortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Z"), self)
        self.redoShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.redoShortcut.activated.connect(self.RedoProjectAction)

        self.startPreviewShortcut = QtGui.QShortcut(QtGui.QKeySequence("F4"), self)
        self.startPreviewShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.startPreviewShortcut.activated.connect(self.StartPreview)

        self.startExportShortcut = QtGui.QShortcut(QtGui.QKeySequence("F5"), self)
        self.startExportShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.startExportShortcut.activated.connect(self.StartExport)

        self.liveExportPreviewShortcut = QtGui.QShortcut(QtGui.QKeySequence("F9"), self)
        self.liveExportPreviewShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.liveExportPreviewShortcut.activated.connect(self.ToggleLiveExportPreview)

        self.openLogShortcut = QtGui.QShortcut(QtGui.QKeySequence("F10"), self)
        self.openLogShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.openLogShortcut.activated.connect(self.OpenRenderLogFile)

        self.showConsoleShortcut = QtGui.QShortcut(QtGui.QKeySequence("F12"), self)
        self.showConsoleShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.showConsoleShortcut.activated.connect(self.ShowRenderLog)

        self.viewSelectedInputFileShortcut = QtGui.QShortcut(QtGui.QKeySequence("V"), self)
        self.viewSelectedInputFileShortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self.viewSelectedInputFileShortcut.activated.connect(self.ViewSelectedInputFileFromShortcut)

    def eventFilter(self, watched, event):
        sidebarScrollPages = getattr(self, "sidebarScrollPages", {})
        if watched in sidebarScrollPages and event.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
            self.SyncSidebarScrollPageWidth(watched)

        if event.type() == QtCore.QEvent.Type.KeyPress and self.HandleTabShortcut(event):
            return True

        if watched in getattr(self, "spinBoxUndoWidgets", set()) and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            self.spinBoxMouseUndoActive = True
            self.BeginUndoTransaction()

        if (
            getattr(self, "spinBoxMouseUndoActive", False)
            and event.type() in (
                QtCore.QEvent.Type.MouseButtonRelease,
                QtCore.QEvent.Type.MouseButtonDblClick,
                QtCore.QEvent.Type.FocusOut,
                QtCore.QEvent.Type.WindowDeactivate,
            )
        ):
            QtCore.QTimer.singleShot(0, self.EndSpinBoxMouseUndoTransaction)

        if watched in getattr(self, "undoKeyWidgets", set()) and event.type() == QtCore.QEvent.Type.KeyPress:
            modifiers = event.modifiers()
            if event.key() == QtCore.Qt.Key.Key_Z and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
                if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.RedoProjectAction()
                else:
                    self.UndoProjectAction()
                event.accept()
                return True

        if (
            self.removePendingEventFilterActive
            and event.type() in (
                QtCore.QEvent.Type.MouseButtonRelease,
                QtCore.QEvent.Type.MouseButtonDblClick,
                QtCore.QEvent.Type.WindowDeactivate,
                QtCore.QEvent.Type.FocusOut,
            )
        ):
            QtCore.QTimer.singleShot(0, self._ClearPendingInputRemoveIfCancelled)

        if watched is getattr(self, "removeInputFileButton", None):
            if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                QtCore.QTimer.singleShot(0, self._ClearPendingInputRemoveIfCancelled)

        if watched in (
            getattr(self, "inputViewport", None),
            getattr(self, "inputFileList", None),
            getattr(getattr(self, "inputFileList", None), "viewport", lambda: None)(),
        ):
            if event.type() == QtCore.QEvent.Type.DragEnter:
                if self.InputDropHasSupportedPaths(event.mimeData()):
                    event.acceptProposedAction()
                    return True
            elif event.type() == QtCore.QEvent.Type.DragMove:
                if self.InputDropHasSupportedPaths(event.mimeData()):
                    event.acceptProposedAction()
                    return True
            elif event.type() == QtCore.QEvent.Type.Drop:
                if self.AddDroppedInputPaths(event.mimeData()):
                    event.acceptProposedAction()
                    return True

        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if self.runActive and event.key() == QtCore.Qt.Key.Key_Escape:
            self.CancelRender()
            event.accept()
            return

        if self.viewportOnlyMode and event.key() in (
            QtCore.Qt.Key.Key_Escape,
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
        ):
            self.SetViewportOnlyMode(False)
            event.accept()
            return

        super().keyPressEvent(event)

    def _BuildUi(self):
        root = QtWidgets.QWidget()
        mainLayout = QtWidgets.QHBoxLayout(root)
        self.mainLayout = mainLayout
        mainLayout.setContentsMargins(12, 12, 12, 12)
        mainLayout.setSpacing(0)

        self._BuildAdvancedPanel()

        sidebar = self._BuildSidebar()
        runGroup = self._BuildRunGroup()
        runGroup.setMinimumWidth(160)

        self.mainSplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.mainSplitter.setChildrenCollapsible(False)
        self.mainSplitter.setHandleWidth(8)
        self.mainSplitter.addWidget(runGroup)
        self.mainSplitter.addWidget(sidebar)
        self.mainSplitter.setStretchFactor(0, 1)
        self.mainSplitter.setStretchFactor(1, 0)
        self.mainSplitter.setSizes([1600, self.defaultSidebarWidth])
        self.mainSplitter.splitterMoved.connect(self.SidebarSplitterMoved)
        self.UpdateSidebarWidthLimits()

        mainLayout.addWidget(self.mainSplitter)
        self.setCentralWidget(root)

        self.settingsWidgets = [
            self.inputDirectory,
            self.addInputFileButton,
            self.sortInputFilesButton,
            self.sortInputFilesNumericButton,
            self.syncInputSelectionButton,
            self.markInputInButton,
            self.markInputOutButton,
            self.clearInputRangeButton,
            self.moveInputFileUpButton,
            self.moveInputFileDownButton,
            self.removeInputFileButton,
            self.removeAllInputFilesButton,
            self.inputFileList,
            self.skipInput,
            self.reverseInput,
            self.presetComboBox,
            self.savePresetButton,
            self.renderPathMode0,
            self.renderPathMode1,
            self.renderPathMode2,
            self.pairBlurSlider,
            self.pairBlurSpinBox,
            self.pairBlurKernel,
            self.stackSizeSlider,
            self.stackSizeSpinBox,
            self.stackDirection,
            self.blendScaleSlider,
            self.blendScaleSpinBox,
            self.blendOffsetSlider,
            self.blendOffsetSpinBox,
            self.absoluteValues,
            self.blendMode,
            self.decay,
            self.opacity,
            self.outputDirectory,
            self.outputFileName,
            self.outputFileType,
            self.outputOptionsButton,
            self.jpgQuality,
            self.jpgQualitySpinBox,
            self.jpgOptimize,
            self.jpgProgressive,
            self.jpgSubsampling,
            self.pngCompressLevel,
            self.pngCompressLevelSpinBox,
            self.pngOptimize,
            self.tiffCompression,
            self.rangeField,
            self.skipOutput,
            self.overrideInputTransfer,
            self.inputTransferFunction,
            self.overrideOutputTransfer,
            self.outputTransferFunction,
            self.overrideResolution,
            self.blendInLinear,
            self.useCustomMiddleGray,
            self.middleGray,
            self.middleGrayResetButton,
            self.viewportScaling,
            self.resizeFilter,
            self.overrideWidth,
            self.overrideHeight,
            self.previewCacheLimit,
            self.previewEnabled,
            self.previewScale,
            self.previewFps,
            self.themeSelector,
            self.viewportBackgroundSlider,
            self.viewportBackgroundSpinBox,
            self.viewportBackgroundResetButton,
        ]

        self.RefreshInputFileState()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.UpdateSidebarWidthLimits()

    def UpdateSidebarWidthLimits(self):
        if not hasattr(self, "sidebarPanel"):
            return

        windowWidth = self.WindowContentWidth()
        maximumWidth = max(self.sidebarMinimumWidth, round(windowWidth * self.sidebarMaximumRatio))
        self.sidebarPanel.setMinimumWidth(self.sidebarMinimumWidth)
        self.sidebarPanel.setMaximumWidth(16777215)

        if hasattr(self, "mainSplitter"):
            sizes = self.mainSplitter.sizes()
            if len(sizes) >= 2 and sizes[1] > maximumWidth:
                self.mainSplitter.setSizes([max(160, self.mainSplitter.width() - maximumWidth), maximumWidth])

    def WindowContentWidth(self):
        central = self.centralWidget()
        width = central.width() if central is not None else self.width()
        if width <= 0:
            width = self.width()
        return max(1, width)

    def SidebarSplitterMoved(self, *_):
        if not hasattr(self, "mainSplitter"):
            return

        availableWidth = max(1, self.mainSplitter.width())
        maximumWidth = max(self.sidebarMinimumWidth, round(self.WindowContentWidth() * self.sidebarMaximumRatio))
        sizes = self.mainSplitter.sizes()
        if len(sizes) < 2:
            return

        sidebarWidth = max(self.sidebarMinimumWidth, min(maximumWidth, sizes[1]))
        if sidebarWidth != sizes[1]:
            self.mainSplitter.setSizes([max(160, availableWidth - sidebarWidth), sidebarWidth])

    def _BuildAdvancedPanel(self):
        self.advancedPanel = QtWidgets.QDialog(self)
        self.advancedPanel.setWindowTitle("Settings")
        self.advancedPanel.setModal(False)

        layout = QtWidgets.QVBoxLayout(self.advancedPanel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.skipInput = QtWidgets.QSpinBox()
        self.skipInput.setRange(1, 999999)
        self.skipInput.setValue(1)
        self.skipInput.setSuffix(" frame(s)")
        self.skipInput.valueChanged.connect(self.RefreshInputFileState)

        self.skipOutput = QtWidgets.QSpinBox()
        self.skipOutput.setRange(1, 999999)
        self.skipOutput.setValue(1)
        self.skipOutput.setSuffix(" frame(s)")
        self.skipOutput.valueChanged.connect(self.UpdateOutputSequenceSuffixLabel)

        overridesForm = QtWidgets.QFormLayout()
        ConfigureFormLayout(overridesForm)

        self.overrideInputTransfer = QtWidgets.QCheckBox("Override")
        self.inputTransferFunction = DownwardComboBox()
        self._AddTransferFunctionItems(self.inputTransferFunction)
        self._SetTransferFunctionValue(self.inputTransferFunction, "sRGB / Display P3")

        self.overrideOutputTransfer = QtWidgets.QCheckBox("Override")
        self.outputTransferFunction = DownwardComboBox()
        self._AddTransferFunctionItems(self.outputTransferFunction)
        self._SetTransferFunctionValue(self.outputTransferFunction, "sRGB / Display P3")

        self.overrideResolution = QtWidgets.QCheckBox("Override")
        self.viewportScaling = DownwardComboBox()
        self.viewportScaling.addItems(["Interpolated", "Nearest"])
        self.viewportScaling.setCurrentText("Interpolated")
        self.viewportScaling.currentTextChanged.connect(self.UpdateViewportScaling)
        self.playbackFps = QtWidgets.QSpinBox()
        self.playbackFps.setRange(1, 120)
        self.playbackFps.setValue(30)
        self.playbackFps.setSuffix(" fps")
        self.playbackFps.valueChanged.connect(self.UpdateScrubberPlaybackInterval)
        self.playbackFpsResetButton = QtWidgets.QPushButton()
        self.playbackFpsResetButton.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        self.playbackFpsResetButton.setToolTip("Reset playback FPS")
        self.playbackFpsResetButton.setFixedWidth(34)
        self.playbackFpsResetButton.clicked.connect(self.ResetPlaybackFps)
        self.previewFpsResetButton = QtWidgets.QPushButton()
        self.previewFpsResetButton.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        self.previewFpsResetButton.setToolTip("Reset update frequency")
        self.previewFpsResetButton.setFixedWidth(34)
        self.previewFpsResetButton.clicked.connect(self.ResetPreviewFps)
        self.resizeFilter = DownwardComboBox()
        self.resizeFilter.addItems(ResizeFilterNames())
        self.resizeFilter.setCurrentText("Lanczos")
        self.overrideWidth = QtWidgets.QSpinBox()
        self.overrideWidth.setRange(1, 99999)
        self.overrideWidth.setValue(1920)
        self.overrideHeight = QtWidgets.QSpinBox()
        self.overrideHeight.setRange(1, 99999)
        self.overrideHeight.setValue(1080)
        self.previewCacheLimit = QtWidgets.QSpinBox()
        self.previewCacheLimit.setRange(128, 65536)
        self.previewCacheLimit.setSingleStep(128)
        self.previewCacheLimit.setValue(2048)
        self.previewCacheLimit.setSuffix(" MB")
        self.blendInLinear = QtWidgets.QCheckBox("Blend using linear light")
        self.blendInLinear.setChecked(True)
        self.useCustomMiddleGray = QtWidgets.QCheckBox("Override")
        self.middleGray = FloatSlider(0.5, decimals = 3)
        self.middleGrayResetButton = QtWidgets.QPushButton()
        self.middleGrayResetButton.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        self.middleGrayResetButton.setToolTip("Reset middle gray")
        self.middleGrayResetButton.setFixedWidth(34)
        self.middleGrayResetButton.clicked.connect(self.ResetMiddleGray)
        self.themeSelector = DownwardComboBox()
        self.themeSelector.addItems(ThemeDisplayNames())
        self.themeSelector.setCurrentText("Dark Ice")
        self.themeSelector.currentTextChanged.connect(self.SetTheme)
        self.viewportBackgroundSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.viewportBackgroundSlider.setRange(0, 255)
        self.viewportBackgroundSlider.setMinimumHeight(26)
        self.viewportBackgroundSpinBox = QtWidgets.QSpinBox()
        self.viewportBackgroundSpinBox.setRange(0, 255)
        self.viewportBackgroundSpinBox.setFixedWidth(72)
        self.viewportBackgroundResetButton = QtWidgets.QPushButton()
        self.viewportBackgroundResetButton.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        self.viewportBackgroundResetButton.setToolTip("Reset viewport background")
        self.viewportBackgroundResetButton.setFixedWidth(34)
        self.viewportBackgroundResetButton.clicked.connect(self.ResetViewportBackground)
        self.viewportBackgroundSlider.valueChanged.connect(self.viewportBackgroundSpinBox.setValue)
        self.viewportBackgroundSpinBox.valueChanged.connect(self.viewportBackgroundSlider.setValue)
        self.viewportBackgroundSpinBox.valueChanged.connect(self.ViewportBackgroundValueChanged)

        self.overrideInputTransfer.toggled.connect(self.UpdateTransferOverrideControls)
        self.overrideInputTransfer.toggled.connect(self.UpdateEffectiveOverrideValues)
        self.overrideInputTransfer.toggled.connect(self.UpdateRangePreview)
        self.inputTransferFunction.currentIndexChanged.connect(self.UpdateEffectiveOverrideValues)
        self.inputTransferFunction.currentIndexChanged.connect(self.UpdateRangePreview)
        self.overrideOutputTransfer.toggled.connect(self.UpdateTransferOverrideControls)
        self.overrideOutputTransfer.toggled.connect(self.UpdateEffectiveOverrideValues)
        self.overrideResolution.toggled.connect(self.UpdateTransferOverrideControls)
        self.overrideResolution.toggled.connect(self.UpdateEffectiveOverrideValues)
        self.overrideResolution.toggled.connect(self.RefreshExportResolutionWarnings)
        self.overrideWidth.valueChanged.connect(self.RefreshExportResolutionWarnings)
        self.overrideHeight.valueChanged.connect(self.RefreshExportResolutionWarnings)
        self.blendInLinear.toggled.connect(self.UpdateTransferOverrideControls)
        self.blendInLinear.toggled.connect(self.UpdateEffectiveOverrideValues)
        self.blendInLinear.toggled.connect(self.RefreshInputTransferWarnings)
        self.blendInLinear.toggled.connect(self.RefreshInputFileList)
        self.blendInLinear.toggled.connect(self.RefreshInputPreviewMetadata)
        self.useCustomMiddleGray.toggled.connect(self.CustomMiddleGrayToggled)
        self.middleGray.valueChanged.connect(self.UpdateMiddleGrayControls)

        overridesForm.addRow("Viewport Scaling", self.viewportScaling)
        playbackField = QtWidgets.QWidget()
        playbackLayout = QtWidgets.QHBoxLayout(playbackField)
        playbackLayout.setContentsMargins(0, 0, 0, 0)
        playbackLayout.setSpacing(8)
        playbackLayout.addWidget(self.playbackFps)
        playbackLayout.addWidget(self.playbackFpsResetButton)
        playbackLayout.addStretch(1)
        overridesForm.addRow("Playback", playbackField)
        self.middleGrayField = QtWidgets.QWidget()
        middleGrayLayout = QtWidgets.QHBoxLayout(self.middleGrayField)
        middleGrayLayout.setContentsMargins(0, 0, 0, 0)
        middleGrayLayout.setSpacing(8)
        middleGrayLayout.addWidget(self.middleGray, 1)
        middleGrayLayout.addWidget(self.middleGrayResetButton)
        systemForm = QtWidgets.QFormLayout()
        ConfigureFormLayout(systemForm)
        systemForm.addRow("Theme", self.themeSelector)
        viewportBackgroundField = QtWidgets.QWidget()
        viewportBackgroundLayout = QtWidgets.QHBoxLayout(viewportBackgroundField)
        viewportBackgroundLayout.setContentsMargins(0, 0, 0, 0)
        viewportBackgroundLayout.setSpacing(8)
        viewportBackgroundLayout.addWidget(SliderSpinBoxField(self.viewportBackgroundSlider, self.viewportBackgroundSpinBox), 1)
        viewportBackgroundLayout.addWidget(self.viewportBackgroundResetButton)
        systemForm.addRow("Viewport Color", viewportBackgroundField)
        previewForm = QtWidgets.QFormLayout()
        ConfigureFormLayout(previewForm)
        self._BuildPreviewControls(previewForm)
        previewForm.addRow("Preview Cache Limit", self.previewCacheLimit)

        closeButton = QtWidgets.QPushButton("Close")
        closeButton.clicked.connect(self.advancedPanel.hide)

        buttonLayout = QtWidgets.QHBoxLayout()
        buttonLayout.addStretch(1)
        buttonLayout.addWidget(closeButton)

        layout.addWidget(SectionHeading("Viewport", "crop_3_2_24dp_E3E3E3.svg"))
        layout.addLayout(overridesForm)
        layout.addSpacing(8)
        layout.addWidget(SectionHeading("Preview", "visibility_24dp_E3E3E3.svg"))
        layout.addLayout(previewForm)
        layout.addSpacing(8)
        layout.addWidget(SectionHeading("Appearance", "palette_24dp_E3E3E3.svg"))
        layout.addLayout(systemForm)
        layout.addLayout(buttonLayout)
        self.UpdateTransferOverrideControls()
        self.UpdateMiddleGrayControls()
        self.SyncViewportBackgroundControls()
        self.advancedPanel.resize(460, 430)

    def _BuildOutputOptionsPanel(self):
        self.outputOptionsPanel = QtWidgets.QDialog(self)
        self.outputOptionsPanel.setWindowTitle("File Export Options")
        self.outputOptionsPanel.setModal(False)

        layout = QtWidgets.QVBoxLayout(self.outputOptionsPanel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.outputOptionsStack = QtWidgets.QStackedWidget()
        self.outputOptionsPages = {}

        self._AddJpgOptionsPage()
        self._AddPngOptionsPage()
        self._AddTiffOptionsPage()
        self._AddBmpOptionsPage()

        closeButton = QtWidgets.QPushButton("Close")
        closeButton.clicked.connect(self.outputOptionsPanel.hide)

        buttonLayout = QtWidgets.QHBoxLayout()
        buttonLayout.addStretch(1)
        buttonLayout.addWidget(closeButton)

        layout.addWidget(self.outputOptionsStack)
        layout.addLayout(buttonLayout)
        self.outputOptionsPanel.resize(420, 240)
        self.UpdateOutputOptionsPanel()

    def _AddOutputOptionsPage(self, fileType, widget):
        self.outputOptionsPages[fileType] = self.outputOptionsStack.addWidget(widget)

    def _AddJpgOptionsPage(self):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        ConfigureFormLayout(form)

        self.jpgQuality = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.jpgQuality.setRange(1, 100)
        self.jpgQualitySpinBox = QtWidgets.QSpinBox()
        self.jpgQualitySpinBox.setRange(1, 100)
        self.jpgQualitySpinBox.setFixedWidth(72)
        self.jpgQuality.valueChanged.connect(self.jpgQualitySpinBox.setValue)
        self.jpgQualitySpinBox.valueChanged.connect(self.jpgQuality.setValue)
        self.jpgQuality.setValue(95)

        self.jpgOptimize = QtWidgets.QCheckBox()
        self.jpgProgressive = QtWidgets.QCheckBox()

        self.jpgSubsampling = DownwardComboBox()
        self.jpgSubsampling.addItem("Default", None)
        self.jpgSubsampling.addItem("4:4:4", 0)
        self.jpgSubsampling.addItem("4:2:2", 1)
        self.jpgSubsampling.addItem("4:2:0", 2)

        form.addRow("Quality", SliderSpinBoxField(self.jpgQuality, self.jpgQualitySpinBox))
        form.addRow("Optimize", CheckboxField(self.jpgOptimize))
        form.addRow("Progressive", CheckboxField(self.jpgProgressive))
        form.addRow("Subsampling", self.jpgSubsampling)
        self._AddOutputOptionsPage("jpg", page)

    def _AddPngOptionsPage(self):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        ConfigureFormLayout(form)

        self.pngCompressLevel = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.pngCompressLevel.setRange(0, 9)
        self.pngCompressLevelSpinBox = QtWidgets.QSpinBox()
        self.pngCompressLevelSpinBox.setRange(0, 9)
        self.pngCompressLevelSpinBox.setFixedWidth(72)
        self.pngCompressLevel.valueChanged.connect(self.pngCompressLevelSpinBox.setValue)
        self.pngCompressLevelSpinBox.valueChanged.connect(self.pngCompressLevel.setValue)
        self.pngCompressLevel.setValue(6)

        self.pngOptimize = QtWidgets.QCheckBox()

        form.addRow("Compression", SliderSpinBoxField(self.pngCompressLevel, self.pngCompressLevelSpinBox))
        form.addRow("Optimize", CheckboxField(self.pngOptimize))
        self._AddOutputOptionsPage("png", page)

    def _AddTiffOptionsPage(self):
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        ConfigureFormLayout(form)

        self.tiffCompression = DownwardComboBox()
        self.tiffCompression.addItem("None", None)
        self.tiffCompression.addItem("LZW", "tiff_lzw")
        self.tiffCompression.addItem("Deflate", "tiff_adobe_deflate")
        self.tiffCompression.addItem("PackBits", "packbits")
        self.tiffCompression.addItem("JPEG", "jpeg")

        form.addRow("Compression", self.tiffCompression)
        self._AddOutputOptionsPage("tiff", page)

    def _AddBmpOptionsPage(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QtWidgets.QLabel("No common Pillow save options for BMP export.")
        label.setWordWrap(True)
        label.setStyleSheet("color: #e7e9ee; font-style: italic;")
        layout.addWidget(label)
        layout.addStretch(1)
        self._AddOutputOptionsPage("bmp", page)

    def _BuildSidebar(self):
        sidebar = QtWidgets.QWidget()
        self.sidebarMinimumWidth = 300
        self.defaultSidebarWidth = max(self.sidebarMinimumWidth, 500)
        self.sidebarMaximumRatio = 0.8
        self.sidebarPanel = sidebar
        sidebar.setMinimumWidth(self.sidebarMinimumWidth)
        sidebar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)

        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.advancedButton = QtWidgets.QPushButton()
        self.advancedButton.setObjectName("settingsButton")
        self.advancedButton.setIcon(AssetIcon("settings_24dp_E3E3E3.svg"))
        self.advancedButton.setToolTip("Settings")
        self.advancedButton.setFixedWidth(34)
        self.advancedButton.clicked.connect(self.OpenAdvancedPanel)

        self.helpButton = QtWidgets.QPushButton()
        self.helpButton.setObjectName("settingsButton")
        self.helpButton.setIcon(AssetIcon("help_24dp_E3E3E3.svg"))
        self.helpButton.setToolTip("Help")
        self.helpButton.setFixedWidth(34)
        self.helpButton.setCheckable(True)
        self.helpButton.clicked.connect(self.ShowHelpMenu)

        self.fileMenuButton = QtWidgets.QPushButton()
        self.fileMenuButton.setObjectName("settingsButton")
        self.fileMenuButton.setIcon(AssetIcon("insert_drive_file_24dp_E3E3E3.svg"))
        self.fileMenuButton.setToolTip("File")
        self.fileMenuButton.setFixedWidth(34)
        self.fileMenuButton.setCheckable(True)
        self.fileMenuButton.clicked.connect(self.ShowFileMenu)

        self.editMenuButton = QtWidgets.QPushButton()
        self.editMenuButton.setObjectName("settingsButton")
        self.editMenuButton.setIcon(AssetIcon("edit_24dp_E3E3E3.svg"))
        self.editMenuButton.setToolTip("Edit")
        self.editMenuButton.setFixedWidth(34)
        self.editMenuButton.setCheckable(True)
        self.editMenuButton.clicked.connect(self.ShowEditMenu)

        self.visibilityMenuButton = QtWidgets.QPushButton()
        self.visibilityMenuButton.setObjectName("settingsButton")
        self.visibilityMenuButton.setIcon(AssetIcon("visibility_24dp_E3E3E3.svg"))
        self.visibilityMenuButton.setToolTip("Viewport labels")
        self.visibilityMenuButton.setFixedWidth(34)
        self.visibilityMenuButton.setCheckable(True)
        self.visibilityMenuButton.clicked.connect(self.ShowVisibilityMenu)

        self.stackerTextLogo = QtWidgets.QPushButton()
        self.stackerTextLogo.setObjectName("stackerTextLogoButton")
        self.stackerTextLogo.setFixedSize(128, 32)
        self.stackerTextLogo.setIconSize(QtCore.QSize(128, 32))
        self.stackerTextLogo.setToolTip("About Stacker")
        self.stackerTextLogo.clicked.connect(self.ShowAboutDialog)

        self.fileMenu = QtWidgets.QMenu(self.fileMenuButton)
        self.fileMenu.setObjectName("viewportContextMenu")
        self.newProjectButton = self.AddHeaderMenuButton(self.fileMenu, "file_new_24dp_E3E3E3.svg", "New Project", "Ctrl + N")
        self.openProjectButton = self.AddHeaderMenuButton(self.fileMenu, "file_open_24dp_E3E3E3.svg", "Open Project", "Ctrl + O")
        self.fileMenu.addSeparator()
        self.saveProjectButton = self.AddHeaderMenuButton(self.fileMenu, "save_24dp_E3E3E3.svg", "Save Project", "Ctrl + S")
        self.saveProjectAsButton = self.AddHeaderMenuButton(self.fileMenu, "save_as_24dp_E3E3E3.svg", "Save Project as", "Ctrl + Shift + S")
        self.fileMenu.addSeparator()
        self.closeProjectButton = self.AddHeaderMenuButton(self.fileMenu, "close_24dp_E3E3E3.svg", "Close Project", "Ctrl + W")
        self.newProjectButton.clicked.connect(self.CloseProject)
        self.openProjectButton.clicked.connect(self.OpenProjectFile)
        self.saveProjectButton.clicked.connect(self.SaveProject)
        self.closeProjectButton.clicked.connect(self.CloseProject)
        self.saveProjectAsButton.clicked.connect(self.SaveProjectAs)
        QtGui.QShortcut(QtGui.QKeySequence.StandardKey.New, self, self.CloseProject)
        QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Open, self, self.OpenProjectFile)
        QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Save, self, self.SaveProject)
        QtGui.QShortcut(QtGui.QKeySequence.StandardKey.SaveAs, self, self.SaveProjectAs)
        QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Close, self, self.CloseProject)
        self.copyViewportShortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Copy, self)
        self.copyViewportShortcut.activated.connect(self.CopyActiveViewportToClipboard)
        self.fileMenu.aboutToShow.connect(lambda: self.SetFileMenuButtonOpen(True))
        self.fileMenu.aboutToHide.connect(lambda: self.SetFileMenuButtonOpen(False))

        self.editMenu = QtWidgets.QMenu(self.editMenuButton)
        self.editMenu.setObjectName("viewportContextMenu")
        self.undoMenuButton = self.AddHeaderMenuButton(self.editMenu, "undo_24dp_E3E3E3.svg", "Undo", "Ctrl + Z")
        self.redoMenuButton = self.AddHeaderMenuButton(self.editMenu, "redo_24dp_E3E3E3.svg", "Redo", "Ctrl + Shift + Z")
        self.editMenu.addSeparator()
        self.copyViewportButton = self.AddHeaderMenuButton(self.editMenu, "content_copy_24dp_E3E3E3.svg", "Copy image", "Ctrl + C")
        self.undoMenuButton.clicked.connect(self.UndoProjectAction)
        self.redoMenuButton.clicked.connect(self.RedoProjectAction)
        self.copyViewportButton.clicked.connect(self.CopyActiveViewportToClipboard)
        self.editMenu.aboutToShow.connect(lambda: self.SetEditMenuButtonOpen(True))
        self.editMenu.aboutToShow.connect(self.RefreshEditMenuState)
        self.editMenu.aboutToHide.connect(lambda: self.SetEditMenuButtonOpen(False))

        self.visibilityMenu = QtWidgets.QMenu(self.visibilityMenuButton)
        self.visibilityMenu.setObjectName("viewportContextMenu")
        self.visibilityMenu.aboutToShow.connect(lambda: self.SetVisibilityMenuButtonOpen(True))
        self.visibilityMenu.aboutToHide.connect(lambda: self.SetVisibilityMenuButtonOpen(False))

        self.helpMenu = QtWidgets.QMenu(self.helpButton)
        self.helpMenu.setObjectName("viewportContextMenu")
        self.helpMenuHelpButton = self.AddHeaderMenuButton(self.helpMenu, "help_24dp_E3E3E3.svg", "Help", "")
        self.helpMenu.addSeparator()
        self.helpMenuAboutButton = self.AddHeaderMenuButton(self.helpMenu, "info_24dp_E3E3E3.svg", "About", "")
        self.helpMenuAboutButton.clicked.connect(self.ShowAboutDialog)
        self.helpMenu.aboutToShow.connect(lambda: self.SetHelpMenuButtonOpen(True))
        self.helpMenu.aboutToHide.connect(lambda: self.SetHelpMenuButtonOpen(False))

        sidebarHeader = QtWidgets.QWidget()
        sidebarHeaderLayout = QtWidgets.QHBoxLayout(sidebarHeader)
        sidebarHeaderLayout.setContentsMargins(0, 0, 0, 0)
        sidebarHeaderLayout.setSpacing(6)
        sidebarHeaderLayout.addWidget(self.fileMenuButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        sidebarHeaderLayout.addWidget(self.editMenuButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        sidebarHeaderLayout.addWidget(self.visibilityMenuButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        sidebarHeaderLayout.addWidget(self.advancedButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        sidebarHeaderLayout.addWidget(self.helpButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        sidebarHeaderLayout.addStretch(1)
        sidebarHeaderLayout.addWidget(self.stackerTextLogo, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        self.RefreshStackerTextLogo()
        layout.addWidget(sidebarHeader, 0)

        self.sidebarTabs = QtWidgets.QTabWidget()
        self.sidebarTabs.addTab(self.SidebarScrollPage(self._BuildInputGroup()), "Images")
        self.sidebarTabs.addTab(self.SidebarScrollPage(self._BuildBlendGroup()), "Blend")
        self.sidebarTabs.addTab(self.SidebarScrollPage(self._BuildOutputGroup()), "Export")
        self.sidebarTabs.setIconSize(QtCore.QSize(18, 18))
        self.RefreshSidebarTabIcons()

        layout.addWidget(self.sidebarTabs, 1)
        layout.addWidget(self._BuildRenderActionFooter(), 0)

        return sidebar

    def SidebarScrollPage(self, page):
        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setObjectName("sidebarScrollPage")
        scrollArea.setWidgetResizable(True)
        scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scrollArea.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scrollArea.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Ignored)
        scrollArea.setMinimumHeight(0)
        page.setMinimumWidth(0)
        page.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
        scrollArea.setWidget(page)
        self.sidebarScrollPages = getattr(self, "sidebarScrollPages", {})
        self.sidebarScrollPages[scrollArea.viewport()] = page
        scrollArea.viewport().installEventFilter(self)
        QtCore.QTimer.singleShot(0, lambda viewport = scrollArea.viewport(): self.SyncSidebarScrollPageWidth(viewport))
        return scrollArea

    def SyncSidebarScrollPageWidth(self, viewport):
        page = getattr(self, "sidebarScrollPages", {}).get(viewport)
        if page is None:
            return
        width = max(1, viewport.width())
        if page.width() != width:
            page.setFixedWidth(width)

    def AddHeaderMenuButton(self, menu, iconName, text, shortcutText):
        action = QtWidgets.QWidgetAction(menu)
        button = QtWidgets.QPushButton()
        button.setObjectName("headerMenuItem")
        button.setFlat(True)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setMinimumWidth(300)
        button.iconName = iconName

        row = QtWidgets.QHBoxLayout(button)
        row.setContentsMargins(12, 0, 14, 0)
        row.setSpacing(14)

        iconLabel = QtWidgets.QLabel()
        iconLabel.setObjectName("menuIconLabel")
        iconLabel.setFixedSize(18, 18)
        iconLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        button.iconLabel = iconLabel

        textLabel = QtWidgets.QLabel(text)
        textLabel.setObjectName("menuTextLabel")
        textLabel.setMinimumWidth(126)
        textLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        button.textLabel = textLabel

        shortcutLabel = QtWidgets.QLabel(shortcutText)
        shortcutLabel.setObjectName("menuShortcutLabel")
        shortcutLabel.setMinimumWidth(96)
        shortcutLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        shortcutLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        button.shortcutLabel = shortcutLabel

        row.addWidget(iconLabel, 0)
        row.addWidget(textLabel, 0)
        row.addStretch(1)
        row.addWidget(shortcutLabel, 0)

        self.RefreshHeaderMenuButtonIcon(button)

        button.clicked.connect(menu.hide)
        action.setDefaultWidget(button)
        menu.addAction(action)
        return button

    def SetHeaderMenuButtonSoftEnabled(self, button, enabled):
        enabled = bool(enabled)
        if button.isEnabled() == enabled and bool(button.property("softDisabled")) == (not enabled):
            return

        button.setEnabled(enabled)
        button.setProperty("softDisabled", not enabled)
        button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor if enabled else
            QtCore.Qt.CursorShape.ArrowCursor
        )
        button.style().unpolish(button)
        button.style().polish(button)
        for label in (getattr(button, "textLabel", None), getattr(button, "shortcutLabel", None)):
            if label is None:
                continue
            label.setProperty("softDisabled", not enabled)
            label.style().unpolish(label)
            label.style().polish(label)
        self.RefreshHeaderMenuButtonIcon(button)

    def ConnectProjectDirtySignals(self):
        trackedSignals = (
            (self.skipInput.valueChanged, "Images"),
            (self.rangeField.valuesChanged, "Images"),
            (self.overrideInputTransfer.toggled, "Images"),
            (self.inputTransferFunction.currentIndexChanged, "Images"),
            (self.blendMode.currentIndexChanged, "Blend"),
            (self.decay.valueChanged, "Blend"),
            (self.pairDistanceSpinBox.valueChanged, "Blend"),
            (self.pairBlurSpinBox.valueChanged, "Blend"),
            (self.pairBlurKernel.currentTextChanged, "Blend"),
            (self.stackSizeSpinBox.valueChanged, "Blend"),
            (self.stackDirection.currentTextChanged, "Blend"),
            (self.blendScaleSpinBox.valueChanged, "Blend"),
            (self.blendOffsetSpinBox.valueChanged, "Blend"),
            (self.absoluteValues.toggled, "Blend"),
            (self.opacity.valueChanged, "Blend"),
            (self.outputDirectory.textChanged, "Export"),
            (self.outputFileName.textChanged, "Export"),
            (self.outputFileType.currentTextChanged, "Export"),
            (self.skipOutput.valueChanged, "Export"),
            (self.resizeFilter.currentTextChanged, "Export"),
            (self.overrideResolution.toggled, "Export"),
            (self.overrideWidth.valueChanged, "Export"),
            (self.overrideHeight.valueChanged, "Export"),
            (self.outputTransferFunction.currentIndexChanged, "Export"),
            (self.blendInLinear.toggled, "Export"),
            (self.useCustomMiddleGray.toggled, "Export"),
            (self.middleGray.valueChanged, "Export"),
            (self.overrideOutputTransfer.toggled, "Export"),
            (self.previewEnabled.toggled, "Export"),
            (self.jpgQuality.valueChanged, "Export"),
            (self.jpgOptimize.toggled, "Export"),
            (self.jpgProgressive.toggled, "Export"),
            (self.jpgSubsampling.currentIndexChanged, "Export"),
            (self.pngCompressLevel.valueChanged, "Export"),
            (self.pngOptimize.toggled, "Export"),
            (self.tiffCompression.currentIndexChanged, "Export"),
        )
        for signal, section in trackedSignals:
            signal.connect(lambda *args, section = section: self.MarkProjectDirty(section = section))

        dragTrackedSliders = (
            self.decay.slider,
            self.opacity.slider,
            self.middleGray.slider,
            self.pairDistanceSlider,
            self.pairBlurSlider,
            self.stackSizeSlider,
            self.blendScaleSlider,
            self.blendOffsetSlider,
            self.jpgQuality,
            self.pngCompressLevel,
        )
        for slider in dragTrackedSliders:
            slider.sliderPressed.connect(self.BeginUndoTransaction)
            slider.sliderReleased.connect(self.EndUndoTransaction)
        for spinBox in self.ProjectUndoSpinBoxes():
            spinBox.editingFinished.connect(self.MarkProjectDirty)
            self.RegisterUndoKeyWidget(spinBox)
            self.RegisterSpinBoxUndoWidget(spinBox)
            lineEdit = spinBox.lineEdit() if hasattr(spinBox, "lineEdit") else None
            if lineEdit is not None:
                self.RegisterUndoKeyWidget(lineEdit)
                self.RegisterSpinBoxUndoWidget(lineEdit)
            undoShortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Undo, spinBox)
            undoShortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            undoShortcut.activated.connect(self.UndoProjectAction)
            redoShortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Z"), spinBox)
            redoShortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            redoShortcut.activated.connect(self.RedoProjectAction)
            spinBox.undoShortcut = undoShortcut
            spinBox.redoShortcut = redoShortcut
        self.rangeField.handleDragStarted.connect(self.BeginUndoTransaction)
        self.rangeField.handleDragEnded.connect(self.EndUndoTransaction)
        self.frameScrubber.markDragStarted.connect(self.BeginUndoTransaction)
        self.frameScrubber.markDragEnded.connect(self.EndUndoTransaction)

    def RegisterUndoKeyWidget(self, widget):
        widget.installEventFilter(self)
        self.undoKeyWidgets.add(widget)

    def RegisterSpinBoxUndoWidget(self, widget):
        widget.installEventFilter(self)
        self.spinBoxUndoWidgets.add(widget)

    def EndSpinBoxMouseUndoTransaction(self):
        if not self.spinBoxMouseUndoActive:
            return

        self.spinBoxMouseUndoActive = False
        self.EndUndoTransaction()

    def ProjectUndoSpinBoxes(self):
        return (
            self.skipInput,
            self.rangeField.startSpinBox,
            self.rangeField.stopSpinBox,
            self.overrideWidth,
            self.overrideHeight,
            self.middleGray.spinBox,
            self.decay.spinBox,
            self.pairDistanceSpinBox,
            self.pairBlurSpinBox,
            self.stackSizeSpinBox,
            self.blendScaleSpinBox,
            self.blendOffsetSpinBox,
            self.opacity.spinBox,
            self.skipOutput,
            self.jpgQualitySpinBox,
            self.pngCompressLevelSpinBox,
        )

    def ShowFileMenu(self):
        self.SetFileMenuButtonOpen(True)
        self.RefreshFileMenuState()
        menuPosition = QtCore.QPoint(0, self.fileMenuButton.height())
        self.fileMenu.popup(self.fileMenuButton.mapToGlobal(menuPosition))

    def RefreshFileMenuState(self):
        hasClosableProject = bool(self.currentProjectPath or self.projectDirty)
        self.SetHeaderMenuButtonSoftEnabled(
            self.newProjectButton,
            hasClosableProject,
        )
        self.SetHeaderMenuButtonSoftEnabled(
            self.closeProjectButton,
            hasClosableProject,
        )

    def ShowEditMenu(self):
        self.SetEditMenuButtonOpen(True)
        self.RefreshEditMenuState()
        menuPosition = QtCore.QPoint(0, self.editMenuButton.height())
        self.editMenu.popup(self.editMenuButton.mapToGlobal(menuPosition))

    def RefreshEditMenuState(self):
        if hasattr(self, "copyViewportButton"):
            self.SetHeaderMenuButtonSoftEnabled(self.copyViewportButton, self.ActiveViewportHasImage())

    def ShowVisibilityMenu(self):
        self.SetVisibilityMenuButtonOpen(True)
        self.visibilityMenu.clear()
        self.AddViewportSubmenuButton(
            self.visibilityMenu,
            "crop_3_2_24dp_E3E3E3.svg",
            "Viewport",
            lambda childMenu: self.PopulateViewportShowMenu(childMenu, self.ActiveViewport(), self.visibilityMenu),
            itemKind = "header",
        )
        self.visibilityMenu.addSeparator()
        iconName = "check_24dp_E3E3E3.svg" if self.previewEnabled.isChecked() else ""
        actionButton = self.AddHeaderMenuButton(self.visibilityMenu, iconName, "Live Export Preview", "F9")
        actionButton.setEnabled(self.previewEnabled.isEnabled())
        actionButton.clicked.connect(self.ToggleLiveExportPreview)
        self.visibilityMenu.addSeparator()
        logButton = self.AddHeaderMenuButton(self.visibilityMenu, "log_24dp_E3E3E3.svg", "Open Log", "F10")
        self.SetHeaderMenuButtonSoftEnabled(logButton, self.RenderLogFileExists())
        logButton.clicked.connect(self.OpenRenderLogFile)
        consoleButton = self.AddHeaderMenuButton(self.visibilityMenu, "terminal_24dp_E3E3E3.svg", "Open Console", "F12")
        consoleButton.clicked.connect(self.ShowRenderLog)
        self.visibilityMenu.addSeparator()
        resetInterfaceButton = self.AddHeaderMenuButton(self.visibilityMenu, "refresh_24dp_E3E3E3.svg", "Reset Interface", "")
        resetInterfaceButton.clicked.connect(self.ResetInterfaceSettings)
        menuPosition = QtCore.QPoint(0, self.visibilityMenuButton.height())
        self.visibilityMenu.popup(self.visibilityMenuButton.mapToGlobal(menuPosition))

    def ToggleLiveExportPreview(self):
        if not hasattr(self, "previewEnabled") or not self.previewEnabled.isEnabled():
            return
        self.previewEnabled.setChecked(not self.previewEnabled.isChecked())

    def ResetInterfaceSettings(self):
        if self.runActive:
            return

        self.themeSelector.setCurrentText("Dark Ice")
        self.SetTheme("Dark Ice")
        self.viewportBackgroundOverride = None
        self.SyncViewportBackgroundControls()
        self.ApplyViewportBackground()

        self.overlayShowDimensions = False
        self.overlayShowColorSpace = False
        self.overlayShowCoordinates = True
        self.overlayShowZoom = True
        self.overlayShowFrameIndex = True
        self.overlayShowImageIndex = True
        self.UpdateViewportInfoVisibility()
        self.UpdatePreviewOverlay()

        self.viewportScaling.setCurrentText("Interpolated")
        self.UpdateViewportScaling()
        self.playbackFps.setValue(30)
        self.previewScale.setCurrentIndex(1)
        self.previewFps.setValue(1.0)
        self.SetPreviewFrameCount("range")
        self.previewCacheLimit.setValue(2048)
        self.UpdateScrubberPlaybackInterval()
        self.UpdatePreviewOptionsEnabled()
        self.SyncActivePreviewSettings()
        self.ResetInterfaceViewState()

        self.RestoreSidebarWidth(self.defaultSidebarWidth)
        self.SaveUiConfig()

    def ResetInterfaceViewState(self):
        viewports = (
            getattr(self, "inputViewport", None),
            getattr(self, "previewViewport", None),
            getattr(self, "outputViewport", None),
        )
        for viewport in viewports:
            if viewport is not None:
                viewport.ResetZoom()

        if getattr(self, "inputViewport", None) is not None:
            self.inputViewport.EmitViewportChanged()

        if hasattr(self, "frameScrubber"):
            self.frameScrubber.ResetZoom()
            if getattr(self, "viewportOnlyMode", False):
                self.UpdateFullscreenScrubberView()

    def RenderLogFilePath(self):
        if not hasattr(self, "outputDirectory"):
            return ""

        directory = self.outputDirectory.Text()
        if not directory:
            return ""
        return os.path.join(directory, "log.log")

    def RenderLogFileExists(self):
        path = self.RenderLogFilePath()
        return bool(path and os.path.isfile(path))

    def OpenRenderLogFile(self):
        path = self.RenderLogFilePath()
        if not path or not os.path.isfile(path):
            return False

        return QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def ShowRenderLog(self):
        if self.renderLogDialog is None:
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("Console")
            dialog.setWindowIcon(QtGui.QIcon(ThemeAppIconPath(ThemeName())))
            dialog.setModal(False)
            dialog.setWindowFlags(
                dialog.windowFlags()
                | QtCore.Qt.WindowType.WindowMinimizeButtonHint
                | QtCore.Qt.WindowType.WindowMaximizeButtonHint
            )
            dialog.resize(760, 420)

            layout = QtWidgets.QVBoxLayout(dialog)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            self.renderLogText = QtWidgets.QPlainTextEdit()
            self.renderLogText.setReadOnly(True)
            self.renderLogText.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
            self.RefreshRenderLogTheme()
            font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
            self.renderLogText.setFont(font)
            self.renderLogText.setPlainText("\n".join(self.renderLogLines))
            layout.addWidget(self.renderLogText, 1)

            buttonRow = QtWidgets.QHBoxLayout()
            buttonRow.addStretch(1)
            clearButton = QtWidgets.QPushButton("Clear")
            clearButton.clicked.connect(self.ClearRenderLog)
            closeButton = QtWidgets.QPushButton("Close")
            closeButton.clicked.connect(dialog.close)
            buttonRow.addWidget(clearButton)
            buttonRow.addWidget(closeButton)
            layout.addLayout(buttonRow)

            dialog.finished.connect(self.RenderLogDialogClosed)
            self.renderLogDialog = dialog

        self.renderLogDialog.show()
        self.renderLogDialog.raise_()
        self.renderLogDialog.activateWindow()
        QtCore.QTimer.singleShot(0, self.ScrollRenderLogToBottom)

    def RenderLogDialogClosed(self, *_):
        self.renderLogDialog = None
        self.renderLogText = None

    def RefreshRenderLogTheme(self):
        if self.renderLogText is None:
            return

        if self.renderLogDialog is not None:
            self.renderLogDialog.setWindowIcon(QtGui.QIcon(ThemeAppIconPath(ThemeName())))

        consoleBackground = ThemeColor("CONSOLE_BG")
        self.renderLogText.setStyleSheet(
            f"QPlainTextEdit {{ background: {consoleBackground}; border: 1px solid {consoleBackground}; }}"
        )

    def RefreshLicensesTheme(self):
        if getattr(self, "licensesText", None) is None:
            return

        consoleBackground = ThemeColor("CONSOLE_BG")
        self.licensesText.setStyleSheet(
            f"QPlainTextEdit {{ background: {consoleBackground}; border: 1px solid {consoleBackground}; }}"
        )

    def ClearRenderLog(self):
        self.renderLogLines = []
        if self.renderLogText is not None:
            self.renderLogText.clear()

    def AppendRenderLog(self, message):
        message = str(message)
        self.renderLogLines.append(message)
        if len(self.renderLogLines) > 5000:
            self.renderLogLines = self.renderLogLines[-5000:]
        if self.renderLogText is not None:
            self.renderLogText.appendPlainText(message)
            self.ScrollRenderLogToBottom()

    def ScrollRenderLogToBottom(self):
        if self.renderLogText is None:
            return

        scrollbar = self.renderLogText.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.renderLogText.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def ShowHelpMenu(self):
        self.SetHelpMenuButtonOpen(True)
        menuPosition = QtCore.QPoint(0, self.helpButton.height())
        self.helpMenu.popup(self.helpButton.mapToGlobal(menuPosition))

    def _BuildRenderActionFooter(self):
        footer = QtWidgets.QWidget()
        footer.setObjectName("renderActionFooter")
        layout = QtWidgets.QVBoxLayout(footer)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        self.previewButton = RightAlignedMenuToolButton()
        self.previewButton.setObjectName("previewButton")
        self.previewButton.setIcon(AssetIcon("play_arrow_24dp_E3E3E3.svg"))
        self.previewButton.setIconSize(QtCore.QSize(24, 24))
        self.previewButton.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.previewButton.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.previewButton.SetPopupAbove(True)
        self.previewButton.clicked.connect(self.StartPreview)

        self.previewFrameMenu = QtWidgets.QMenu(self.previewButton)
        self.previewFrameMenu.setObjectName("footerActionMenu")
        self.previewFrameActions = {}
        for frameCount in (50, 100, 250, 500):
            action = self._AddRightAlignedMenuButton(
                self.previewFrameMenu,
                f"{frameCount} Frames",
                lambda count = frameCount: self.SetPreviewFrameCount(count),
            )
            self.previewFrameActions[frameCount] = action
        rangeAction = self._AddRightAlignedMenuButton(
            self.previewFrameMenu,
            "Trim Range",
            lambda: self.SetPreviewFrameCount("range"),
        )
        self.previewFrameActions["range"] = rangeAction

        self.previewButton.setMenu(self.previewFrameMenu)
        self.previewFrameMenu.setMinimumWidth(210)
        self.SetPreviewFrameCount(self.previewFrameCount)

        self.exportButton = RightAlignedMenuToolButton()
        self.exportButton.setObjectName("exportButton")
        self.exportButton.setIcon(AssetIcon("save_alt_24dp_E3E3E3.svg"))
        self.exportButton.setIconSize(QtCore.QSize(24, 24))
        self.exportButton.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.exportButton.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.exportButton.SetPopupAbove(True)
        self.exportButton.clicked.connect(self.StartExport)

        self.exportModeMenu = QtWidgets.QMenu(self.exportButton)
        self.exportModeMenu.setObjectName("footerActionMenu")
        self.exportSequenceAction = self._AddRightAlignedMenuButton(
            self.exportModeMenu,
            "Export Sequence",
            lambda: self.SetExportMode("sequence"),
        )
        self.exportFinalBlendAction = self._AddRightAlignedMenuButton(
            self.exportModeMenu,
            "Export Final Blend Only",
            lambda: self.SetExportMode("final"),
        )
        self.exportButton.setMenu(self.exportModeMenu)
        self.exportModeMenu.setMinimumWidth(210)
        self.SetExportMode("sequence")

        self.cancelButton = QtWidgets.QPushButton(IconButtonText("Stop"))
        self.cancelButton.setObjectName("cancelButton")
        self.cancelButton.setIcon(AssetIcon("stop_24dp_E3E3E3.svg"))
        self.cancelButton.setIconSize(QtCore.QSize(24, 24))
        self.cancelButton.setEnabled(False)
        self.cancelButton.clicked.connect(self.CancelRender)

        actionRow = QtWidgets.QHBoxLayout()
        actionRow.setContentsMargins(0, 0, 0, 0)
        actionRow.setSpacing(8)
        actionRow.addWidget(self.previewButton, 1)
        actionRow.addWidget(self.exportButton, 1)

        for button in (self.previewButton, self.exportButton, self.cancelButton):
            button.setFixedHeight(38)
            button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        actionPage = QtWidgets.QWidget()
        actionPage.setLayout(actionRow)

        stopPage = QtWidgets.QWidget()
        stopLayout = QtWidgets.QVBoxLayout(stopPage)
        stopLayout.setContentsMargins(0, 0, 0, 0)
        stopLayout.setSpacing(0)
        stopLayout.addWidget(self.cancelButton)

        self.renderButtonStack = QtWidgets.QStackedWidget()
        self.renderButtonStack.addWidget(actionPage)
        self.renderButtonStack.addWidget(stopPage)
        layout.addWidget(self.renderButtonStack)

        return footer

    def _AddRightAlignedMenuButton(self, menu, text, callback):
        action = QtWidgets.QWidgetAction(menu)
        button = QtWidgets.QPushButton(text)
        button.setObjectName("footerMenuItem")
        button.setCheckable(True)
        button.setFlat(True)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setMinimumWidth(210)
        button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        button.setStyleSheet("text-align: right;")

        def Trigger():
            menu.hide()
            callback()

        button.clicked.connect(Trigger)
        action.setDefaultWidget(button)
        menu.addAction(action)
        return button

    def SetTheme(self, themeName):
        themeName = str(themeName or "dark_ice").lower()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.setStyleSheet(BuildStyle(themeName))
            app.setWindowIcon(QtGui.QIcon(ThemeAppIconPath(themeName)))
        self.setWindowIcon(QtGui.QIcon(ThemeAppIconPath(themeName)))
        self.viewportBackgroundOverride = None
        self.SyncViewportBackgroundControls()
        self.ApplyViewportBackground()
        self.RefreshRenderLogTheme()
        self.RefreshLicensesTheme()
        self.RefreshThemeIcons()

    def DefaultViewportBackgroundValue(self):
        color = ThemeQColor("VIEWPORT_BG")
        return round((color.red() * 0.299) + (color.green() * 0.587) + (color.blue() * 0.114))

    def EffectiveViewportBackgroundValue(self):
        if self.viewportBackgroundOverride is None:
            return self.DefaultViewportBackgroundValue()
        return self.viewportBackgroundOverride

    def SyncViewportBackgroundControls(self):
        if not hasattr(self, "viewportBackgroundSlider"):
            return

        value = self.EffectiveViewportBackgroundValue()
        self.viewportBackgroundSlider.blockSignals(True)
        self.viewportBackgroundSpinBox.blockSignals(True)
        self.viewportBackgroundSlider.setValue(value)
        self.viewportBackgroundSpinBox.setValue(value)
        self.viewportBackgroundSlider.blockSignals(False)
        self.viewportBackgroundSpinBox.blockSignals(False)
        self.viewportBackgroundResetButton.setEnabled(self.viewportBackgroundOverride is not None)

    def ViewportBackgroundValueChanged(self, value):
        self.viewportBackgroundOverride = max(0, min(255, int(value)))
        self.ApplyViewportBackground()
        self.SyncViewportBackgroundControls()

    def ResetViewportBackground(self):
        self.viewportBackgroundOverride = None
        self.SyncViewportBackgroundControls()
        self.ApplyViewportBackground()

    def ApplyViewportBackground(self):
        for viewport in (
            getattr(self, "inputViewport", None),
            getattr(self, "previewViewport", None),
            getattr(self, "outputViewport", None),
        ):
            if viewport is not None:
                viewport.SetViewportBackgroundOverride(self.viewportBackgroundOverride)

    def RefreshThemeIcons(self):
        if hasattr(self, "inputFileListDelegate"):
            self.inputFileListDelegate.RefreshIcons()
        for heading in self.findChildren(QtWidgets.QWidget, "sectionHeading"):
            if hasattr(heading, "RefreshIcon"):
                heading.RefreshIcon()
        if hasattr(self, "stackSizeWarningIcon"):
            self.stackSizeWarningIcon.setPixmap(self.TintedAssetPixmap("warning_24dp_E3E3E3.svg", "WARNING", 18))
        self.UpdateStackMemoryEstimate()
        self.RefreshStackerTextLogo()
        self.RefreshSidebarTabIcons()
        self.RefreshInputFileList()
        if hasattr(self, "inputDirectory"):
            self.inputDirectory.RefreshIcon()
        if hasattr(self, "addInputFileButton"):
            self.addInputFileButton.setIcon(AssetIcon("add_photo_alternate_24dp_E3E3E3.svg"))
        if hasattr(self, "outputDirectory"):
            self.outputDirectory.RefreshIcon()
        if hasattr(self, "inputDirectory"):
            self.inputDirectory.RefreshIcon()
            self.inputDirectory.button.setIcon(AssetIcon("add_folder_24dp_E3E3E3.svg"))
        if hasattr(self, "advancedButton"):
            self.advancedButton.setIcon(AssetIcon("settings_24dp_E3E3E3.svg"))
        if hasattr(self, "helpButton"):
            self.helpButton.setIcon(AssetIcon("help_24dp_E3E3E3.svg"))
            if hasattr(self, "helpMenuHelpButton"):
                self.RefreshHeaderMenuButtonIcon(self.helpMenuHelpButton)
                self.RefreshHeaderMenuButtonIcon(self.helpMenuAboutButton)
        if hasattr(self, "fileMenuButton"):
            self.UpdateFileMenuButtonIcon()
            self.RefreshHeaderMenuButtonIcon(self.newProjectButton)
            self.RefreshHeaderMenuButtonIcon(self.openProjectButton)
            self.RefreshHeaderMenuButtonIcon(self.saveProjectButton)
            self.RefreshHeaderMenuButtonIcon(self.closeProjectButton)
            self.RefreshHeaderMenuButtonIcon(self.saveProjectAsButton)
        if hasattr(self, "editMenuButton"):
            self.editMenuButton.setIcon(AssetIcon("edit_24dp_E3E3E3.svg"))
            self.RefreshHeaderMenuButtonIcon(self.undoMenuButton)
            self.RefreshHeaderMenuButtonIcon(self.redoMenuButton)
            self.RefreshHeaderMenuButtonIcon(self.copyViewportButton)
        if hasattr(self, "visibilityMenuButton"):
            self.visibilityMenuButton.setIcon(AssetIcon("visibility_24dp_E3E3E3.svg"))
        for viewport in (
            getattr(self, "inputViewport", None),
            getattr(self, "previewViewport", None),
            getattr(self, "outputViewport", None),
        ):
            if viewport is not None:
                viewport.RefreshEmptyIcon()
        if hasattr(self, "sortInputFilesButton"):
            self.sortInputFilesButton.setIcon(AssetIcon("sort_by_alpha_24dp_E3E3E3.svg"))
        if hasattr(self, "sortInputFilesNumericButton"):
            self.sortInputFilesNumericButton.setIcon(AssetIcon("sort_by_num_24dp_E3E3E3.svg"))
        if hasattr(self, "reverseInput"):
            self.reverseInput.setIcon(AssetIcon("reverse_24dp_E3E3E3.svg"))
        if hasattr(self, "syncInputSelectionButton"):
            self.syncInputSelectionButton.setIcon(AssetIcon("sync_alt_24dp_E3E3E3.svg"))
        if hasattr(self, "markInputInButton"):
            self.markInputInButton.setIcon(SplitAssetIcon("data_array_24dp_E3E3E3.svg", "left"))
        if hasattr(self, "markInputOutButton"):
            self.markInputOutButton.setIcon(SplitAssetIcon("data_array_24dp_E3E3E3.svg", "right"))
        if hasattr(self, "clearInputRangeButton"):
            self.clearInputRangeButton.setIcon(AssetIcon("clear_range_24dp_E3E3E3.svg"))
        if hasattr(self, "moveInputFileUpButton"):
            self.moveInputFileUpButton.setIcon(AssetIcon("move_up_24dp_E3E3E3.svg"))
        if hasattr(self, "moveInputFileDownButton"):
            self.moveInputFileDownButton.setIcon(AssetIcon("move_down_24dp_E3E3E3.svg"))
        if hasattr(self, "removeInputFileButton"):
            self.removeInputFileButton.setIcon(AssetIcon("remove_24dp_E3E3E3.svg"))
        if hasattr(self, "removeAllInputFilesButton"):
            self.removeAllInputFilesButton.setIcon(AssetIcon("close_24dp_E3E3E3.svg"))
        if hasattr(self, "outputOptionsButton"):
            self.outputOptionsButton.setIcon(AssetIcon("settings_24dp_E3E3E3.svg"))
        if hasattr(self, "savePresetButton"):
            self.savePresetButton.setIcon(AssetIcon("add_24dp_E3E3E3.svg"))
        if hasattr(self, "renderPathMode0"):
            self.renderPathMode0.setIcon(AssetIcon("gather_24dp_E3E3E3.svg"))
            self.renderPathMode1.setIcon(AssetIcon("pair_24dp_E3E3E3.svg"))
            self.renderPathMode2.setIcon(AssetIcon("stack_24dp_E3E3E3.svg"))
        if hasattr(self, "previewButton"):
            self.previewButton.setIcon(AssetIcon("play_arrow_24dp_E3E3E3.svg"))
        if hasattr(self, "exportButton"):
            self.exportButton.setIcon(AssetIcon("save_alt_24dp_E3E3E3.svg"))
        if hasattr(self, "cancelButton"):
            self.cancelButton.setIcon(AssetIcon("stop_24dp_E3E3E3.svg"))
        if hasattr(self, "viewportBackgroundResetButton"):
            self.viewportBackgroundResetButton.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        if hasattr(self, "middleGrayResetButton"):
            self.middleGrayResetButton.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        if hasattr(self, "previewFpsResetButton"):
            self.previewFpsResetButton.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        for button in getattr(self, "blendResetButtons", {}).values():
            button.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        if hasattr(self, "fullscreenButton"):
            iconName = "fullscreen_exit_24dp_E3E3E3.svg" if self.viewportOnlyMode else "fullscreen_24dp_E3E3E3.svg"
            self.fullscreenButton.setIcon(AssetIcon(iconName))
        if hasattr(self, "transportStartPlaceholderButton"):
            self.transportStartPlaceholderButton.setIcon(SplitAssetIcon("data_array_24dp_E3E3E3.svg", "left"))
            self.transportSkipPreviousButton.setIcon(AssetIcon("skip_previous_24dp_E3E3E3.svg"))
            self.transportPreviousButton.setIcon(AssetIcon("navigate_before_24dp_E3E3E3.svg"))
            self.transportNextButton.setIcon(AssetIcon("navigate_next_24dp_E3E3E3.svg"))
            self.transportSkipNextButton.setIcon(AssetIcon("skip_next_24dp_E3E3E3.svg"))
            self.transportEndPlaceholderButton.setIcon(SplitAssetIcon("data_array_24dp_E3E3E3.svg", "right"))
            self.SetScrubberPlaybackActive(self.scrubberPlaybackTimer.isActive())
        if hasattr(self, "frameScrubber"):
            self.frameScrubber.update()
        self.RefreshScrubberTransportLayout()

    def RefreshStackerTextLogo(self):
        if not hasattr(self, "stackerTextLogo"):
            return
        logoName = "stacker_text_CCCCCC.svg" if ThemeBaseName() == "light" else "stacker_text_444444.svg"
        self.stackerTextLogo.setIcon(QtGui.QIcon(ThemeAssetPath(logoName)))

    def UpdateFileMenuButtonIcon(self, *_):
        if hasattr(self, "fileMenuButton"):
            self.fileMenuButton.setIcon(AssetIcon("insert_drive_file_24dp_E3E3E3.svg"))

    def SetFileMenuButtonOpen(self, isOpen):
        if not hasattr(self, "fileMenuButton"):
            return
        self.fileMenuButton.setChecked(isOpen)
        self.UpdateFileMenuButtonIcon()

    def SetEditMenuButtonOpen(self, isOpen):
        if not hasattr(self, "editMenuButton"):
            return
        self.editMenuButton.setChecked(isOpen)

    def SetVisibilityMenuButtonOpen(self, isOpen):
        if not hasattr(self, "visibilityMenuButton"):
            return
        self.visibilityMenuButton.setChecked(isOpen)

    def SetHelpMenuButtonOpen(self, isOpen):
        if not hasattr(self, "helpButton"):
            return
        self.helpButton.setChecked(isOpen)

    def RefreshHeaderMenuButtonIcon(self, button):
        if not button or not hasattr(button, "iconLabel"):
            return
        if not getattr(button, "iconName", ""):
            button.iconLabel.clear()
            return
        icon = AssetIcon(button.iconName)
        pixmap = icon.pixmap(18, 18)
        if button.property("softDisabled"):
            tinted = QtGui.QPixmap(pixmap.size())
            tinted.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(tinted)
            painter.drawPixmap(0, 0, pixmap)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(tinted.rect(), ThemeQColor("TEXT_DISABLED"))
            painter.end()
            pixmap = tinted
        button.iconLabel.setPixmap(pixmap)

    def RefreshSidebarTabIcons(self):
        if not hasattr(self, "sidebarTabs"):
            return

        tabIcons = (
            "collections_24dp_E3E3E3.svg",
            "opacity_24dp_E3E3E3.svg",
            "save_alt_24dp_E3E3E3.svg",
        )
        for index, iconName in enumerate(tabIcons):
            if index < self.sidebarTabs.count():
                self.sidebarTabs.setTabIcon(index, AssetIcon(iconName))
        self.UpdateInputEmptyAction()
        self.UpdateOutputEmptyAction()
        self.UpdateViewportInfoVisibility()
        self.UpdatePreviewOverlay()
        self._RefreshPreview()

    def _BuildInputGroup(self):
        group = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(group)
        layout.setContentsMargins(14, 14, 14, 14)
        ConfigureFormLayout(layout)

        self.inputDirectory = FolderField("", dialogTitle = "Select Image Folder")
        self.inputDirectory.pathBrowsed.connect(self.AddInputFolderToRenderList)
        self.inputDirectory.lineEdit.hide()

        self.inputCountLabel = QtWidgets.QLabel()
        self.inputCountLabel.setWordWrap(False)
        self.inputCountLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.inputCountLabel.setStyleSheet("color: #b8b8b8; font-style: italic;")
        self.inputCountLabel.hide()

        self.inputFileModel = InputFileListModel(self)
        self.inputFileList = InputFileListView()
        self.inputFileList.setObjectName("inputFileList")
        self.inputFileList.setModel(self.inputFileModel)
        self.inputFileList.setAlternatingRowColors(False)
        self.inputFileList.setUniformItemSizes(True)
        self.inputFileList.setMinimumHeight(150)
        self.inputFileList.setMouseTracking(True)
        self.inputFileList.viewport().setMouseTracking(True)
        self.inputFileList.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.inputFileList.setDragEnabled(False)
        self.inputFileList.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.inputFileListDelegate = InputFileListDelegate(self.inputFileList)
        self.inputFileListDelegate.toggleRequested.connect(self.ToggleInputFileEnabled)
        self.inputFileList.setItemDelegate(self.inputFileListDelegate)
        self.inputFileList.selectionModel().selectionChanged.connect(lambda *_: self.InputFileSelectionChanged())
        self.inputFileList.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.inputFileList.customContextMenuRequested.connect(self.OpenInputFileListContextMenu)
        self.inputFileList.reorderRequested.connect(self.MoveInputFileEntries)
        self.inputFileList.setAcceptDrops(True)
        self.inputFileList.viewport().setAcceptDrops(True)
        self.inputFileList.installEventFilter(self)
        self.inputFileList.viewport().installEventFilter(self)
        self.removeInputFilesShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Delete), self.inputFileList)
        self.removeInputFilesShortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.removeInputFilesShortcut.activated.connect(self.RemoveSelectedInputFilesShortcut)
        self.disableInputFilesShortcut = QtGui.QShortcut(QtGui.QKeySequence("H"), self.inputFileList)
        self.disableInputFilesShortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.disableInputFilesShortcut.activated.connect(lambda: self.SetSelectedInputFilesEnabledShortcut(False))
        self.enableInputFilesShortcut = QtGui.QShortcut(QtGui.QKeySequence("U"), self.inputFileList)
        self.enableInputFilesShortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.enableInputFilesShortcut.activated.connect(lambda: self.SetSelectedInputFilesEnabledShortcut(True))

        self.addInputFileButton = QtWidgets.QToolButton()
        self.addInputFileButton.setIcon(AssetIcon("add_photo_alternate_24dp_E3E3E3.svg"))
        self.addInputFileButton.setText(IconButtonText("Add Images"))
        self.addInputFileButton.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addInputFileButton.setToolTip("Add one or more images")
        self.addInputFileButton.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.addInputFileButton.clicked.connect(self.OpenInputFileBrowser)

        self.inputDirectory.button.setText(IconButtonText("Add Folder"))
        self.inputDirectory.button.setIcon(AssetIcon("add_folder_24dp_E3E3E3.svg"))
        self.inputDirectory.button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.inputDirectory.button.setToolTip("Add all images from a folder")
        self.inputDirectory.button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        self.sortInputFilesButton = self.CreateInputToolButton("sort_by_alpha_24dp_E3E3E3.svg", "Sort alphabetically")
        self.sortInputFilesButton.clicked.connect(self.SortInputFileList)

        self.sortInputFilesNumericButton = self.CreateInputToolButton("sort_by_num_24dp_E3E3E3.svg", "Sort numerically")
        self.sortInputFilesNumericButton.clicked.connect(self.SortInputFileListNumerically)

        self.reverseInput = self.CreateInputToolButton("reverse_24dp_E3E3E3.svg", "Reverse image list")
        self.reverseInput.clicked.connect(self.ReverseInputList)

        self.syncInputSelectionButton = self.CreateInputToolButton("sync_alt_24dp_E3E3E3.svg", "Sync image list and timeline")
        self.syncInputSelectionButton.setProperty("showCheckedState", True)
        self.syncInputSelectionButton.setCheckable(True)
        self.syncInputSelectionButton.toggled.connect(self.SyncInputSelectionToggled)

        self.markInputInButton = self.CreateInputToolButton("data_array_24dp_E3E3E3.svg", "Mark in from selected image")
        self.markInputInButton.setIcon(SplitAssetIcon("data_array_24dp_E3E3E3.svg", "left"))
        self.markInputInButton.clicked.connect(lambda: self.MarkRangeFromFileList("in"))

        self.markInputOutButton = self.CreateInputToolButton("data_array_24dp_E3E3E3.svg", "Mark out from selected image")
        self.markInputOutButton.setIcon(SplitAssetIcon("data_array_24dp_E3E3E3.svg", "right"))
        self.markInputOutButton.clicked.connect(lambda: self.MarkRangeFromFileList("out"))

        self.clearInputRangeButton = self.CreateInputToolButton("clear_range_24dp_E3E3E3.svg", "Clear trim range")
        self.clearInputRangeButton.clicked.connect(self.ResetTrimRange)

        self.moveInputFileUpButton = self.CreateInputToolButton("move_up_24dp_E3E3E3.svg", "Move up")
        self.moveInputFileUpButton.clicked.connect(lambda: self.MoveSelectedInputFilesBy(-1))

        self.moveInputFileDownButton = self.CreateInputToolButton("move_down_24dp_E3E3E3.svg", "Move down")
        self.moveInputFileDownButton.clicked.connect(lambda: self.MoveSelectedInputFilesBy(1))

        self.removeInputFileButton = QtWidgets.QPushButton(IconButtonText("Remove"))
        self.removeInputFileButton.setIcon(AssetIcon("remove_24dp_E3E3E3.svg"))
        self.removeInputFileButton.setToolTip("Remove selected image(s) from the list")
        self.removeInputFileButton.installEventFilter(self)
        self.removeInputFileButton.pressed.connect(self.MarkSelectedInputFilesPendingRemove)
        self.removeInputFileButton.released.connect(self.ClearPendingInputRemoveIfCancelled)
        self.removeInputFileButton.clicked.connect(self.RemoveSelectedInputFilesFromList)

        self.removeAllInputFilesButton = QtWidgets.QPushButton(IconButtonText("Remove all"))
        self.removeAllInputFilesButton.setIcon(AssetIcon("close_24dp_E3E3E3.svg"))
        self.removeAllInputFilesButton.setToolTip("Remove every image from the list")
        self.removeAllInputFilesButton.clicked.connect(self.RemoveAllInputFilesFromList)

        self.rangeField = RangeField()
        self.rangeField.valuesChanged.connect(self.UpdateRangePreview)
        self.rangeField.handleDragStarted.connect(self.RangeHandleDragStarted)
        self.rangeField.handleDragEnded.connect(self.RangeHandleDragEnded)
        self.rangeField.SetDisplayReversed(False)

        inputAddToolbar = QtWidgets.QWidget()
        inputAddToolbarLayout = QtWidgets.QHBoxLayout(inputAddToolbar)
        inputAddToolbarLayout.setContentsMargins(0, 0, 0, 2)
        inputAddToolbarLayout.setSpacing(10)
        inputAddToolbarLayout.addWidget(self.addInputFileButton, 1)
        inputAddToolbarLayout.addWidget(self.inputDirectory.button, 1)
        layout.addRow(inputAddToolbar)

        inputFileListField = QtWidgets.QWidget()
        inputFileListLayout = QtWidgets.QHBoxLayout(inputFileListField)
        inputFileListLayout.setContentsMargins(0, 0, 0, 0)
        inputFileListLayout.setSpacing(8)
        inputFileListLayout.addWidget(self.inputFileList, 1)

        inputFileListSortToolbar = QtWidgets.QWidget()
        inputFileListSortToolbar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Expanding)
        inputFileListSortLayout = QtWidgets.QVBoxLayout(inputFileListSortToolbar)
        inputFileListSortLayout.setContentsMargins(0, 0, 0, 0)
        inputFileListSortLayout.setSpacing(6)
        inputFileListSortLayout.addWidget(self.moveInputFileUpButton)
        inputFileListSortLayout.addWidget(self.moveInputFileDownButton)
        inputFileListSortLayout.addWidget(self.reverseInput)
        inputFileListSortLayout.addWidget(self.sortInputFilesButton)
        inputFileListSortLayout.addWidget(self.sortInputFilesNumericButton)
        inputFileListSortLayout.addStretch(1)
        inputFileListSortLayout.addWidget(self.markInputInButton)
        inputFileListSortLayout.addWidget(self.markInputOutButton)
        inputFileListSortLayout.addWidget(self.clearInputRangeButton)
        inputFileListSortLayout.addWidget(self.syncInputSelectionButton)
        inputFileListLayout.addWidget(inputFileListSortToolbar, 0)
        layout.addRow(inputFileListField)

        fileListButtonRow = QtWidgets.QWidget()
        fileListButtonLayout = QtWidgets.QHBoxLayout(fileListButtonRow)
        fileListButtonLayout.setContentsMargins(0, 0, 0, 0)
        fileListButtonLayout.setSpacing(8)
        fileListButtonLayout.addWidget(self.removeInputFileButton)
        fileListButtonLayout.addWidget(self.removeAllInputFilesButton)
        fileListButtonLayout.addStretch(1)
        layout.addRow(fileListButtonRow)

        skipInputRow = QtWidgets.QWidget()
        skipInputLayout = QtWidgets.QHBoxLayout(skipInputRow)
        skipInputLayout.setContentsMargins(0, 0, 0, 0)
        skipInputLayout.setSpacing(8)
        skipInputLayout.addWidget(self.FixedFormLabel("Only read every", self.IO_LABEL_WIDTH))
        skipInputLayout.addWidget(self.skipInput, 0)
        skipInputLayout.addStretch(1)
        layout.addRow(skipInputRow)

        self.UpdateInputFileActionButtons()

        return group

    def CreateInputToolButton(self, iconName, tooltip):
        button = QtWidgets.QToolButton()
        button.setObjectName("inputToolButton")
        button.setProperty("showCheckedState", False)
        button.setIcon(AssetIcon(iconName))
        button.setToolTip(tooltip)
        button.setFixedSize(34, 30)
        button.setIconSize(QtCore.QSize(24, 24))
        return button

    def _BuildOutputGroup(self):
        group = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.outputDirectory = FolderField("", dialogTitle = "Select Export Folder")
        self.outputDirectory.textChanged.connect(self.UpdateOutputViewport)
        self.outputFileName = QtWidgets.QLineEdit("frame")
        self.outputFileName.textChanged.connect(self.UpdateOutputViewport)
        self.outputFileName.textChanged.connect(self.UpdateOutputSequenceSuffixLabel)

        self.outputFileType = DownwardComboBox()
        self.outputFileType.setEditable(False)
        self.outputFileType.addItems(OUTPUT_TYPES)
        self.outputFileType.setCurrentText("jpg")

        self.outputOptionsButton = QtWidgets.QToolButton()
        self.outputOptionsButton.setIcon(AssetIcon("settings_24dp_E3E3E3.svg"))
        self.outputOptionsButton.setToolTip("File export options")
        self.outputOptionsButton.clicked.connect(self.OpenOutputOptionsPanel)
        self._BuildOutputOptionsPanel()
        self.outputFileType.currentTextChanged.connect(self.UpdateOutputOptionsPanel)
        self.outputFileType.currentTextChanged.connect(self.UpdateOutputViewport)
        self.outputFileType.currentTextChanged.connect(self.UpdateOutputSequenceSuffixLabel)

        form = QtWidgets.QFormLayout()
        ConfigureFormLayout(form)

        def AddSectionGap():
            spacer = QtWidgets.QWidget()
            spacer.setFixedHeight(6)
            form.addRow(spacer)

        form.addRow(SectionHeading("Output", "save_24dp_E3E3E3.svg"))
        self.AddFixedFormRow(form, "Folder", self.outputDirectory, self.IO_LABEL_WIDTH)
        self.outputNameTypeField = OutputNameTypeField(self.outputFileName, self.outputFileType, self.outputOptionsButton)
        self.UpdateOutputSequenceSuffixLabel()
        self.AddFixedFormRow(form, "Filename", self.outputNameTypeField, self.IO_LABEL_WIDTH)
        self.AddFixedFormRow(form, "Only export every", self.skipOutput, self.IO_LABEL_WIDTH)
        AddSectionGap()
        form.addRow(SectionHeading("Resolution", "image_aspect_ratio_24dp_E3E3E3.svg"))
        self.AddFixedFormRow(form, "Export Resolution", OverrideField(ResolutionField(self.overrideWidth, self.overrideHeight), self.overrideResolution), self.IO_LABEL_WIDTH)
        self.AddFixedFormRow(form, "Export Scaling", self.resizeFilter, self.IO_LABEL_WIDTH)
        AddSectionGap()
        form.addRow(SectionHeading("Blending", "opacity_24dp_E3E3E3.svg"))
        self.AddFixedFormRow(form, "", CheckboxField(self.blendInLinear), self.IO_LABEL_WIDTH)
        self.AddFixedFormRow(form, "Middle Gray", OverrideField(self.middleGrayField, self.useCustomMiddleGray), self.IO_LABEL_WIDTH)
        AddSectionGap()
        form.addRow(SectionHeading("Color", "gamma_24dp_E3E3E3.svg"))
        self.AddFixedFormRow(form, "Output Curve", OverrideField(self.outputTransferFunction, self.overrideOutputTransfer), self.IO_LABEL_WIDTH)
        AddSectionGap()
        self.AddFixedFormRow(form, "", CheckboxField(self.previewEnabled), self.IO_LABEL_WIDTH)

        layout.addLayout(form)
        layout.addStretch(1)
        return group

    def _BuildBlendGroup(self):
        group = QtWidgets.QWidget()
        outerLayout = QtWidgets.QVBoxLayout(group)
        outerLayout.setContentsMargins(14, 14, 14, 14)
        outerLayout.setSpacing(12)

        layout = QtWidgets.QFormLayout()
        ConfigureFormLayout(layout)

        self.blendMode = DownwardComboBox()
        for name, mode in BLEND_MODES.items():
            self.blendMode.addItem(name, mode)
        self.blendMode.setCurrentText("Max (Lighten)")
        self.blendMode.currentIndexChanged.connect(self.UpdateBlendControlsEnabled)
        self.blendMode.currentIndexChanged.connect(self.UpdatePresetDirtyIndicator)

        self.decay = FloatSlider(1.0, decimals = 3)
        self.decay.valueChanged.connect(self.UpdatePresetDirtyIndicator)
        self.decay.valueChanged.connect(self.UpdateBlendResetButtons)
        self.opacity = FloatSlider(1.0, decimals = 3)
        self.opacity.valueChanged.connect(self.UpdatePresetDirtyIndicator)
        self.opacity.valueChanged.connect(self.UpdateBlendResetButtons)
        self.pairDistanceSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.pairDistanceSlider.setRange(-20, 20)
        self.pairDistanceSlider.setMinimumHeight(26)
        self.pairDistanceSpinBox = QtWidgets.QSpinBox()
        self.pairDistanceSpinBox.setRange(-9999, 9999)
        self.pairDistanceSpinBox.setFixedWidth(72)
        self.pairDistanceSlider.valueChanged.connect(self.pairDistanceSpinBox.setValue)
        self.pairDistanceSpinBox.valueChanged.connect(self.PairDistanceSpinBoxChanged)
        self.pairDistanceSpinBox.valueChanged.connect(self.UpdatePresetDirtyIndicator)
        self.pairDistanceSpinBox.valueChanged.connect(self.UpdateBlendResetButtons)
        self.pairDistanceSpinBox.setValue(-1)
        self.pairDistanceField = self.BlendResetField(
            SliderSpinBoxField(self.pairDistanceSlider, self.pairDistanceSpinBox),
            "shift",
            "Reset shift",
        )
        self.pairBlurSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.pairBlurSlider.setRange(0, 20)
        self.pairBlurSlider.setMinimumHeight(26)
        self.pairBlurSpinBox = QtWidgets.QSpinBox()
        self.pairBlurSpinBox.setRange(0, 9999)
        self.pairBlurSpinBox.setFixedWidth(72)
        self.pairBlurSlider.valueChanged.connect(self.pairBlurSpinBox.setValue)
        self.pairBlurSpinBox.valueChanged.connect(self.PairBlurSpinBoxChanged)
        self.pairBlurSpinBox.valueChanged.connect(self.UpdatePresetDirtyIndicator)
        self.pairBlurSpinBox.valueChanged.connect(self.UpdateBlendControlsEnabled)
        self.pairBlurSpinBox.valueChanged.connect(self.UpdateBlendResetButtons)
        self.pairBlurSpinBox.setValue(0)
        self.pairBlurField = self.BlendResetField(
            SliderSpinBoxField(self.pairBlurSlider, self.pairBlurSpinBox),
            "blur",
            "Reset temporal blur",
        )
        self.pairBlurKernel = DownwardComboBox()
        self.pairBlurKernel.setEditable(False)
        self.pairBlurKernel.addItems(("Box", "Triangle", "Semicircle", "Gaussian", "Cosine", "Exponential"))
        self.pairBlurKernel.setCurrentText("Gaussian")
        self.pairBlurKernel.currentTextChanged.connect(self.UpdatePresetDirtyIndicator)
        self.stackSizeSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.stackSizeSlider.setRange(1, 20)
        self.stackSizeSlider.setMinimumHeight(26)
        self.stackSizeSpinBox = QtWidgets.QSpinBox()
        self.stackSizeSpinBox.setRange(1, 9999)
        self.stackSizeSpinBox.setFixedWidth(72)
        self.stackSizeSlider.valueChanged.connect(self.stackSizeSpinBox.setValue)
        self.stackSizeSpinBox.valueChanged.connect(self.StackSizeSpinBoxChanged)
        self.stackSizeSpinBox.valueChanged.connect(self.UpdatePresetDirtyIndicator)
        self.stackSizeSpinBox.valueChanged.connect(self.UpdateBlendResetButtons)
        self.stackSizeSpinBox.setValue(10)
        self.stackSizeField = self.BlendResetField(
            SliderSpinBoxField(self.stackSizeSlider, self.stackSizeSpinBox),
            "size",
            "Reset size",
        )
        self.stackDirection = DownwardComboBox()
        self.stackDirection.setEditable(False)
        self.stackDirection.addItems(("Past", "Future", "Centered"))
        self.stackDirection.setCurrentText("Past")
        self.stackDirection.currentTextChanged.connect(self.UpdatePresetDirtyIndicator)

        self.blendScaleSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.blendScaleSlider.setRange(0, 2000)
        self.blendScaleSlider.setMinimumHeight(26)
        self.blendScaleSpinBox = QtWidgets.QDoubleSpinBox()
        self.blendScaleSpinBox.setRange(0.0, 9999.0)
        self.blendScaleSpinBox.setDecimals(3)
        self.blendScaleSpinBox.setSingleStep(0.01)
        self.blendScaleSpinBox.setFixedWidth(96)
        self.blendScaleSlider.valueChanged.connect(self.BlendScaleSliderChanged)
        self.blendScaleSpinBox.valueChanged.connect(self.BlendScaleSpinBoxChanged)
        self.blendScaleSpinBox.valueChanged.connect(self.UpdatePresetDirtyIndicator)
        self.blendScaleSpinBox.valueChanged.connect(self.UpdateBlendResetButtons)
        self.blendScaleSpinBox.setValue(1.0)
        self.blendScaleSlider.setValue(1000)
        self.blendScaleField = self.BlendResetField(
            SliderSpinBoxField(self.blendScaleSlider, self.blendScaleSpinBox),
            "scale",
            "Reset gain",
        )

        self.blendOffsetSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.blendOffsetSlider.setRange(-1000, 1000)
        self.blendOffsetSlider.setMinimumHeight(26)
        self.blendOffsetSpinBox = QtWidgets.QDoubleSpinBox()
        self.blendOffsetSpinBox.setRange(-1.0, 1.0)
        self.blendOffsetSpinBox.setDecimals(3)
        self.blendOffsetSpinBox.setSingleStep(0.01)
        self.blendOffsetSpinBox.setFixedWidth(96)
        self.blendOffsetSlider.valueChanged.connect(self.BlendOffsetSliderChanged)
        self.blendOffsetSpinBox.valueChanged.connect(self.BlendOffsetSpinBoxChanged)
        self.blendOffsetSpinBox.valueChanged.connect(self.UpdatePresetDirtyIndicator)
        self.blendOffsetSpinBox.valueChanged.connect(self.UpdateBlendResetButtons)
        self.blendOffsetSpinBox.setValue(0.0)
        self.blendOffsetSlider.setValue(0)
        self.blendOffsetField = self.BlendResetField(
            SliderSpinBoxField(self.blendOffsetSlider, self.blendOffsetSpinBox),
            "lift",
            "Reset lift",
        )
        self.absoluteValues = QtWidgets.QCheckBox("Absolute Values")
        self.absoluteValues.setToolTip("Fold negative adjusted RGB values back above zero.")
        self.absoluteValues.toggled.connect(self.UpdatePresetDirtyIndicator)

        self.activePresetCleanData = None
        self.presetComboBox = DownwardComboBox()
        self.presetComboBox.setObjectName("presetComboBox")
        presetFont = self.presetComboBox.font()
        presetFont.setPointSize(presetFont.pointSize() + 1)
        self.presetComboBox.setFont(presetFont)
        self.presetComboBox.setMinimumHeight(34)
        self.presetComboBox.currentIndexChanged.connect(self.LoadSelectedPreset)
        self.presetComboBox.activated.connect(self.LoadSelectedPreset)
        self.savePresetButton = QtWidgets.QPushButton(IconButtonText("Save Preset"))
        self.savePresetButton.setObjectName("savePresetButton")
        self.savePresetButton.setFont(presetFont)
        self.savePresetButton.setMinimumHeight(34)
        self.savePresetButton.setIcon(AssetIcon("add_24dp_E3E3E3.svg"))
        self.savePresetButton.clicked.connect(self.SaveBlendPreset)
        self.RefreshPresetList()

        self.AddFormGap(layout, 3)
        layout.addRow(ButtonComboField(self.presetComboBox, self.savePresetButton))
        self.AddFormGap(layout, 3)
        layout.addRow(SectionHeading("Blend", "opacity_24dp_E3E3E3.svg"))
        self.renderPathGroup = QtWidgets.QButtonGroup(self)
        self.renderPathGroup.setExclusive(True)
        self.renderPathMode0 = QtWidgets.QPushButton(IconButtonText("Gather"))
        self.renderPathMode1 = QtWidgets.QPushButton(IconButtonText("Pair"))
        self.renderPathMode2 = QtWidgets.QPushButton(IconButtonText("Stack"))
        for path, (button, iconName) in enumerate((
            (self.renderPathMode0, "gather_24dp_E3E3E3.svg"),
            (self.renderPathMode1, "pair_24dp_E3E3E3.svg"),
            (self.renderPathMode2, "stack_24dp_E3E3E3.svg"),
        )):
            button.setObjectName("renderPathButton")
            button.setIcon(AssetIcon(iconName))
            button.setIconSize(QtCore.QSize(18, 18))
            button.setCheckable(True)
            button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            self.renderPathGroup.addButton(button, path)
        self.renderPathMode0.setChecked(True)
        self.renderPathGroup.idClicked.connect(self.UpdateRenderPathControls)
        self.renderPathGroup.idClicked.connect(self.RenderPathClicked)

        renderPathField = QtWidgets.QWidget()
        renderPathLayout = QtWidgets.QHBoxLayout(renderPathField)
        renderPathLayout.setContentsMargins(0, 0, 0, 0)
        renderPathLayout.setSpacing(8)
        renderPathLayout.addWidget(self.renderPathMode0)
        renderPathLayout.addWidget(self.renderPathMode1)
        renderPathLayout.addWidget(self.renderPathMode2)
        layout.addRow(renderPathField)
        self.AddFixedFormRow(layout, "Blend", self.blendMode, self.BLEND_LABEL_WIDTH)
        self.decayLabel = QtWidgets.QLabel("Spread")
        self.decayLabel.setFixedWidth(self.BLEND_LABEL_WIDTH)
        self.decayLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.decayField = self.BlendResetField(self.decay, "spread", "Reset spread")
        layout.addRow(self.decayLabel, self.decayField)
        self.pairDistanceLabel = QtWidgets.QLabel("Shift")
        self.pairDistanceLabel.setFixedWidth(self.BLEND_LABEL_WIDTH)
        self.pairDistanceLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addRow(self.pairDistanceLabel, self.pairDistanceField)
        self.pairBlurLabel = QtWidgets.QLabel("Temporal Blur")
        self.pairBlurLabel.setFixedWidth(self.BLEND_LABEL_WIDTH)
        self.pairBlurLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addRow(self.pairBlurLabel, self.pairBlurField)
        self.pairKernelLabel = QtWidgets.QLabel("Kernel")
        self.pairKernelLabel.setFixedWidth(self.BLEND_LABEL_WIDTH)
        self.pairKernelLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addRow(self.pairKernelLabel, self.pairBlurKernel)
        self.stackSizeLabel = QtWidgets.QLabel("Size")
        self.stackSizeLabel.setFixedWidth(self.BLEND_LABEL_WIDTH)
        self.stackSizeLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addRow(self.stackSizeLabel, self.stackSizeField)
        self.stackMemoryIcon = QtWidgets.QLabel()
        self.stackMemoryIcon.setFixedSize(18, 18)
        self.stackMemoryIcon.hide()
        self.stackMemoryLabel = QtWidgets.QLabel("Memory Required: --")
        self.stackMemoryLabel.setStyleSheet("font-style: italic;")
        self.stackMemoryLabel.setToolTip("Estimated stack memory for the current render, compared against currently available RAM.")
        self.stackMemoryDetailLabel = QtWidgets.QLabel("")
        self.stackMemoryDetailLabel.setStyleSheet("font-style: italic;")
        self.stackMemoryDetailLabel.hide()
        self.stackMemoryField = QtWidgets.QWidget()
        stackMemoryOuterLayout = QtWidgets.QHBoxLayout(self.stackMemoryField)
        stackMemoryOuterLayout.setContentsMargins(0, 0, 0, 0)
        stackMemoryOuterLayout.setSpacing(6)
        stackMemoryTextLayout = QtWidgets.QVBoxLayout()
        stackMemoryTextLayout.setContentsMargins(0, 0, 0, 0)
        stackMemoryTextLayout.setSpacing(1)
        stackMemoryTextLayout.addWidget(self.stackMemoryLabel)
        stackMemoryTextLayout.addWidget(self.stackMemoryDetailLabel)
        stackMemoryLayout = stackMemoryOuterLayout
        stackMemoryLayout.setContentsMargins(0, 0, 0, 0)
        stackMemoryLayout.addWidget(self.stackMemoryIcon)
        stackMemoryLayout.addLayout(stackMemoryTextLayout, 1)
        self.stackMemoryField.hide()
        self.stackMemorySpacer = self.AddFixedFormRow(layout, "", self.stackMemoryField, self.BLEND_LABEL_WIDTH)
        self.stackMemorySpacer.hide()
        self.stackSizeWarningIcon = QtWidgets.QLabel()
        self.stackSizeWarningIcon.setFixedSize(18, 18)
        self.stackSizeWarningIcon.setPixmap(self.TintedAssetPixmap("warning_24dp_E3E3E3.svg", "WARNING", 18))
        self.stackSizeWarningLabel = QtWidgets.QLabel("Large stack sizes can significantly slow render times.")
        self.stackSizeWarningLabel.setObjectName("warningLabel")
        self.stackSizeWarningLabel.setWordWrap(True)
        self.stackSizeWarningField = QtWidgets.QWidget()
        stackSizeWarningLayout = QtWidgets.QHBoxLayout(self.stackSizeWarningField)
        stackSizeWarningLayout.setContentsMargins(0, 0, 0, 0)
        stackSizeWarningLayout.setSpacing(6)
        stackSizeWarningLayout.addWidget(self.stackSizeWarningIcon)
        stackSizeWarningLayout.addWidget(self.stackSizeWarningLabel, 1)
        self.stackSizeWarningField.hide()
        self.stackSizeWarningSpacer = self.AddFixedFormRow(layout, "", self.stackSizeWarningField, self.BLEND_LABEL_WIDTH)
        self.stackSizeWarningSpacer.hide()
        self.stackDirectionLabel = QtWidgets.QLabel("Direction")
        self.stackDirectionLabel.setFixedWidth(self.BLEND_LABEL_WIDTH)
        self.stackDirectionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addRow(self.stackDirectionLabel, self.stackDirection)
        self.AddFormGap(layout, 6)
        layout.addRow(SectionHeading("Adjustment", "tune_24dp_E3E3E3.svg"))
        self.AddFixedFormRow(layout, "Gain", self.blendScaleField, self.BLEND_LABEL_WIDTH)
        self.AddFixedFormRow(layout, "Lift", self.blendOffsetField, self.BLEND_LABEL_WIDTH)
        self.AddFixedFormRow(layout, "", CheckboxField(self.absoluteValues), self.BLEND_LABEL_WIDTH)
        self.AddFormGap(layout, 6)
        layout.addRow(SectionHeading("Final Composite", "texture_24dp_E3E3E3.svg"))
        self.opacityField = self.BlendResetField(self.opacity, "intensity", "Reset intensity")
        self.AddFixedFormRow(layout, "Intensity", self.opacityField, self.BLEND_LABEL_WIDTH)
        self.AddFormGap(layout, 6)
        self.UpdateRenderPathControls()
        self.UpdateBlendControlsEnabled()
        outerLayout.addLayout(layout)
        outerLayout.addStretch(1)
        return group

    def _BuildRunGroup(self):
        group = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(group)
        self.runLayout = layout
        layout.setContentsMargins(0, 0, 0, 0)

        self.progressRow = QtWidgets.QWidget()
        progressLayout = QtWidgets.QHBoxLayout(self.progressRow)
        progressLayout.setContentsMargins(0, 0, 0, 0)
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setObjectName("idleProgress")
        self.progressBar.setRange(0, 1)
        self.progressBar.setValue(0)
        self.progressBar.setMinimumWidth(240)
        self.progressBar.setMaximumWidth(1600)
        self.progressBar.setVisible(False)
        self.progressText = "0/0"
        self.fpsText = "0.0 fps"
        self.remainingText = "-- remaining"

        progressLayout.addStretch(1)
        progressLayout.addWidget(self.progressBar, 1)
        progressLayout.addStretch(1)

        self.viewportTabs = QtWidgets.QTabWidget()
        self.viewportTabs.setObjectName("viewportTabs")
        self.inputViewport = PreviewPane()
        self.previewViewport = PreviewPane()
        self.outputViewport = PreviewPane()
        self.previewViewport.SetNeutralPlaceholder("Generated previews can be viewed here")
        self.outputViewport.SetNeutralPlaceholder("Rendered exports can be viewed here")
        self.frameScrubber = FrameScrubber()
        self.viewportTabs.addTab(self.inputViewport, "Input")
        self.viewportTabs.addTab(self.previewViewport, "Preview Cache")
        self.viewportTabs.addTab(self.outputViewport, "View Export")
        self.viewportTabs.currentChanged.connect(self.ViewportTabChanged)
        self.inputViewport.viewportChanged.connect(self.outputViewport.SetViewportState)
        self.inputViewport.viewportChanged.connect(self.previewViewport.SetViewportState)
        self.outputViewport.viewportChanged.connect(self.inputViewport.SetViewportState)
        self.outputViewport.viewportChanged.connect(self.previewViewport.SetViewportState)
        self.previewViewport.viewportChanged.connect(self.inputViewport.SetViewportState)
        self.previewViewport.viewportChanged.connect(self.outputViewport.SetViewportState)
        self.inputViewport.emptyClicked.connect(self.InputViewportEmptyClicked)
        self.inputViewport.setAcceptDrops(True)
        self.inputViewport.installEventFilter(self)
        self.outputViewport.emptyClicked.connect(self.OpenOutputFolderBrowser)
        self.inputViewport.contextMenuRequested.connect(self.OpenViewportContextMenu)
        self.previewViewport.contextMenuRequested.connect(self.OpenViewportContextMenu)
        self.outputViewport.contextMenuRequested.connect(self.OpenViewportContextMenu)
        self.frameScrubber.frameChanged.connect(self.FrameScrubberChanged)
        self.frameScrubber.markRequested.connect(self.MarkRangeFromScrubber)
        self.frameScrubber.markDragStarted.connect(self.TrimDragStarted)
        self.frameScrubber.markDragEnded.connect(self.TrimDragEnded)
        self.UpdateViewportScaling()
        self.UpdateViewportInfoVisibility()
        self.UpdatePreviewOverlay()
        self.UpdateOutputViewport()

        self.scrubberTransport = self._BuildScrubberTransport()
        self.fullscreenButton = QtWidgets.QPushButton()
        self.fullscreenButton.setObjectName("fullscreenButton")
        self.fullscreenButton.setIcon(AssetIcon("fullscreen_24dp_E3E3E3.svg"))
        self.fullscreenButton.setIconSize(QtCore.QSize(24, 24))
        self.fullscreenButton.setToolTip("Viewport only")
        self.fullscreenButton.clicked.connect(self.ToggleViewportOnlyMode)

        self.viewportOverlay = ViewportOverlay(self.viewportTabs, self.scrubberTransport)
        self.viewportOverlay.SetRightOverlay(self.fullscreenButton)

        layout.addWidget(self.viewportOverlay, 1)
        self.frameScrubberLayoutIndex = layout.count()
        layout.addWidget(self.frameScrubber)
        layout.addWidget(self.progressRow)
        self.UpdateViewportFooterControls()
        return group

    def _BuildScrubberTransport(self):
        widget = QtWidgets.QWidget()
        widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetFixedSize)

        def AddButton(icon, tooltip, callback = None, wide = True):
            button = QtWidgets.QPushButton()
            button.setObjectName("transportButton")
            button.setIcon(icon)
            button.setIconSize(QtCore.QSize(22, 22))
            button.setProperty("wideTransportButton", wide)
            button.setFixedSize(54 if wide else 36, 32)
            button.setToolTip(tooltip)
            if callback:
                button.clicked.connect(callback)
            layout.addWidget(button)
            return button

        layout.addStretch(1)
        self.transportStartPlaceholderButton = AddButton(SplitAssetIcon("data_array_24dp_E3E3E3.svg", "left"), "Mark In", lambda: self.MarkCurrentScrubberFrame("in"), wide = False)
        self.transportSkipPreviousButton = AddButton(AssetIcon("skip_previous_24dp_E3E3E3.svg"), "First frame", lambda: self.JumpActiveFrame("first"))
        self.transportPreviousButton = AddButton(AssetIcon("navigate_before_24dp_E3E3E3.svg"), "Previous frame", lambda: self.StepActiveFrame(-1))
        self.transportPlayButton = AddButton(AssetIcon("play_arrow_24dp_E3E3E3.svg"), "Play", self.ToggleScrubberPlayback)
        self.transportNextButton = AddButton(AssetIcon("navigate_next_24dp_E3E3E3.svg"), "Next frame", lambda: self.StepActiveFrame(1))
        self.transportSkipNextButton = AddButton(AssetIcon("skip_next_24dp_E3E3E3.svg"), "Last frame", lambda: self.JumpActiveFrame("last"))
        self.transportEndPlaceholderButton = AddButton(SplitAssetIcon("data_array_24dp_E3E3E3.svg", "right"), "Mark Out", lambda: self.MarkCurrentScrubberFrame("out"), wide = False)
        layout.addStretch(1)

        self.scrubberTransportButtons = [
            self.transportStartPlaceholderButton,
            self.transportSkipPreviousButton,
            self.transportPreviousButton,
            self.transportPlayButton,
            self.transportNextButton,
            self.transportSkipNextButton,
            self.transportEndPlaceholderButton,
        ]
        return widget

    def _BuildPreviewControls(self, form):
        self.previewEnabled = QtWidgets.QCheckBox("Live Export Preview")
        self.previewEnabled.setChecked(True)
        self.previewEnabled.toggled.connect(self.UpdatePreviewOptionsEnabled)
        self.previewEnabled.toggled.connect(self.SyncActivePreviewSettings)

        self.previewScale = DownwardComboBox()
        self.previewScale.addItem("Full", 1)
        self.previewScale.addItem("Half", 2)
        self.previewScale.addItem("Quarter", 4)
        self.previewScale.setCurrentIndex(1)
        self.previewScale.currentIndexChanged.connect(self.SyncActivePreviewSettings)

        self.previewFps = QtWidgets.QDoubleSpinBox()
        self.previewFps.setRange(0.25, 30.0)
        self.previewFps.setSingleStep(0.25)
        self.previewFps.setDecimals(2)
        self.previewFps.setValue(1.0)
        self.previewFps.setSuffix(" fps")
        self.previewFps.setFixedWidth(104)
        self.previewFps.valueChanged.connect(self.SyncActivePreviewSettings)

        form.addRow("Preview Resolution", self.previewScale)
        previewFpsField = QtWidgets.QWidget()
        previewFpsLayout = QtWidgets.QHBoxLayout(previewFpsField)
        previewFpsLayout.setContentsMargins(0, 0, 0, 0)
        previewFpsLayout.setSpacing(8)
        previewFpsLayout.addWidget(self.previewFps)
        previewFpsLayout.addWidget(self.previewFpsResetButton)
        previewFpsLayout.addStretch(1)
        form.addRow("Update Frequency", previewFpsField)
        self.UpdatePreviewOptionsEnabled()

    def OpenAdvancedPanel(self):
        self.advancedPanel.show()
        self.advancedPanel.raise_()
        self.advancedPanel.activateWindow()

    def AppIconPixmap(self, targetSize = 256):
        icon = QtGui.QIcon(ThemeAppIconPath(ThemeName()))
        availableSizes = icon.availableSizes()
        if availableSizes:
            largestSize = max(availableSizes, key = lambda size: size.width() * size.height())
            return icon.pixmap(largestSize)
        return icon.pixmap(targetSize, targetSize)

    def AboutLogoPixmap(self, targetSize = 256):
        return QtGui.QIcon(ThemeAboutLogoPath(ThemeName())).pixmap(targetSize, targetSize)

    def CreateAboutLinkItem(self, iconName, text, url = "", actionName = ""):
        item = QtWidgets.QWidget()
        if url:
            item.setProperty("aboutUrl", url)
        if actionName:
            item.setProperty("aboutAction", actionName)
        if url or actionName:
            item.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        layout = QtWidgets.QHBoxLayout(item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        iconLabel = QtWidgets.QLabel()
        if url:
            iconLabel.setProperty("aboutUrl", url)
        if actionName:
            iconLabel.setProperty("aboutAction", actionName)
            iconLabel.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        iconSize = 28
        iconLabel.setFixedSize(iconSize, iconSize)
        if iconName == "github":
            githubIcon = "github_202020.svg" if ThemeBaseName() == "light" else "github_e3e3e3.svg"
            icon = QtGui.QIcon(ThemeAssetPath(githubIcon))
        else:
            icon = AssetIcon(iconName)
        iconLabel.setPixmap(icon.pixmap(iconSize, iconSize))
        layout.addWidget(iconLabel)

        if url:
            textColor = ThemeColor("TEXT")
            textLabel = QtWidgets.QLabel(
                f'<a href="{url}" style="color: {textColor}; text-decoration: underline;">{html.escape(text)}</a>'
            )
            textLabel.setProperty("aboutUrl", url)
            textLabel.setOpenExternalLinks(True)
            textLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        else:
            if actionName:
                textColor = ThemeColor("TEXT")
                textLabel = QtWidgets.QLabel(
                    f'<span style="color: {textColor}; text-decoration: underline;">{html.escape(text)}</span>'
                )
            else:
                textLabel = QtWidgets.QLabel(text)
            if actionName:
                textLabel.setProperty("aboutAction", actionName)
                textLabel.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        layout.addWidget(textLabel)
        return item

    def LicensesText(self):
        path = os.path.join(AppRoot(), "LICENSES.txt")
        try:
            with open(path, "r", encoding = "utf-8") as file:
                return file.read()
        except OSError:
            return "Licenses file could not be loaded."

    def ShowLicensesDialog(self):
        if getattr(self, "licensesDialog", None) is not None and self.licensesDialog.isVisible():
            self.licensesDialog.raise_()
            self.licensesDialog.activateWindow()
            return

        dialog = QtWidgets.QDialog(self)
        self.licensesDialog = dialog
        dialog.setWindowTitle("Licenses")
        dialog.setWindowIcon(StatusAssetIcon("info"))
        dialog.setModal(False)
        dialog.setWindowFlags(
            dialog.windowFlags()
            | QtCore.Qt.WindowType.WindowMinimizeButtonHint
            | QtCore.Qt.WindowType.WindowMaximizeButtonHint
        )
        dialog.resize(760, 560)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        text = QtWidgets.QPlainTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        text.setPlainText(self.LicensesText())
        text.setStyleSheet(
            f"QPlainTextEdit {{ background: {ThemeColor('CONSOLE_BG')}; border: 1px solid {ThemeColor('CONSOLE_BG')}; }}"
        )
        self.licensesText = text
        layout.addWidget(text, 1)

        buttonRow = QtWidgets.QHBoxLayout()
        buttonRow.addStretch(1)
        closeButton = QtWidgets.QPushButton("Close")
        closeButton.clicked.connect(dialog.close)
        buttonRow.addWidget(closeButton)
        layout.addLayout(buttonRow)

        def LicensesDialogClosed(*_):
            self.licensesDialog = None
            self.licensesText = None

        dialog.finished.connect(LicensesDialogClosed)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def ShowAboutDialog(self):
        existingDialog = getattr(self, "aboutDialog", None)
        if existingDialog and existingDialog.isVisible():
            existingDialog.raise_()
            existingDialog.activateWindow()
            return

        dialog = QtWidgets.QDialog(self)
        self.aboutDialog = dialog
        dialog.setWindowTitle(f"About {APP_NAME}")
        dialog.setWindowIcon(StatusAssetIcon("info"))
        dialog.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        dialog.setMinimumWidth(600)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 18)
        layout.setSpacing(12)

        iconLabel = QtWidgets.QLabel()
        iconLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        iconPixmap = self.AboutLogoPixmap(300)
        if not iconPixmap.isNull():
            iconLabel.setPixmap(iconPixmap)
        layout.addWidget(iconLabel, 0, QtCore.Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(8)
        versionLabel = QtWidgets.QLabel(f"Version {APP_VERSION} - {APP_RELEASE_DATE}")
        versionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        versionLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(versionLabel)

        copyrightRow = QtWidgets.QHBoxLayout()
        copyrightRow.setContentsMargins(0, 0, 0, 0)
        copyrightRow.setSpacing(6)
        copyrightRow.addStretch(1)
        copyrightIcon = QtWidgets.QLabel()
        copyrightIcon.setFixedSize(18, 18)
        copyrightIcon.setPixmap(AssetIcon("copyright_24dp_E3E3E3.svg").pixmap(18, 18))
        copyrightRow.addWidget(copyrightIcon)
        copyrightLabel = QtWidgets.QLabel(APP_COPYRIGHT)
        copyrightLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        copyrightRow.addWidget(copyrightLabel)
        copyrightRow.addStretch(1)
        layout.addLayout(copyrightRow)

        layout.addSpacing(8)
        descriptionLabel = QtWidgets.QLabel(APP_DESCRIPTION)
        descriptionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        descriptionLabel.setWordWrap(True)
        descriptionLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        descriptionRow = QtWidgets.QHBoxLayout()
        descriptionRow.setContentsMargins(64, 0, 64, 0)
        descriptionRow.addWidget(descriptionLabel)
        layout.addLayout(descriptionRow)

        layout.addSpacing(32)
        linkRow = QtWidgets.QHBoxLayout()
        linkRow.setContentsMargins(0, 0, 0, 0)
        linkRow.setSpacing(32)
        linkRow.addStretch(1)
        linkRow.addWidget(self.CreateAboutLinkItem("github", "Github", APP_GITHUB_URL))
        linkRow.addSpacing(8)
        linkRow.addWidget(self.CreateAboutLinkItem("bug_report_24dp_E3E3E3.svg", "Report Issue", APP_ISSUES_URL))
        linkRow.addSpacing(8)
        linkRow.addWidget(self.CreateAboutLinkItem("attribution_24dp_E3E3E3.svg", "Licenses", actionName = "licenses"))
        linkRow.addStretch(1)
        layout.addLayout(linkRow)
        layout.addSpacing(24)

        dismissFilter = ClickDismissFilter(dialog, {"licenses": self.ShowLicensesDialog})
        self.aboutDismissFilter = dismissFilter
        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(dismissFilter)

        def CleanupAboutDialog():
            if app and dismissFilter:
                app.removeEventFilter(dismissFilter)
            if getattr(self, "aboutDialog", None) is dialog:
                self.aboutDialog = None
            if dismissFilter and getattr(self, "aboutDismissFilter", None) is dismissFilter:
                self.aboutDismissFilter = None

        dialog.finished.connect(CleanupAboutDialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def OpenOutputOptionsPanel(self):
        self.UpdateOutputOptionsPanel()
        if hasattr(self, "outputOptionsButton") and not self.outputOptionsButton.isEnabled():
            return
        self.outputOptionsPanel.show()
        self.outputOptionsPanel.raise_()
        self.outputOptionsPanel.activateWindow()

    def OpenInputFolderBrowser(self):
        self.inputDirectory.Browse()

    def OpenOutputFolderBrowser(self):
        return self.outputDirectory.Browse()

    def SetExportMode(self, mode):
        if mode not in ("sequence", "final"):
            mode = "sequence"

        oldMode = self.exportMode
        self.exportMode = mode
        self.exportSequenceAction.setChecked(mode == "sequence")
        self.exportFinalBlendAction.setChecked(mode == "final")
        if mode == "final":
            self.exportButton.setText(IconButtonText("Export Final Blend Only"))
        else:
            self.exportButton.setText(IconButtonText("Export Sequence"))
        if hasattr(self, "outputNameTypeField") and hasattr(self.outputNameTypeField, "sequenceSuffixLabel"):
            self.outputNameTypeField.sequenceSuffixLabel.setVisible(mode != "final")
            self.UpdateOutputSequenceSuffixLabel()
        if mode != oldMode:
            self.MarkProjectDirty(section = "Export")

    def OutputSequenceFrameDigits(self):
        frameCount = len(self.InputReadFilenames()) if hasattr(self, "inputFileEntries") else 0
        skip = max(1, self.skipOutput.value()) if hasattr(self, "skipOutput") else 1
        outputFrameCount = ((frameCount - 1) // skip) + 1 if frameCount > 0 else 1
        return max(4, len(str(max(0, outputFrameCount - 1))))

    def UpdateOutputSequenceSuffixLabel(self, *_):
        if not hasattr(self, "outputNameTypeField") or not hasattr(self.outputNameTypeField, "sequenceSuffixLabel"):
            return

        digits = self.OutputSequenceFrameDigits()
        self.outputNameTypeField.sequenceSuffixLabel.setText(f"_{'0' * digits}.")

    def SetPreviewFrameCount(self, frameCount):
        self.previewFrameCount = "range" if str(frameCount).lower() == "range" else int(frameCount)
        for action in getattr(self, "previewFrameActions", {}).values():
            action.setChecked(False)
        action = getattr(self, "previewFrameActions", {}).get(self.previewFrameCount)
        if action:
            action.setChecked(True)
        if hasattr(self, "previewButton"):
            label = "Range" if self.previewFrameCount == "range" else str(self.previewFrameCount)
            self.previewButton.setText(IconButtonText(f"Generate Preview ({label})"))

    def UpdateBlendControlsEnabled(self, *_):
        self.decay.setEnabled((not self.runActive) and self.RenderPath() == 0 and self.blendMode.currentData() is not None)
        pairKernelEnabled = (not self.runActive) and self.RenderPath() == 1 and self.pairBlurSpinBox.value() > 0
        self.pairBlurKernel.setEnabled(pairKernelEnabled)
        self.pairKernelLabel.setEnabled(pairKernelEnabled)
        if hasattr(self, "blendScaleField"):
            self.blendScaleField.setEnabled(not self.runActive)
        if hasattr(self, "blendOffsetField"):
            self.blendOffsetField.setEnabled(not self.runActive)
        self.UpdateBlendResetButtons()

    def RenderPathClicked(self, *_):
        if hasattr(self, "presetComboBox"):
            index = self.presetComboBox.currentIndex()
            data = self.presetComboBox.itemData(index) if index >= 0 else None
            if isinstance(data, dict) and data.get("kind") in ("builtin", "user"):
                self.ClearLoadedPreset()
        self.MarkProjectDirty(section = "Blend")

    def UpdateTransferOverrideControls(self, *_):
        accessible = not self.runActive
        transferAccessible = accessible and self.blendInLinear.isChecked()
        self.overrideInputTransfer.setEnabled(transferAccessible)
        self.overrideOutputTransfer.setEnabled(transferAccessible)
        self.inputTransferFunction.setEnabled(transferAccessible and self.overrideInputTransfer.isChecked())
        self.outputTransferFunction.setEnabled(transferAccessible and self.overrideOutputTransfer.isChecked())
        self.overrideWidth.setEnabled(accessible and self.overrideResolution.isChecked())
        self.overrideHeight.setEnabled(accessible and self.overrideResolution.isChecked())

    def UpdateMiddleGrayControls(self, *_):
        enabled = (not self.runActive) and self.useCustomMiddleGray.isChecked()
        self.middleGray.setEnabled(enabled)
        self.middleGrayResetButton.setEnabled(
            (not self.runActive)
            and abs(self.middleGray.Value() - 0.5) > 0.0005
        )

    def CustomMiddleGrayToggled(self, checked):
        if not checked:
            self.middleGray.SetValue(0.5)
        self.UpdateMiddleGrayControls()

    def ResetMiddleGray(self):
        self.middleGray.SetValue(0.5)
        self.UpdateMiddleGrayControls()

    def EffectiveBaseImageFilename(self):
        if not self.inputPreviewFilenames:
            return None

        entries = self.DisplayInputFileEntries()
        return entries[0][0] if entries else None

    def EffectiveExportResolution(self):
        if not hasattr(self, "overrideWidth") or not hasattr(self, "overrideHeight"):
            return None

        if self.overrideResolution.isChecked():
            return (self.overrideWidth.value(), self.overrideHeight.value())

        filename = self.EffectiveBaseImageFilename()
        return self.CachedImageDimensions(filename) if filename else None

    def UpdateEffectiveOverrideValues(self, *_):
        if self.runActive:
            return

        filename = self.EffectiveBaseImageFilename()
        metadata = ReadImageMetadata(filename) if filename else {}

        inputOverrideActive = self.blendInLinear.isChecked() and self.overrideInputTransfer.isChecked()
        outputOverrideActive = self.blendInLinear.isChecked() and self.overrideOutputTransfer.isChecked()

        effectiveInputTransfer = (
            self._TransferFunctionValue(self.inputTransferFunction)
            if inputOverrideActive else
            self._TransferFunctionFromMetadata(metadata)
        )

        if not inputOverrideActive:
            self._SetTransferFunctionValue(self.inputTransferFunction, effectiveInputTransfer)

        if not outputOverrideActive:
            self._SetTransferFunctionValue(self.outputTransferFunction, effectiveInputTransfer)

        if not self.overrideResolution.isChecked():
            dimensions = self.EffectiveExportResolution()
            if dimensions:
                blocked = [self.overrideWidth.blockSignals(True), self.overrideHeight.blockSignals(True)]
                try:
                    self.overrideWidth.setValue(dimensions[0])
                    self.overrideHeight.setValue(dimensions[1])
                finally:
                    self.overrideWidth.blockSignals(blocked[0])
                    self.overrideHeight.blockSignals(blocked[1])
                self.RefreshInputDimensionWarnings()
                self.RefreshInputPreviewMetadata()

    def UpdateViewportScaling(self, *_):
        if hasattr(self, "inputViewport"):
            self.inputViewport.SetViewportScaling(self.viewportScaling.currentText())
        if hasattr(self, "previewViewport"):
            self.previewViewport.SetViewportScaling(self.viewportScaling.currentText())
        if hasattr(self, "outputViewport"):
            self.outputViewport.SetViewportScaling(self.viewportScaling.currentText())

    def ViewportTabChanged(self, *_):
        self.StopScrubberPlayback()
        self.UpdateInputSyncForViewportTab()
        if hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() == 2:
            self.UpdateOutputViewport()
        self.UpdateFrameScrubber()
        self.UpdateViewportInfoVisibility()
        self.UpdateViewportFooterControls()
        self.UpdatePreviewOptionsEnabled()

    def HandleTabShortcut(self, event):
        modifiers = event.modifiers() & ~QtCore.Qt.KeyboardModifier.KeypadModifier
        if modifiers != QtCore.Qt.KeyboardModifier.NoModifier:
            return False

        keyToAction = {
            QtCore.Qt.Key.Key_1: lambda: self.SetViewportTab(0),
            QtCore.Qt.Key.Key_2: lambda: self.SetViewportTab(1),
            QtCore.Qt.Key.Key_3: lambda: self.SetViewportTab(2),
            QtCore.Qt.Key.Key_4: lambda: self.SetSidebarTab(0),
            QtCore.Qt.Key.Key_5: lambda: self.SetSidebarTab(1),
            QtCore.Qt.Key.Key_6: lambda: self.SetSidebarTab(2),
        }
        action = keyToAction.get(event.key())
        if action is None or self.TabShortcutShouldYieldToFocusedWidget():
            return False

        action()
        event.accept()
        return True

    def TabShortcutShouldYieldToFocusedWidget(self):
        widget = QtWidgets.QApplication.focusWidget()
        while widget is not None:
            if isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox)):
                return True
            if isinstance(widget, QtWidgets.QComboBox) and widget.isEditable():
                return True
            widget = widget.parentWidget()
        return False

    def SetViewportTab(self, index):
        if not hasattr(self, "viewportTabs"):
            return

        index = int(index)
        if 0 <= index < self.viewportTabs.count():
            self.viewportTabs.setCurrentIndex(index)

    def SetSidebarTab(self, index):
        if not hasattr(self, "sidebarTabs"):
            return

        index = int(index)
        if 0 <= index < self.sidebarTabs.count():
            self.sidebarTabs.setCurrentIndex(index)

    def UpdateInputSyncForViewportTab(self):
        if not hasattr(self, "syncInputSelectionButton") or not hasattr(self, "viewportTabs"):
            return

        onInputTab = self.viewportTabs.currentIndex() == 0
        if not onInputTab:
            if not self.inputSyncSuspendedByViewport:
                self.inputSyncRestoreChecked = self.syncInputSelectionButton.isChecked()
                self.inputSyncSuspendedByViewport = True
            if self.syncInputSelectionButton.isChecked():
                self.syncInputSelectionButton.blockSignals(True)
                self.syncInputSelectionButton.setChecked(False)
                self.syncInputSelectionButton.blockSignals(False)
                self.UpdateInputFileSelectionMode()
            self.syncInputSelectionButton.setEnabled(False)
            self.UpdateInputFileActionButtons()
            return

        self.syncInputSelectionButton.setEnabled(True)
        if self.inputSyncSuspendedByViewport:
            restoreChecked = bool(self.inputSyncRestoreChecked)
            self.inputSyncSuspendedByViewport = False
            if self.syncInputSelectionButton.isChecked() != restoreChecked:
                self.syncInputSelectionButton.blockSignals(True)
                self.syncInputSelectionButton.setChecked(restoreChecked)
                self.syncInputSelectionButton.blockSignals(False)
                self.UpdateInputFileSelectionMode()
                if restoreChecked:
                    self.EnforceSingleInputFileSelection()
                    self.InputFileSelectionChanged()
        self.UpdateInputFileActionButtons()

    def OpenViewportContextMenu(self, viewport, globalPosition):
        menu = QtWidgets.QMenu(self)
        menu.setObjectName("viewportContextMenu")

        if viewport is self.inputViewport:
            self.AddViewportFileContextActions(menu, viewport)
        if menu.actions():
            menu.addSeparator()

        self.AddViewportMenuButton(menu, "zoom_in_24dp_E3E3E3.svg", "Zoom in", lambda: viewport.ZoomBy(1.25))
        self.AddViewportMenuButton(menu, "zoom_out_24dp_E3E3E3.svg", "Zoom out", lambda: viewport.ZoomBy(0.8))
        self.AddViewportMenuButton(menu, "refresh_24dp_E3E3E3.svg", "Reset zoom", lambda: self.ResetViewportZoom(viewport))
        menu.addSeparator()
        fullscreenIcon = "fullscreen_exit_24dp_E3E3E3.svg" if self.viewportOnlyMode else "fullscreen_24dp_E3E3E3.svg"
        self.AddViewportMenuButton(menu, fullscreenIcon, "Toggle Fullscreen", self.ToggleViewportOnlyMode)
        menu.addSeparator()

        if self.ViewportHasImage(viewport):
            self.AddViewportMenuButton(menu, "content_copy_24dp_E3E3E3.svg", "Copy image", self.CopyActiveViewportToClipboard, shortcutText = "Ctrl + C")
            menu.addSeparator()

        self.AddViewportInfoContextActions(menu, viewport)
        if (
            (viewport is self.inputViewport and self.CurrentInputViewportEntry())
            or (viewport is self.outputViewport and self.currentOutputPreviewFile)
        ):
            menu.addSeparator()

        self.AddViewportSubmenuButton(
            menu,
            "crop_3_2_24dp_E3E3E3.svg",
            "Viewport",
            lambda childMenu: self.PopulateViewportShowMenu(childMenu, viewport, menu),
        )

        menu.aboutToHide.connect(self.ClearPendingInputRemoveHighlight)
        menu.exec(globalPosition)
        self.ClearPendingInputRemoveHighlight()

    def PopulateViewportShowMenu(self, showMenu, viewport, rootMenu = None):
        allLabelsVisible = self.AllViewportOverlayOptionsVisible(viewport)
        noLabelsVisible = self.NoViewportOverlayOptionsVisible(viewport)
        showAllIcon = "check_24dp_E3E3E3.svg" if allLabelsVisible else ""
        hideAllIcon = "check_24dp_E3E3E3.svg" if noLabelsVisible else ""
        self.AddViewportMenuButton(showMenu, showAllIcon, "Show all labels", lambda: self.SetAllViewportOverlayOptions(True), closeMenu = rootMenu)
        self.AddViewportMenuButton(showMenu, hideAllIcon, "Hide all labels", lambda: self.SetAllViewportOverlayOptions(False), closeMenu = rootMenu)
        showMenu.addSeparator()

        def AddToggle(label, value, callback, visible = True, enabled = True):
            if not visible:
                return None
            iconName = "check_24dp_E3E3E3.svg" if value else ""
            button = self.AddViewportMenuButton(
                showMenu,
                iconName,
                label,
                lambda value = value, callback = callback: callback(not value),
                closeMenu = rootMenu,
            )
            button.setEnabled(enabled)
            return button

        AddToggle("Show dimensions", self.overlayShowDimensions, lambda checked: self.SetViewportOverlayOption("dimensions", checked))
        AddToggle(
            "Show color space",
            self.overlayShowColorSpace,
            lambda checked: self.SetViewportOverlayOption("colorSpace", checked),
            visible = viewport is not self.previewViewport,
        )
        AddToggle("Show coordinates", self.overlayShowCoordinates, lambda checked: self.SetViewportOverlayOption("coordinates", checked))
        AddToggle("Show zoom level", self.overlayShowZoom, lambda checked: self.SetViewportOverlayOption("zoom", checked))
        AddToggle("Show frame index", self.overlayShowFrameIndex, lambda checked: self.SetViewportOverlayOption("frameIndex", checked))
        AddToggle(
            "Show image index",
            self.overlayShowImageIndex,
            lambda checked: self.SetViewportOverlayOption("imageIndex", checked),
            visible = viewport is self.inputViewport,
        )

    def AddViewportFileContextActions(self, menu, viewport):
        if viewport is self.previewViewport:
            return

        if viewport is self.inputViewport:
            entry = self.CurrentInputViewportEntry()
            if not entry:
                return

            self.AddViewportMenuButton(menu, SplitAssetIcon("data_array_24dp_E3E3E3.svg", "left"), "Mark In", lambda entry = entry: self.MarkViewportInputFile("in", entry["id"]), shortcutText = "I")
            self.AddViewportMenuButton(menu, SplitAssetIcon("data_array_24dp_E3E3E3.svg", "right"), "Mark Out", lambda entry = entry: self.MarkViewportInputFile("out", entry["id"]), shortcutText = "O")
            menu.addSeparator()
            self.AddViewportMenuButton(menu, "visibility_off_24dp_E3E3E3.svg", "Disable image", lambda entry = entry: self.SetViewportInputFileEnabled(entry["id"], False))
            menu.addSeparator()
            self.AddViewportMenuButton(
                menu,
                "remove_24dp_E3E3E3.svg",
                "Remove image",
                lambda entry = entry: self.RemoveViewportInputFile(entry["id"]),
                dangerOnPress = True,
                pendingEntryIds = {entry["id"]},
            )
            return

    def AddViewportInfoContextActions(self, menu, viewport):
        if viewport is self.inputViewport:
            entry = self.CurrentInputViewportEntry()
            if not entry:
                return

            self.AddViewportMenuButton(menu, "folder_open_24dp_E3E3E3.svg", "Open containing folder", lambda entry = entry: self.OpenContainingFolder(entry["filename"]))
            self.AddViewportMenuButton(menu, "info_24dp_E3E3E3.svg", "Show image info", lambda entry = entry: self.ShowInputFileInfoDialog(entry))
            return

        if viewport is self.outputViewport and self.currentOutputPreviewFile:
            self.AddViewportMenuButton(menu, "folder_open_24dp_E3E3E3.svg", "Open containing folder", lambda: self.OpenContainingFolder(self.currentOutputPreviewFile))
            self.AddViewportMenuButton(menu, "info_24dp_E3E3E3.svg", "Show image info", lambda: self.ShowOutputFileInfoDialog(self.currentOutputPreviewFile))

    def AddViewportMenuButton(self, menu, iconName, text, callback, dangerOnPress = False, pendingEntryIds = None, shortcutText = "", closeMenu = None):
        action = QtWidgets.QWidgetAction(menu)
        button = QtWidgets.QPushButton()
        button.setObjectName("viewportMenuItem")
        button.setFlat(True)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setMinimumWidth(250)
        row = QtWidgets.QHBoxLayout(button)
        row.setContentsMargins(12, 0, 14, 0)
        row.setSpacing(14)

        icon = iconName if isinstance(iconName, QtGui.QIcon) else AssetIcon(iconName) if iconName else QtGui.QIcon()
        iconLabel = QtWidgets.QLabel()
        iconLabel.setObjectName("menuIconLabel")
        iconLabel.setFixedSize(18, 18)
        if not icon.isNull():
            iconLabel.setPixmap(icon.pixmap(18, 18))
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
        if dangerOnPress:
            button.pressed.connect(lambda entryIds = pendingEntryIds: self.MarkInputFilesPendingRemove(entryIds))
            button.released.connect(lambda button = button: self.ClearPendingInputRemoveIfButtonCancelled(button))

        def Trigger():
            menu.hide()
            if closeMenu is not None:
                closeMenu.hide()
            callback()

        button.clicked.connect(Trigger)
        action.setDefaultWidget(button)
        menu.addAction(action)
        return button

    def AddViewportSubmenuButton(self, menu, iconName, text, populateCallback, itemKind = "viewport"):
        action = QtWidgets.QWidgetAction(menu)
        button = QtWidgets.QPushButton()
        button.setObjectName("headerMenuItem" if itemKind == "header" else "viewportMenuItem")
        button.setCheckable(True)
        button.setFlat(True)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setMinimumWidth(250)
        row = QtWidgets.QHBoxLayout(button)
        row.setContentsMargins(12, 0, 14, 0)
        row.setSpacing(14)

        icon = iconName if isinstance(iconName, QtGui.QIcon) else AssetIcon(iconName) if iconName else QtGui.QIcon()
        iconLabel = QtWidgets.QLabel()
        iconLabel.setObjectName("menuIconLabel")
        iconLabel.setFixedSize(18, 18)
        if not icon.isNull():
            iconLabel.setPixmap(icon.pixmap(18, 18))
        iconLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        textLabel = QtWidgets.QLabel(text)
        textLabel.setObjectName("menuTextLabel")
        textLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        arrowLabel = QtWidgets.QLabel(">")
        arrowLabel.setObjectName("menuShortcutLabel")
        arrowLabel.setMinimumWidth(24)
        arrowLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        arrowLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        row.addWidget(iconLabel, 0)
        row.addWidget(textLabel, 0)
        row.addStretch(1)
        row.addWidget(arrowLabel, 0)

        controller = ContextSubmenuController(self, menu, button, populateCallback)
        button._submenuController = controller
        action.setDefaultWidget(button)
        menu.addAction(action)
        return button

    def ResetViewportZoom(self, viewport):
        viewport.ResetZoom()
        viewport.EmitViewportChanged()

    def ViewportOverlayOptions(self, viewport = None):
        if viewport is None:
            viewport = self.ActiveViewport()
        options = [
            self.overlayShowDimensions,
            self.overlayShowCoordinates,
            self.overlayShowZoom,
            self.overlayShowFrameIndex,
        ]
        if viewport is not self.previewViewport:
            options.append(self.overlayShowColorSpace)
        if viewport is self.inputViewport:
            options.append(self.overlayShowImageIndex)
        return options

    def AllViewportOverlayOptionsVisible(self, viewport = None):
        return all(self.ViewportOverlayOptions(viewport))

    def NoViewportOverlayOptionsVisible(self, viewport = None):
        return not any(self.ViewportOverlayOptions(viewport))

    def SetAllViewportOverlayOptions(self, checked):
        checked = bool(checked)
        self.overlayShowDimensions = checked
        self.overlayShowColorSpace = checked
        self.overlayShowCoordinates = checked
        self.overlayShowZoom = checked
        self.overlayShowFrameIndex = checked
        if self.ActiveViewport() is self.inputViewport:
            self.overlayShowImageIndex = checked
        self.UpdateViewportInfoVisibility()
        self.UpdatePreviewOverlay()

    def SetViewportOverlayOption(self, option, checked):
        checked = bool(checked)
        if option == "dimensions":
            self.overlayShowDimensions = checked
        elif option == "colorSpace":
            self.overlayShowColorSpace = checked
        elif option == "coordinates":
            self.overlayShowCoordinates = checked
        elif option == "zoom":
            self.overlayShowZoom = checked
        elif option == "frameIndex":
            self.overlayShowFrameIndex = checked
        elif option == "imageIndex":
            self.overlayShowImageIndex = checked

        self.UpdateViewportInfoVisibility()
        self.UpdatePreviewOverlay()

    def UpdateViewportInfoVisibility(self):
        if not hasattr(self, "inputViewport"):
            return

        renderViewport = self.RenderViewport() if self.runActive else None
        for viewport in (self.inputViewport, self.previewViewport, self.outputViewport):
            titleAlwaysVisible = (
                viewport is self.previewViewport
                or (self.runActive and viewport is renderViewport)
            )
            viewport.SetInfoVisibility(
                titleAlwaysVisible or viewport is not self.previewViewport,
                self.overlayShowDimensions,
                False if viewport is self.previewViewport else self.overlayShowColorSpace,
                self.overlayShowCoordinates,
                self.overlayShowZoom,
            )

    def UpdateViewportFooterControls(self):
        if not hasattr(self, "viewportTabs"):
            return

        if hasattr(self, "previewButton"):
            self.previewButton.setVisible(True)
            self.exportButton.setVisible(True)
            self.cancelButton.setVisible(True)
            if hasattr(self, "renderButtonStack"):
                self.renderButtonStack.setCurrentIndex(1 if self.runActive else 0)

    def ToggleViewportOnlyMode(self):
        self.SetViewportOnlyMode(not self.viewportOnlyMode)

    def SetViewportOnlyMode(self, enabled):
        enabled = bool(enabled)
        if self.viewportOnlyMode == enabled:
            return

        self.viewportOnlyMode = enabled
        if enabled and hasattr(self, "mainSplitter"):
            self.savedSplitterSizes = self.mainSplitter.sizes()

        if hasattr(self, "sidebarPanel"):
            self.sidebarPanel.setVisible(not enabled)
        if hasattr(self, "frameScrubber"):
            self.SetFrameScrubberOverlayMode(enabled)
        if hasattr(self, "progressRow"):
            self.progressRow.setVisible((not enabled) and self.runActive)
        if hasattr(self, "scrubberTransport"):
            self.scrubberTransport.setVisible(not self.runActive)
        if hasattr(self, "viewportTabs"):
            self.viewportTabs.tabBar().setVisible(not enabled)
            self.viewportTabs.setProperty("viewportOnly", enabled)
            self.viewportTabs.style().unpolish(self.viewportTabs)
            self.viewportTabs.style().polish(self.viewportTabs)
        if hasattr(self, "mainLayout"):
            self.mainLayout.setContentsMargins(0, 0, 0, 0) if enabled else self.mainLayout.setContentsMargins(12, 12, 12, 12)
        for viewport in (getattr(self, "inputViewport", None), getattr(self, "previewViewport", None), getattr(self, "outputViewport", None)):
            if viewport is not None:
                viewport.SetBorderVisible(not enabled)
        if hasattr(self, "fullscreenButton"):
            iconName = "fullscreen_exit_24dp_E3E3E3.svg" if enabled else "fullscreen_24dp_E3E3E3.svg"
            self.fullscreenButton.setIcon(AssetIcon(iconName))
            self.fullscreenButton.setToolTip("Exit viewport only" if enabled else "Viewport only")
        if hasattr(self, "viewportOverlay"):
            self.viewportOverlay.PositionOverlay()

        if (not enabled) and self.savedSplitterSizes and hasattr(self, "mainSplitter"):
            self.sidebarPanel.setVisible(True)
            self.mainSplitter.setSizes(self.savedSplitterSizes)
            self.savedSplitterSizes = None

        self.UpdateStatusBar()

    def SetFrameScrubberOverlayMode(self, enabled):
        if not hasattr(self, "frameScrubber"):
            return

        if enabled:
            if hasattr(self, "runLayout"):
                self.runLayout.removeWidget(self.frameScrubber)
            if hasattr(self, "viewportOverlay"):
                self.viewportOverlay.SetBottomOverlay(self.frameScrubber)
            self.frameScrubber.SetFullscreenMode(True)
            self.UpdateFullscreenScrubberView()
            self.frameScrubber.setVisible(True)
        else:
            if hasattr(self, "viewportOverlay"):
                self.viewportOverlay.ClearBottomOverlay()
            self.frameScrubber.SetFullscreenMode(False)
            if hasattr(self, "runLayout"):
                self.runLayout.insertWidget(self.frameScrubberLayoutIndex, self.frameScrubber)
            self.frameScrubber.setVisible(True)

        self.frameScrubber.setEnabled((not self.runActive) and self.frameScrubber.frameCount > 0)
        self.frameScrubber.updateGeometry()
        self.frameScrubber.update()
        if hasattr(self, "viewportOverlay"):
            self.viewportOverlay.PositionOverlay()

    def UpdateFullscreenScrubberView(self):
        if not getattr(self, "viewportOnlyMode", False) or not hasattr(self, "frameScrubber"):
            return

        trimBounds = self.ActiveInputTrimBounds()
        if trimBounds:
            trimStart, trimEnd = trimBounds
            self.frameScrubber.SetFullscreenViewRange(trimStart, trimEnd)
            if self.frameScrubber.value < trimStart or self.frameScrubber.value > trimEnd:
                self.frameScrubber.SetValue(trimStart, emit = True)
            return

        self.frameScrubber.SetFullscreenViewRange(0, max(0, self.frameScrubber.frameCount - 1))

    def UpdateOutputOptionsPanel(self, *_):
        if not hasattr(self, "outputOptionsStack"):
            return

        fileType = self._CleanFileType(self.outputFileType.currentText())
        pageIndex = self.outputOptionsPages.get(fileType, self.outputOptionsPages.get("bmp", 0))
        self.outputOptionsStack.setCurrentIndex(pageIndex)
        if hasattr(self, "outputOptionsButton"):
            hasOptions = fileType != "bmp"
            self.outputOptionsButton.setEnabled(hasOptions)
            self.outputOptionsButton.setToolTip(
                "File export options" if hasOptions else "BMP has no export options"
            )

    def PreviewSettingsAccessible(self):
        pausedRun = (
            self.runActive
            and self.pauseEvent is not None
            and self.pauseEvent.is_set()
        )
        return (not self.runActive) or pausedRun

    def UpdatePreviewOptionsEnabled(self, *_):
        accessible = self.PreviewSettingsAccessible()
        self.previewEnabled.setEnabled(accessible)
        self.previewScale.setEnabled(accessible)
        self.previewFps.setEnabled(accessible)

    def SyncActivePreviewSettings(self, *_):
        if not self.activeSettings:
            return

        renderScale = self.activeSettings.get("preview", {}).get("renderScale", 1)
        self.activeSettings["preview"] = {
            "enabled": self.previewEnabled.isChecked(),
            "scale": self.previewScale.currentData(),
            "fps": self.previewFps.value(),
            "renderScale": renderScale,
            "cacheLimitMb": self.previewCacheLimit.value(),
        }

    def _CleanFileType(self, fileType):
        return CanonicalFileType(fileType)

    def InputFileKey(self, filename):
        return os.path.normcase(os.path.abspath(filename))

    def InputFileOccurrenceKeyForRow(self, row):
        if not hasattr(self, "inputFileModel") or row < 0 or row >= self.inputFileModel.rowCount():
            return None

        index = self.inputFileModel.index(row, 0)
        filename = index.data(FILENAME_ROLE)
        entryId = index.data(ENTRY_ID_ROLE)
        if not filename or entryId is None:
            return None

        targetKey = self.InputFileKey(filename)
        occurrence = 0
        for displayRow in range(row + 1):
            displayIndex = self.inputFileModel.index(displayRow, 0)
            displayFilename = displayIndex.data(FILENAME_ROLE)
            if displayFilename and self.InputFileKey(displayFilename) == targetKey:
                occurrence += 1
        return targetKey, occurrence

    def EntryIdsForInputFileOccurrenceKeys(self, occurrenceKeys):
        if not hasattr(self, "inputFileModel"):
            return set()

        wanted = {
            tuple(key)
            for key in occurrenceKeys
            if isinstance(key, (list, tuple)) and len(key) == 2 and key[0] and key[1]
        }
        if not wanted:
            return set()

        counts = {}
        entryIds = set()
        for row in range(self.inputFileModel.rowCount()):
            index = self.inputFileModel.index(row, 0)
            filename = index.data(FILENAME_ROLE)
            entryId = index.data(ENTRY_ID_ROLE)
            if not filename or entryId is None:
                continue
            fileKey = self.InputFileKey(filename)
            counts[fileKey] = counts.get(fileKey, 0) + 1
            if (fileKey, counts[fileKey]) in wanted:
                entryIds.add(entryId)
        return entryIds

    def SyncInputPreviewFilenames(self):
        self.inputPreviewFilenames = [entry["filename"] for entry in self.inputFileEntries]

    def SortInputFileList(self):
        if not self.inputFileEntries:
            return

        self.inputFileEntries.sort(
            key = lambda entry: (
                os.path.basename(entry["filename"]).casefold(),
                os.path.normcase(entry["filename"]),
            ),
        )
        self.RefreshInputFileState()
        self.MarkProjectDirty()
        if self.InputSelectionSyncEnabled():
            self.InputFileSelectionChanged()

    def SortInputFileListNumerically(self):
        if not self.inputFileEntries:
            return

        self.inputFileEntries.sort(
            key = lambda entry: (
                self.NaturalFilenameSortKey(os.path.basename(entry["filename"])),
                os.path.normcase(entry["filename"]),
            ),
        )
        self.RefreshInputFileState()
        self.MarkProjectDirty()
        if self.InputSelectionSyncEnabled():
            self.InputFileSelectionChanged()

    def NaturalFilenameSortKey(self, filename):
        return tuple(
            (0, int(part)) if part.isdigit() else (1, part.casefold())
            for part in re.split(r"(\d+)", filename)
        )

    def AdjustTrimForReorderedInputFiles(self, oldEntries, oldRangeStart, oldRangeStop):
        if not hasattr(self, "rangeField") or not oldEntries:
            return

        oldFrameCount = len(oldEntries)
        newFrameCount = len(self.inputFileEntries)
        if oldRangeStart <= 0 and oldRangeStop >= oldFrameCount:
            self.rangeField.SetValues(0, newFrameCount)
            return

        oldRangeStart = max(0, min(oldRangeStart, oldFrameCount - 1))
        oldRangeStop = max(oldRangeStart + 1, min(oldRangeStop, oldFrameCount))
        oldRangeLength = max(1, oldRangeStop - oldRangeStart)
        startEntryId = oldEntries[oldRangeStart]["id"]

        newPositions = {
            entry["id"]: index
            for index, entry in enumerate(self.inputFileEntries)
        }
        if startEntryId not in newPositions:
            return

        newRangeLength = min(oldRangeLength, newFrameCount)
        newStart = min(newPositions[startEntryId], max(0, newFrameCount - newRangeLength))
        newStop = newStart + newRangeLength
        if (newStart, newStop) != self.InputTrimRange():
            self.rangeField.SetValues(newStart, newStop)

    def MoveInputFileEntries(self, selectedEntryIds, targetDisplayRow):
        if self.InputSelectionSyncChecked() or not selectedEntryIds:
            return

        displayIds = [
            entryId
            for _filename, _sourceIndex, entryId in self.DisplayInputFileEntries()
        ]
        selectedSet = set(selectedEntryIds)
        selectedIds = [entryId for entryId in displayIds if entryId in selectedSet]
        if not selectedIds:
            return

        targetDisplayRow = max(0, min(int(targetDisplayRow), len(displayIds)))
        selectedRowsBeforeTarget = sum(
            1 for row, entryId in enumerate(displayIds)
            if row < targetDisplayRow and entryId in selectedSet
        )
        adjustedTarget = targetDisplayRow - selectedRowsBeforeTarget
        remainingIds = [entryId for entryId in displayIds if entryId not in selectedSet]
        adjustedTarget = max(0, min(adjustedTarget, len(remainingIds)))
        newDisplayIds = remainingIds[:adjustedTarget] + selectedIds + remainingIds[adjustedTarget:]

        if newDisplayIds == displayIds:
            return

        sourceIds = newDisplayIds
        entryById = {entry["id"]: entry for entry in self.inputFileEntries}
        if set(sourceIds) != set(entryById):
            return

        oldEntries = list(self.inputFileEntries)
        oldRangeStart, oldRangeStop = self.InputTrimRange()
        self.inputFileEntries = [entryById[entryId] for entryId in sourceIds]
        self.SyncInputPreviewFilenames()
        if hasattr(self, "rangeField"):
            self.rangeField.SetMaximum(len(self.inputPreviewFilenames))
            self.AdjustTrimForReorderedInputFiles(oldEntries, oldRangeStart, oldRangeStop)
        scrollValue = self.inputFileList.verticalScrollBar().value()
        self.pendingInputFileListScroll = scrollValue
        self.RefreshInputFileState()
        self.suppressInputFileSelectionSync = True
        try:
            selection = self.inputFileList.selectionModel()
            if selection:
                selection.clearSelection()
                firstIndex = None
                for entryId in selectedIds:
                    row = self.inputFileModel.RowForEntryId(entryId)
                    if row is None:
                        continue
                    index = self.inputFileModel.index(row, 0)
                    selection.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
                    if firstIndex is None:
                        firstIndex = index
                if firstIndex is not None:
                    selection.setCurrentIndex(firstIndex, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
                self.inputFileList.verticalScrollBar().setValue(scrollValue)
        finally:
            self.suppressInputFileSelectionSync = False
        self.UpdateInputFileActionButtons()
        self.MarkProjectDirty()

    def MoveSelectedInputFilesBy(self, offset):
        if self.InputSelectionSyncChecked() or not hasattr(self, "inputFileModel"):
            return

        selection = self.inputFileList.selectionModel()
        selectedRows = sorted(index.row() for index in selection.selectedRows()) if selection else []
        if not selectedRows:
            return

        offset = int(offset)
        if offset < 0:
            if selectedRows[0] <= 0:
                return
            targetRow = selectedRows[0] - 1
        elif offset > 0:
            if selectedRows[-1] >= self.inputFileModel.rowCount() - 1:
                return
            targetRow = selectedRows[-1] + 2
        else:
            return

        selectedEntryIds = [
            self.inputFileModel.index(row, 0).data(ENTRY_ID_ROLE)
            for row in selectedRows
            if self.inputFileModel.index(row, 0).data(ENTRY_ID_ROLE) is not None
        ]
        self.MoveInputFileEntries(selectedEntryIds, targetRow)
        self.UpdateInputFileActionButtons()

    def UpdateInputFileActionButtons(self):
        if not hasattr(self, "inputFileModel") or not hasattr(self, "moveInputFileUpButton"):
            return

        selection = self.inputFileList.selectionModel()
        selectedRows = sorted(index.row() for index in selection.selectedRows()) if selection else []
        hasFiles = self.inputFileModel.rowCount() > 0
        hasSelection = bool(selectedRows)
        singleSelection = len(selectedRows) == 1
        canMove = hasSelection and not self.InputSelectionSyncChecked() and not self.runActive
        if hasattr(self, "sortInputFilesButton"):
            self.sortInputFilesButton.setEnabled(hasFiles and not self.runActive)
        if hasattr(self, "sortInputFilesNumericButton"):
            self.sortInputFilesNumericButton.setEnabled(hasFiles and not self.runActive)
        if hasattr(self, "reverseInput"):
            self.reverseInput.setEnabled(hasFiles and not self.runActive)
        self.moveInputFileUpButton.setEnabled(canMove and selectedRows[0] > 0)
        self.moveInputFileDownButton.setEnabled(canMove and selectedRows[-1] < self.inputFileModel.rowCount() - 1)
        self.removeInputFileButton.setEnabled(hasSelection and not self.runActive)
        if hasattr(self, "markInputInButton"):
            self.markInputInButton.setEnabled(singleSelection and not self.runActive)
        if hasattr(self, "markInputOutButton"):
            self.markInputOutButton.setEnabled(singleSelection and not self.runActive)
        if hasattr(self, "clearInputRangeButton"):
            self.clearInputRangeButton.setEnabled(self.TrimRangeIsActive() and not self.runActive)
        if hasattr(self, "removeAllInputFilesButton"):
            self.removeAllInputFilesButton.setEnabled(hasFiles and not self.runActive)

    def AddInputFilesToRenderList(self, filenames):
        filenames = [filename for filename in filenames if filename]
        if not filenames:
            return []

        startedUndoTransaction = False
        if not self.suppressProjectDirty and self.pendingUndoTransactionSnapshot is None:
            self.BeginUndoTransaction()
            startedUndoTransaction = True

        oldCount = len(self.inputPreviewFilenames)
        wasFullRange = True
        if hasattr(self, "rangeField"):
            rangeStart, rangeStop = self.InputTrimRange()
            wasFullRange = rangeStart <= 0 and rangeStop >= oldCount

        addedEntryIds = []
        for filename in filenames:
            entryId = self.nextInputEntryId
            self.inputFileEntries.append({
                "id": entryId,
                "filename": os.path.normpath(filename),
                "transferOverrideEnabled": False,
                "transferFunction": "sRGB / Display P3",
            })
            addedEntryIds.append(entryId)
            self.nextInputEntryId += 1
            self.RefreshInputEntryTransferWarning(entryId, filename, refreshList = False)
        self.SyncInputPreviewFilenames()
        if hasattr(self, "rangeField"):
            self.rangeField.SetMaximum(
                len(self.inputPreviewFilenames),
                useFullRange = wasFullRange,
            )
        if startedUndoTransaction:
            self.EndUndoTransaction()
        elif addedEntryIds:
            self.MarkProjectDirty()
        return addedEntryIds

    def SupportedInputExtensions(self):
        extensions = []
        for fileType in INPUT_TYPES:
            for extension in FileTypeExtensions(fileType):
                if extension not in extensions:
                    extensions.append(extension)
        return extensions

    def InputFileDialogFilter(self):
        supportedPatterns = " ".join(f"*.{extension}" for extension in self.SupportedInputExtensions())
        filters = [f"Supported Images ({supportedPatterns})"]
        for fileType in INPUT_TYPES:
            patterns = " ".join(f"*.{extension}" for extension in FileTypeExtensions(fileType))
            filters.append(f"{fileType.upper()} ({patterns})")
        return ";;".join(filters)

    def InputFilenameIsSupported(self, filename):
        extension = os.path.splitext(filename)[1].lower().lstrip(".")
        return extension in set(self.SupportedInputExtensions())

    def FindSupportedInputFilenames(self, directory):
        supportedExtensions = set(self.SupportedInputExtensions())
        filenames = []
        for filename in os.listdir(directory):
            path = os.path.join(directory, filename)
            extension = os.path.splitext(filename)[1].lower().lstrip(".")
            if os.path.isfile(path) and extension in supportedExtensions:
                filenames.append(path)
        return sorted(filenames)

    def SelectInputEntry(self, entryId):
        if entryId is None or not hasattr(self, "inputFileModel"):
            return

        self.suppressInputFileSelectionSync = True
        try:
            row = self.inputFileModel.RowForEntryId(entryId)
            if row is None:
                return

            index = self.inputFileModel.index(row, 0)
            selection = self.inputFileList.selectionModel()
            selection.clearSelection()
            selection.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
            selection.setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
            self.inputFileList.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
        finally:
            self.suppressInputFileSelectionSync = False

    def OpenInputFileBrowser(self):
        startPath = self.lastInputBrowserDirectory
        if not os.path.isdir(startPath):
            startPath = os.getcwd()

        filenames, _selectedFilter = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select Image Files",
            startPath,
            self.InputFileDialogFilter(),
        )
        if not filenames:
            return

        filenames = [filename for filename in filenames if self.InputFilenameIsSupported(filename)]
        if not filenames:
            self.ShowWarningMessage("Image File", "Choose a supported image file.")
            return

        self.lastInputBrowserDirectory = os.path.dirname(filenames[-1])
        self.inputDirectory.SetStartPath(self.lastInputBrowserDirectory)
        addedEntryIds = self.AddInputFilesToRenderList(filenames)
        self.RefreshInputFileState()
        if addedEntryIds:
            self.SelectInputEntry(addedEntryIds[-1])

    def InputDropHasSupportedPaths(self, mimeData):
        if not mimeData or not mimeData.hasUrls():
            return False

        return bool(self.InputPathsFromMimeData(mimeData, collect = False))

    def InputPathsFromMimeData(self, mimeData, collect = True):
        paths = []
        for url in mimeData.urls() if mimeData and mimeData.hasUrls() else []:
            path = url.toLocalFile()
            if not path:
                continue
            if os.path.isdir(path):
                if collect:
                    paths.extend(self.FindSupportedInputFilenames(path))
                else:
                    return [path]
            elif os.path.isfile(path) and self.InputFilenameIsSupported(path):
                if collect:
                    paths.append(path)
                else:
                    return [path]
        return paths

    def AddDroppedInputPaths(self, mimeData):
        filenames = self.InputPathsFromMimeData(mimeData, collect = True)
        if not filenames:
            return False

        self.lastInputBrowserDirectory = self.DropStartDirectory(mimeData, filenames)
        if self.lastInputBrowserDirectory:
            self.inputDirectory.SetStartPath(self.lastInputBrowserDirectory)

        addedEntryIds = self.AddInputFilesToRenderList(filenames)
        self.RefreshInputFileState()
        if addedEntryIds:
            self.SelectInputEntry(addedEntryIds[-1])
        return True

    def DropStartDirectory(self, mimeData, filenames):
        for url in mimeData.urls() if mimeData and mimeData.hasUrls() else []:
            path = url.toLocalFile()
            if os.path.isdir(path):
                return path
            if os.path.isfile(path):
                return os.path.dirname(path)
        return os.path.dirname(filenames[-1]) if filenames else ""

    def RestoreInputFileEntries(self, files, refresh = True):
        oldEntries = list(getattr(self, "inputFileEntries", []))
        oldDisabledIds = set(getattr(self, "disabledInputFilenames", set()))
        oldMissingIds = set(getattr(self, "missingInputFilenames", set()))
        oldRescaleWarningIds = set(getattr(self, "rescaleWarningInputFilenames", set()))
        oldTransferWarningIds = set(getattr(self, "transferWarningInputFilenames", set()))
        oldDimensionCache = dict(getattr(self, "inputDimensionCache", {}))
        oldOccurrenceIds = {}
        occurrenceCounts = {}
        for entry in oldEntries:
            fileKey = self.InputFileKey(entry["filename"])
            occurrenceCounts[fileKey] = occurrenceCounts.get(fileKey, 0) + 1
            oldOccurrenceIds[(fileKey, occurrenceCounts[fileKey])] = entry["id"]

        self.inputFileEntries = []
        self.disabledInputFilenames = set()
        self.removedInputFilenames = set()
        self.missingInputFilenames = set()
        self.rescaleWarningInputFilenames = set()
        self.transferWarningInputFilenames = set()
        self.nextInputEntryId = 1
        usedEntryIds = set()
        newDimensionCache = {}

        newOccurrenceCounts = {}
        for item in files if isinstance(files, list) else []:
            if isinstance(item, dict):
                filename = str(item.get("path", "")).strip()
                enabled = bool(item.get("enabled", True))
                transferOverrideEnabled = bool(item.get("transferOverrideEnabled", False))
                transferFunction = str(item.get("transferFunction", "sRGB / Display P3"))
            else:
                filename = str(item).strip()
                enabled = True
                transferOverrideEnabled = False
                transferFunction = "sRGB / Display P3"
            if not filename:
                continue

            filename = os.path.normpath(filename)
            fileKey = self.InputFileKey(filename)
            newOccurrenceCounts[fileKey] = newOccurrenceCounts.get(fileKey, 0) + 1
            entryId = oldOccurrenceIds.get((fileKey, newOccurrenceCounts[fileKey]))
            if entryId is None or entryId in usedEntryIds:
                while self.nextInputEntryId in usedEntryIds:
                    self.nextInputEntryId += 1
                entryId = self.nextInputEntryId
            usedEntryIds.add(entryId)
            self.nextInputEntryId = max(self.nextInputEntryId, entryId + 1)
            self.inputFileEntries.append({
                "id": entryId,
                "filename": filename,
                "transferOverrideEnabled": transferOverrideEnabled,
                "transferFunction": transferFunction,
            })
            if not enabled:
                self.disabledInputFilenames.add(entryId)
            elif entryId in oldDisabledIds and enabled:
                self.disabledInputFilenames.discard(entryId)
            if entryId in oldMissingIds:
                self.missingInputFilenames.add(entryId)
            if entryId in oldRescaleWarningIds:
                self.rescaleWarningInputFilenames.add(entryId)
            if entryId in oldTransferWarningIds:
                self.transferWarningInputFilenames.add(entryId)
            if filename in oldDimensionCache:
                newDimensionCache[filename] = oldDimensionCache[filename]

        self.SyncInputPreviewFilenames()
        self.inputDimensionCache = newDimensionCache
        if self.blendInLinear.isChecked():
            for entry in self.inputFileEntries:
                self.RefreshInputEntryTransferWarning(entry["id"], refreshList = False)
        elif self.transferWarningInputFilenames:
            self.transferWarningInputFilenames = set()
        if hasattr(self, "rangeField"):
            self.rangeField.SetMaximum(len(self.inputPreviewFilenames), useFullRange = True)
        if refresh:
            self.RefreshInputFileState(preserveScrubberView = True)

    def AddInputFolderToRenderList(self, directory):
        directory = str(directory or "").strip()
        if not directory or not os.path.isdir(directory):
            return

        self.lastInputBrowserDirectory = directory
        self.inputDirectory.SetStartPath(directory)
        filenames = self.FindSupportedInputFilenames(directory)
        if not filenames:
            self.RefreshInputStatusLabel()
            return

        self.AddInputFilesToRenderList(filenames)
        self.RefreshInputFileState()

    def RestoreDisabledInputFiles(self, disabledFiles):
        disabledNames = {
            os.path.normcase(str(filename))
            for filename in disabledFiles
            if str(filename).strip()
        }
        self.disabledInputFilenames = {
            self.InputFileKey(filename)
            for filename in self.inputPreviewFilenames
            if os.path.normcase(os.path.basename(filename)) in disabledNames
        }
        self.RefreshInputFileList()
        self.RefreshInputStatusLabel()
        self.RefreshInputPreviewMetadata()
        self.UpdateEffectiveOverrideValues()
        self.UpdateRangePreview()
        self.UpdateStackSizeMaximum()
        self.UpdateFrameScrubber()
        self.UpdateFrameScrubberHighlight()

    def RestoreRemovedInputFiles(self, removedFiles):
        removedNames = {
            os.path.normcase(str(filename))
            for filename in removedFiles
            if str(filename).strip()
        }
        self.removedInputFilenames = {
            self.InputFileKey(filename)
            for filename in self.inputPreviewFilenames
            if os.path.normcase(os.path.basename(filename)) in removedNames
        }
        self.disabledInputFilenames = {
            key for key in self.disabledInputFilenames
            if key not in self.removedInputFilenames
        }
        self.RefreshInputFileState()

    def ClearRemovedInputFilesForFolderOpen(self, _path = ""):
        self.removedInputFilenames = set()

    def SourceIndexForInputFile(self, filename):
        target = self.InputFileKey(filename)
        for index, inputFilename in enumerate(self.inputPreviewFilenames):
            if self.InputFileKey(inputFilename) == target:
                return index
        return None

    def SourceIndexForInputEntry(self, entryId):
        for index, entry in enumerate(self.inputFileEntries):
            if entry["id"] == entryId:
                return index
        return None

    def EntryIdForInputFilename(self, filename):
        target = self.InputFileKey(filename)
        for entry in self.inputFileEntries:
            if self.InputFileKey(entry["filename"]) == target:
                return entry["id"]
        return None

    def SetInputEntryMissing(self, entryId, missing = True):
        if entryId is None:
            return False

        wasMissing = entryId in self.missingInputFilenames
        if missing:
            self.missingInputFilenames.add(entryId)
        else:
            self.missingInputFilenames.discard(entryId)
        return wasMissing != missing

    def CheckInputEntryFileExists(self, entryId, filename):
        missing = not os.path.isfile(filename)
        if self.SetInputEntryMissing(entryId, missing):
            self.RefreshInputFileList()
        return not missing

    def EffectiveOutputResolution(self):
        return self.EffectiveExportResolution()

    def SetInputEntryRescaleWarning(self, entryId, warning = True):
        if entryId is None:
            return False

        hadWarning = entryId in self.rescaleWarningInputFilenames
        if warning:
            self.rescaleWarningInputFilenames.add(entryId)
        else:
            self.rescaleWarningInputFilenames.discard(entryId)
        return hadWarning != warning

    def SetInputEntryTransferWarning(self, entryId, warning = True):
        if entryId is None:
            return False

        hadWarning = entryId in self.transferWarningInputFilenames
        if warning:
            self.transferWarningInputFilenames.add(entryId)
        else:
            self.transferWarningInputFilenames.discard(entryId)
        return hadWarning != warning

    def CachedInputMetadata(self, filename):
        filename = os.path.normpath(filename or "")
        if not filename:
            return {}
        cached = self.inputMetadataCache.get(filename)
        if cached is not None:
            return cached
        metadata = ReadImageMetadata(filename)
        self.inputMetadataCache[filename] = metadata
        return metadata

    def RefreshInputEntryTransferWarning(self, entryId, filename = None, metadata = None, refreshList = True):
        entry = self.InputEntryById(entryId)
        if not entry:
            return False

        filename = filename or entry.get("filename")
        if not self.blendInLinear.isChecked():
            changed = self.SetInputEntryTransferWarning(entryId, False)
        elif entryId in self.missingInputFilenames or not filename or not os.path.isfile(filename):
            changed = self.SetInputEntryTransferWarning(entryId, False)
        elif self.InputEntryTransferOverride(entry):
            changed = self.SetInputEntryTransferWarning(entryId, False)
        else:
            try:
                metadata = metadata or self.CachedInputMetadata(filename)
                warning = IsUnknownTransferFunction(metadata.get("transfer"))
            except (OSError, FileNotFoundError):
                warning = False
            changed = self.SetInputEntryTransferWarning(entryId, warning)

        if changed and refreshList:
            self.RefreshInputFileList()
        return changed

    def RefreshInputTransferWarnings(self, *_args, refreshList = True):
        if not self.blendInLinear.isChecked():
            changed = bool(self.transferWarningInputFilenames)
            self.transferWarningInputFilenames = set()
            if changed and refreshList:
                self.RefreshInputFileList()
            return

        changed = False
        for entry in self.inputFileEntries:
            entryId = entry["id"]
            changed = self.RefreshInputEntryTransferWarning(entryId, refreshList = False) or changed

        if changed and refreshList:
            self.RefreshInputFileList()

    def RefreshInputDimensionWarnings(self, *_args, refreshList = True):
        targetResolution = self.EffectiveOutputResolution()
        if not targetResolution:
            return

        changed = False
        for entry in self.inputFileEntries:
            dimensions = self.CachedImageDimensions(entry["filename"])
            if dimensions is None and entry["id"] in self.missingInputFilenames:
                continue
            warning = bool(dimensions and dimensions != targetResolution)
            changed = self.SetInputEntryRescaleWarning(entry["id"], warning) or changed

        if changed and refreshList:
            self.RefreshInputFileList()

    def RefreshExportResolutionWarnings(self, *_args):
        self.RefreshInputDimensionWarnings()
        self.RefreshInputPreviewMetadata()

    def RefreshMissingInputFiles(self):
        changed = False
        for entry in self.inputFileEntries:
            changed = self.SetInputEntryMissing(entry["id"], not os.path.isfile(entry["filename"])) or changed
        if changed:
            self.RefreshInputFileList()

    def MarkMissingInputFiles(self, filenames):
        missingKeys = {self.InputFileKey(filename) for filename in filenames}
        changed = False
        for entry in self.inputFileEntries:
            if self.InputFileKey(entry["filename"]) in missingKeys:
                changed = self.SetInputEntryMissing(entry["id"], True) or changed
        if changed:
            self.RefreshInputFileList()

    def MarkMissingInputFilesFromError(self, errorText):
        changed = False
        normalizedError = os.path.normcase(str(errorText))
        for entry in self.inputFileEntries:
            filename = entry["filename"]
            if (
                self.InputFileKey(filename) in normalizedError
                or os.path.normcase(os.path.basename(filename)) in normalizedError
            ):
                changed = self.SetInputEntryMissing(entry["id"], True) or changed
        if changed:
            self.RefreshInputFileList()

    def DisplayInputFileEntries(self, includeRemoved = False):
        indexedEntries = list(enumerate(self.inputFileEntries))

        entries = []
        for sourceIndex, entry in indexedEntries:
            if not includeRemoved and entry["id"] in self.removedInputFilenames:
                continue
            entries.append((entry["filename"], sourceIndex, entry["id"]))
        return entries

    def EnabledFrameCountInSourceRange(self, rangeStart, rangeStop):
        count = 0
        for filename, sourceIndex in self.EnabledInputFilenamesWithSourceIndices():
            if rangeStart <= sourceIndex < rangeStop:
                count += 1
        return count

    def AdjustTrimForDisabledFrame(self, sourceIndex, targetEnabledCount):
        if sourceIndex is None or not hasattr(self, "rangeField"):
            return

        frameCount = len(self.inputPreviewFilenames)
        if frameCount <= 0:
            return

        rangeStart, rangeStop = self.InputTrimRange()
        if rangeStart <= 0 and rangeStop >= frameCount:
            return
        if not (rangeStart <= sourceIndex < rangeStop):
            return

        newStop = rangeStop
        while (
            newStop < frameCount
            and self.EnabledFrameCountInSourceRange(rangeStart, newStop) < targetEnabledCount
        ):
            newStop += 1

        if newStop != rangeStop:
            self.rangeField.SetValues(rangeStart, newStop)

    def AdjustTrimForReenabledFrame(self, sourceIndex, targetEnabledCount):
        if sourceIndex is None or not hasattr(self, "rangeField"):
            return

        frameCount = len(self.inputPreviewFilenames)
        if frameCount <= 0:
            return

        rangeStart, rangeStop = self.InputTrimRange()
        if rangeStart <= 0 and rangeStop >= frameCount:
            return
        if not (rangeStart <= sourceIndex < rangeStop):
            return

        newStop = rangeStop
        while (
            newStop > rangeStart + 1
            and self.EnabledFrameCountInSourceRange(rangeStart, newStop) > targetEnabledCount
        ):
            newStop -= 1

        if newStop != rangeStop:
            self.rangeField.SetValues(rangeStart, newStop)

    def SetInputFileEnabled(self, entryId, enabled):
        if entryId is None:
            return False

        currentlyEnabled = entryId not in self.disabledInputFilenames
        if currentlyEnabled == enabled:
            return False

        sourceIndex = self.SourceIndexForInputEntry(entryId)
        rangeStart, rangeStop = self.InputTrimRange()
        targetEnabledCount = self.EnabledFrameCountInSourceRange(rangeStart, rangeStop)
        previousSuppressRangePreview = self.suppressRangePreview
        self.suppressRangePreview = True
        try:
            if enabled:
                self.disabledInputFilenames.remove(entryId)
                self.AdjustTrimForReenabledFrame(sourceIndex, targetEnabledCount)
            else:
                self.disabledInputFilenames.add(entryId)
                self.AdjustTrimForDisabledFrame(sourceIndex, targetEnabledCount)
        finally:
            self.suppressRangePreview = previousSuppressRangePreview
        return True

    def SetInputFilesEnabled(self, entryIds, enabled):
        entryIds = {entryId for entryId in entryIds if entryId is not None}
        if not entryIds:
            return False

        changingIds = {
            entryId for entryId in entryIds
            if (entryId not in self.disabledInputFilenames) != bool(enabled)
        }
        if not changingIds:
            return False

        rangeStart, rangeStop = self.InputTrimRange()
        frameCount = len(self.inputPreviewFilenames)
        fullRange = rangeStart <= 0 and rangeStop >= frameCount
        targetEnabledCount = self.EnabledFrameCountInSourceRange(rangeStart, rangeStop)
        changedInsideTrim = any(
            rangeStart <= sourceIndex < rangeStop
            for sourceIndex, entry in enumerate(self.inputFileEntries)
            if entry["id"] in changingIds
        )

        if enabled:
            self.disabledInputFilenames.difference_update(changingIds)
        else:
            self.disabledInputFilenames.update(changingIds)

        previousSuppressRangePreview = self.suppressRangePreview
        self.suppressRangePreview = True
        try:
            if not fullRange and changedInsideTrim and hasattr(self, "rangeField"):
                newStop = rangeStop
                if enabled:
                    while (
                        newStop > rangeStart + 1
                        and self.EnabledFrameCountInSourceRange(rangeStart, newStop) > targetEnabledCount
                    ):
                        newStop -= 1
                else:
                    while (
                        newStop < frameCount
                        and self.EnabledFrameCountInSourceRange(rangeStart, newStop) < targetEnabledCount
                    ):
                        newStop += 1

                if newStop != rangeStop:
                    self.rangeField.SetValues(rangeStart, newStop)
        finally:
            self.suppressRangePreview = previousSuppressRangePreview

        return True

    def RefreshInputFileState(self, preserveScrubberView = False, refreshWarnings = False):
        scrubberSnapshot = self.ScrubberViewSnapshot() if preserveScrubberView else None
        preserveSelectionEntryIds = (
            set(self.pendingInputSelectionEntryIds)
            if self.pendingInputSelectionEntryIds is not None else
            None
        )
        self.SyncInputPreviewFilenames()
        if hasattr(self, "rangeField"):
            self.rangeField.SetMaximum(len(self.inputPreviewFilenames))
        if refreshWarnings:
            self.RefreshInputDimensionWarnings(refreshList = False)
            self.RefreshInputTransferWarnings(refreshList = False)
        self.RefreshInputFileList()
        self.RefreshInputStatusLabel()
        self.RefreshInputPreviewMetadata()
        self.UpdateEffectiveOverrideValues()
        self.UpdateStackSizeMaximum()
        if preserveScrubberView:
            self.UpdateFrameScrubber(preserveView = True)
            self.UpdateFrameScrubberHighlight()
            self.RestoreScrubberViewSnapshot(scrubberSnapshot)
            if self.ActiveScrubberFilenames():
                self.FrameScrubberChanged(self.frameScrubber.value, preserveView = True)
                self.RestoreScrubberViewSnapshot(scrubberSnapshot)
                self.UpdatePreviewOverlay()
            else:
                self.ClearInputPreview(preserveScrubberView = True)
        else:
            self.UpdateRangePreview()
            self.UpdateFrameScrubber()
            self.UpdateFrameScrubberHighlight()
        if preserveSelectionEntryIds:
            self.RestoreInputFileSelection(preserveSelectionEntryIds)
        self.UpdateOutputSequenceSuffixLabel()
        self.UpdateRunButtons()

    def ScrubberViewSnapshot(self):
        if not hasattr(self, "frameScrubber"):
            return None

        return {
            "value": self.frameScrubber.value,
            "viewStart": self.frameScrubber.viewStart,
            "viewEnd": self.frameScrubber.viewEnd,
        }

    def RestoreScrubberViewSnapshot(self, snapshot):
        if not snapshot or not hasattr(self, "frameScrubber") or self.frameScrubber.frameCount <= 0:
            return

        maxFrame = float(max(0, self.frameScrubber.frameCount - 1))
        value = max(0, min(int(snapshot["value"]), int(maxFrame)))

        self.frameScrubber.updating = True
        try:
            self.frameScrubber.value = value
            self.frameScrubber.RestoreViewRange(snapshot["viewStart"], snapshot["viewEnd"])
            self.frameScrubber.update()
        finally:
            self.frameScrubber.updating = False

    def ToggleInputFileEnabled(self, row):
        if not hasattr(self, "inputFileModel") or row < 0 or row >= self.inputFileModel.rowCount():
            return

        entryId = self.inputFileModel.EntryIdAt(row)
        if entryId is None:
            return

        currentSelection = {
            index.data(ENTRY_ID_ROLE)
            for index in self.inputFileList.selectionModel().selectedRows()
            if index.data(ENTRY_ID_ROLE) is not None
        }
        if not currentSelection:
            current = self.inputFileList.currentIndex()
            currentId = current.data(ENTRY_ID_ROLE) if current.isValid() else None
            if currentId is not None:
                currentSelection.add(currentId)
        self.pendingInputSelectionEntryIds = currentSelection or {entryId}

        enabled = entryId in self.disabledInputFilenames
        if self.SetInputFileEnabled(entryId, enabled):
            self.RefreshInputFileState(preserveScrubberView = True)
            self.MarkProjectDirty()
            restoreSelection = set(self.pendingInputSelectionEntryIds or currentSelection or {entryId})
            QtCore.QTimer.singleShot(0, lambda entryIds = restoreSelection: self.RestoreInputFileSelection(entryIds))

    def SelectedInputFileListEntries(self):
        if not hasattr(self, "inputFileModel"):
            return []

        selection = self.inputFileList.selectionModel()
        selectedRows = sorted(index.row() for index in selection.selectedRows()) if selection else []
        entries = [
            (
                self.inputFileModel.data(self.inputFileModel.index(row, 0), FILENAME_ROLE),
                self.inputFileModel.data(self.inputFileModel.index(row, 0), ENTRY_ID_ROLE),
            )
            for row in selectedRows
            if self.inputFileModel.data(self.inputFileModel.index(row, 0), FILENAME_ROLE)
            and self.inputFileModel.data(self.inputFileModel.index(row, 0), ENTRY_ID_ROLE) is not None
        ]
        if entries:
            return entries

        current = self.inputFileList.currentIndex()
        filename = current.data(FILENAME_ROLE) if current.isValid() else None
        entryId = current.data(ENTRY_ID_ROLE) if current.isValid() else None
        return [(filename, entryId)] if filename and entryId is not None else []

    def SelectedInputFileListFilenames(self):
        return [filename for filename, _entryId in self.SelectedInputFileListEntries()]

    def RestoreInputFileSelection(self, entryIds):
        if not hasattr(self, "inputFileModel") or not entryIds:
            return

        self.suppressInputFileSelectionSync = True
        try:
            selection = self.inputFileList.selectionModel()
            if not selection:
                return
            selection.clearSelection()
            firstIndex = None
            for entryId in entryIds:
                row = self.inputFileModel.RowForEntryId(entryId)
                if row is None:
                    continue
                index = self.inputFileModel.index(row, 0)
                selection.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
                if firstIndex is None:
                    firstIndex = index
            if firstIndex is not None:
                selection.setCurrentIndex(firstIndex, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
        finally:
            self.suppressInputFileSelectionSync = False

    def RestoreInputFileSelectionRows(self, rows, currentRow = None):
        if not hasattr(self, "inputFileModel"):
            return

        rowCount = self.inputFileModel.rowCount()
        validRows = sorted({row for row in rows if 0 <= row < rowCount})
        currentRow = currentRow if currentRow is not None else (validRows[0] if validRows else None)
        if currentRow is not None:
            currentRow = max(0, min(int(currentRow), max(0, rowCount - 1)))

        self.suppressInputFileSelectionSync = True
        try:
            selection = self.inputFileList.selectionModel()
            if not selection:
                return
            selection.clearSelection()
            for row in validRows:
                selection.select(
                    self.inputFileModel.index(row, 0),
                    QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                )
            if currentRow is not None and rowCount > 0:
                selection.setCurrentIndex(
                    self.inputFileModel.index(currentRow, 0),
                    QtCore.QItemSelectionModel.SelectionFlag.NoUpdate,
                )
        finally:
            self.suppressInputFileSelectionSync = False

    def SetSelectedInputFilesEnabled(self, enabled):
        entryIds = [
            entryId
            for _filename, entryId in self.SelectedInputFileListEntries()
            if entryId is not None
        ]
        changed = self.SetInputFilesEnabled(entryIds, enabled)
        if changed:
            self.RefreshInputFileState(preserveScrubberView = True)
            self.MarkProjectDirty()

    def SetSelectedInputFilesEnabledShortcut(self, enabled):
        if self.runActive or not self.SelectedInputFileListEntries():
            return
        self.SetSelectedInputFilesEnabled(enabled)

    def RemoveSelectedInputFilesShortcut(self):
        if self.runActive or not self.SelectedInputFileListEntries():
            return
        self.RemoveSelectedInputFilesFromList()

    def AdjustTrimForRemovedInputFiles(self, removedSourceIndices, oldEntries, oldDisabledIds, oldRangeStart, oldRangeStop, targetEnabledCount):
        if not hasattr(self, "rangeField"):
            return

        newFrameCount = len(self.inputPreviewFilenames)
        oldFrameCount = len(oldEntries)
        if oldFrameCount <= 0 or newFrameCount <= 0:
            self.rangeField.SetValues(0, newFrameCount)
            return

        if oldRangeStart <= 0 and oldRangeStop >= oldFrameCount:
            self.rangeField.SetValues(0, newFrameCount)
            return

        removedBeforeStart = sum(1 for index in removedSourceIndices if index < oldRangeStart)
        removedEnabledInsideTrim = any(
            oldRangeStart <= index < oldRangeStop
            and oldEntries[index]["id"] not in oldDisabledIds
            for index in removedSourceIndices
            if 0 <= index < oldFrameCount
        )

        newStart = max(0, oldRangeStart - removedBeforeStart)
        newStop = max(newStart + 1, oldRangeStop - removedBeforeStart)
        newStop = min(newStop, newFrameCount)
        newStart = min(newStart, max(0, newStop - 1))

        if removedEnabledInsideTrim:
            while (
                newStop < newFrameCount
                and self.EnabledFrameCountInSourceRange(newStart, newStop) < targetEnabledCount
            ):
                newStop += 1

        if (newStart, newStop) != self.InputTrimRange():
            self.rangeField.SetValues(newStart, newStop)

    def RemoveInputFileFromList(self, entryId):
        if entryId is None:
            return False

        sourceIndex = self.SourceIndexForInputEntry(entryId)
        if sourceIndex is None:
            return False
        rangeStart, rangeStop = self.InputTrimRange()
        oldEntries = list(self.inputFileEntries)
        oldDisabledIds = set(self.disabledInputFilenames)
        targetEnabledCount = self.EnabledFrameCountInSourceRange(rangeStart, rangeStop)

        self.inputFileEntries.pop(sourceIndex)
        self.disabledInputFilenames.discard(entryId)
        self.removedInputFilenames.discard(entryId)
        self.missingInputFilenames.discard(entryId)
        self.rescaleWarningInputFilenames.discard(entryId)
        self.transferWarningInputFilenames.discard(entryId)
        self.SyncInputPreviewFilenames()
        if hasattr(self, "rangeField"):
            self.rangeField.SetMaximum(len(self.inputPreviewFilenames))
            self.AdjustTrimForRemovedInputFiles({sourceIndex}, oldEntries, oldDisabledIds, rangeStart, rangeStop, targetEnabledCount)
        self.MarkProjectDirty()
        return True

    def RemoveSelectedInputFilesFromList(self):
        selectedIds = {
            entryId
            for _filename, entryId in self.SelectedInputFileListEntries()
            if entryId is not None
        }
        self.RemoveInputFilesFromListByIds(selectedIds)

    def RemoveInputFilesFromListByIds(self, selectedIds):
        selection = self.inputFileList.selectionModel()
        selectedRows = sorted(index.row() for index in selection.selectedRows()) if selection else []
        if selectedRows:
            self.pendingInputFileListRow = min(selectedRows)
            self.pendingInputFileListScroll = self.inputFileList.verticalScrollBar().value()

        selectedIds = set(selectedIds)
        if not selectedIds:
            self.ClearPendingInputRemoveHighlight()
            return

        rangeStart, rangeStop = self.InputTrimRange()
        frameCountBefore = len(self.inputFileEntries)
        oldEntries = list(self.inputFileEntries)
        oldDisabledIds = set(self.disabledInputFilenames)
        targetEnabledCount = self.EnabledFrameCountInSourceRange(rangeStart, rangeStop)
        selectedSourceIndices = {
            index
            for index, entry in enumerate(self.inputFileEntries)
            if entry["id"] in selectedIds
        }

        self.inputFileEntries = [
            entry for entry in self.inputFileEntries
            if entry["id"] not in selectedIds
        ]
        if len(self.inputFileEntries) == frameCountBefore:
            self.ClearPendingInputRemoveHighlight()
            return

        self.disabledInputFilenames.difference_update(selectedIds)
        self.removedInputFilenames.difference_update(selectedIds)
        self.missingInputFilenames.difference_update(selectedIds)
        self.rescaleWarningInputFilenames.difference_update(selectedIds)
        self.transferWarningInputFilenames.difference_update(selectedIds)
        self.SyncInputPreviewFilenames()
        if hasattr(self, "rangeField"):
            self.rangeField.SetMaximum(len(self.inputPreviewFilenames))
            self.AdjustTrimForRemovedInputFiles(
                selectedSourceIndices,
                oldEntries,
                oldDisabledIds,
                rangeStart,
                rangeStop,
                targetEnabledCount,
            )

        self.RefreshInputFileState()
        self.ClearPendingInputRemoveHighlight()
        self.MarkProjectDirty()

    def RemoveAllInputFilesFromList(self):
        if not hasattr(self, "inputFileModel") or self.inputFileModel.rowCount() <= 0:
            return

        allEntryIds = {
            self.inputFileModel.index(row, 0).data(ENTRY_ID_ROLE)
            for row in range(self.inputFileModel.rowCount())
            if self.inputFileModel.index(row, 0).data(ENTRY_ID_ROLE) is not None
        }
        self.MarkInputFilesPendingRemove(allEntryIds, startEventFilter = False)

        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle("Remove Images")
        message.setWindowIcon(StatusAssetIcon("warning"))
        message.setIconPixmap(self.TintedAssetPixmap("warning_24dp_E3E3E3.svg", "WARNING", 48))
        message.setText("Remove all images from the project?")
        removeButton = message.addButton("Remove all", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        message.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() is not removeButton:
            self.ClearPendingInputRemoveHighlight()
            return

        self.BeginUndoTransaction()
        try:
            self.RemoveInputFilesFromListByIds(allEntryIds)
        finally:
            self.EndUndoTransaction()

    def OpenInputFileListContextMenu(self, position):
        clickedIndex = self.inputFileList.indexAt(position)
        self.fileListContextEntryId = None
        if clickedIndex.isValid():
            self.fileListContextEntryId = clickedIndex.data(ENTRY_ID_ROLE)
            selection = self.inputFileList.selectionModel()
            if selection and selection.isSelected(clickedIndex):
                self.inputFileList.selectionModel().setCurrentIndex(
                    clickedIndex,
                    QtCore.QItemSelectionModel.SelectionFlag.NoUpdate,
                )
            else:
                selection.clearSelection()
                selection.select(clickedIndex, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
                selection.setCurrentIndex(clickedIndex, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)

        filenames = self.SelectedInputFileListFilenames()
        if not filenames:
            return

        menu = QtWidgets.QMenu(self.inputFileList)
        menu.setObjectName("fileListContextMenu")
        menu.aboutToHide.connect(self.ClearPendingInputRemoveHighlight)
        selectedEntries = self.SelectedInputFileListEntries()
        singleSelection = len(selectedEntries) == 1
        imageNoun = "image" if singleSelection else "images"
        if singleSelection:
            if not self.InputSelectionSyncChecked():
                self.AddFileListMenuButton(menu, "crop_3_2_24dp_E3E3E3.svg", "View", self.ViewSelectedInputFile, shortcutText = "V")
                menu.addSeparator()
            self.AddFileListMenuButton(menu, SplitAssetIcon("data_array_24dp_E3E3E3.svg", "left"), "Mark In", lambda: self.MarkRangeFromFileList("in"))
            self.AddFileListMenuButton(menu, SplitAssetIcon("data_array_24dp_E3E3E3.svg", "right"), "Mark Out", lambda: self.MarkRangeFromFileList("out"))
            if self.TrimRangeIsActive():
                self.AddFileListMenuButton(menu, "refresh_24dp_E3E3E3.svg", "Clear Range", self.ResetTrimRange, shortcutText = "Alt+X")
            menu.addSeparator()
        self.AddFileListMenuButton(menu, "visibility_off_24dp_E3E3E3.svg", f"Disable {imageNoun}", lambda: self.SetSelectedInputFilesEnabled(False), shortcutText = "H")
        self.AddFileListMenuButton(menu, "visibility_24dp_E3E3E3.svg", f"Enable {imageNoun}", lambda: self.SetSelectedInputFilesEnabled(True), shortcutText = "U")
        menu.addSeparator()
        self.AddFileListMenuButton(
            menu,
            "remove_24dp_E3E3E3.svg",
            f"Remove {imageNoun}",
            self.RemoveSelectedInputFilesFromList,
            dangerOnPress = True,
            shortcutText = "Delete",
        )
        if self.blendInLinear.isChecked():
            menu.addSeparator()
            self.AddViewportSubmenuButton(
                menu,
                "gamma_24dp_E3E3E3.svg",
                "Transfer Function",
                lambda childMenu: self.PopulateFileListGammaMenu(childMenu, selectedEntries, menu),
            )
        if singleSelection:
            menu.addSeparator()
            self.AddFileListMenuButton(menu, "folder_open_24dp_E3E3E3.svg", "Open containing folder", self.OpenSelectedInputContainingFolder)
            self.AddFileListMenuButton(menu, "info_24dp_E3E3E3.svg", "Show image info", self.ShowSelectedInputFileInfo)
        menu.exec(self.inputFileList.mapToGlobal(position))
        self.ClearPendingInputRemoveHighlight()
        self.fileListContextEntryId = None

    def AddFileListMenuButton(self, menu, icon, text, callback, dangerOnPress = False, shortcutText = "", enabled = True):
        action = QtWidgets.QWidgetAction(menu)
        button = QtWidgets.QPushButton()
        button.setObjectName("viewportMenuItem")
        button.setFlat(True)
        button.setEnabled(enabled)
        button.setProperty("softDisabled", not enabled)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor if enabled else QtCore.Qt.CursorShape.ArrowCursor)
        button.setMinimumWidth(250)
        row = QtWidgets.QHBoxLayout(button)
        row.setContentsMargins(12, 0, 14, 0)
        row.setSpacing(14)

        menuIcon = icon if isinstance(icon, QtGui.QIcon) else AssetIcon(icon)
        iconLabel = QtWidgets.QLabel()
        iconLabel.setObjectName("menuIconLabel")
        iconLabel.setFixedSize(18, 18)
        iconPixmap = menuIcon.pixmap(18, 18)
        if not enabled:
            tinted = QtGui.QPixmap(iconPixmap.size())
            tinted.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(tinted)
            painter.drawPixmap(0, 0, iconPixmap)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(tinted.rect(), ThemeQColor("TEXT_DISABLED"))
            painter.end()
            iconPixmap = tinted
        iconLabel.setPixmap(iconPixmap)
        iconLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        textLabel = QtWidgets.QLabel(text)
        textLabel.setObjectName("menuTextLabel")
        textLabel.setProperty("softDisabled", not enabled)
        textLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        shortcutLabel = QtWidgets.QLabel(shortcutText)
        shortcutLabel.setObjectName("menuShortcutLabel")
        shortcutLabel.setProperty("softDisabled", not enabled)
        shortcutLabel.setMinimumWidth(24)
        shortcutLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        shortcutLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        row.addWidget(iconLabel, 0)
        row.addWidget(textLabel, 0)
        row.addStretch(1)
        row.addWidget(shortcutLabel, 0)
        if dangerOnPress and enabled:
            button.pressed.connect(self.MarkSelectedInputFilesPendingRemove)
            button.released.connect(lambda button = button: self.ClearPendingInputRemoveIfButtonCancelled(button))

        def Trigger():
            callback()
            menu.hide()

        if enabled:
            button.clicked.connect(Trigger)
        action.setDefaultWidget(button)
        menu.addAction(action)
        return button

    def EntryDetectedTransferFunction(self, entry):
        if not entry:
            return "sRGB / Display P3", True

        try:
            metadata = self.CachedInputMetadata(entry["filename"])
            transfer = metadata.get("transfer", "Unknown")
        except (OSError, FileNotFoundError):
            transfer = "Unknown"

        if IsUnknownTransferFunction(transfer):
            return "sRGB / Display P3", True
        return str(transfer), False

    def EntryGammaState(self, entry):
        override = self.InputEntryTransferOverride(entry)
        if override:
            return override, True, False

        detectedTransfer, assumed = self.EntryDetectedTransferFunction(entry)
        return detectedTransfer, False, assumed

    def SelectedGammaState(self, entries):
        states = []
        for _filename, entryId in entries:
            entry = self.InputEntryById(entryId)
            if entry:
                states.append(self.EntryGammaState(entry))
        if not states:
            return None
        firstState = states[0]
        return firstState if all(state == firstState for state in states) else None

    def SelectedGammaAutoState(self, entries):
        states = []
        for _filename, entryId in entries:
            entry = self.InputEntryById(entryId)
            if entry:
                states.append(self.EntryDetectedTransferFunction(entry))
        if not states:
            return None
        firstState = states[0]
        return firstState if all(state == firstState for state in states) else None

    def SelectedGammaAllAuto(self, entries):
        states = []
        for _filename, entryId in entries:
            entry = self.InputEntryById(entryId)
            if entry:
                states.append(not bool(entry.get("transferOverrideEnabled", False)))
        return bool(states) and all(states)

    def PopulateFileListGammaMenu(self, menu, selectedEntries, rootMenu):
        menu.setMinimumWidth(310)
        selectedEntries = list(selectedEntries or [])
        largeSelection = len(selectedEntries) > 100
        if largeSelection:
            overrideStates = []
            for _filename, entryId in selectedEntries:
                entry = self.InputEntryById(entryId)
                if entry and entry.get("transferOverrideEnabled", False):
                    overrideStates.append((entry.get("transferFunction", "sRGB / Display P3"), True, False))
                else:
                    overrideStates.append(None)
            firstOverrideState = overrideStates[0] if overrideStates else None
            selectedState = (
                firstOverrideState
                if firstOverrideState is not None and all(state == firstOverrideState for state in overrideStates) else
                None
            )
            detectedAutoState = None
        else:
            selectedState = self.SelectedGammaState(selectedEntries)
            detectedAutoState = self.SelectedGammaAutoState(selectedEntries)
        selectedTransfer = selectedState[0] if selectedState else None
        selectedIsOverride = selectedState[1] if selectedState else None
        allAuto = self.SelectedGammaAllAuto(selectedEntries)

        self.AddViewportMenuButton(
            menu,
            "check_24dp_E3E3E3.svg" if allAuto else "",
            "Auto",
            self.SetSelectedInputFilesTransferFunctionAuto,
            closeMenu = rootMenu,
        )
        menu.addSeparator()

        for transferName in TransferFunctionNames():
            suffix = ""
            if detectedAutoState and transferName == detectedAutoState[0]:
                suffix = " (assumed)" if detectedAutoState[1] else " (auto)"

            checked = (
                selectedTransfer == transferName
                and (
                    bool(selectedIsOverride)
                    or (allAuto and detectedAutoState and not detectedAutoState[1])
                )
            )
            iconName = "check_24dp_E3E3E3.svg" if checked else ""
            self.AddViewportMenuButton(
                menu,
                iconName,
                f"{transferName}{suffix}",
                lambda transferName = transferName: self.SetSelectedInputFilesTransferFunction(transferName),
                closeMenu = rootMenu,
            )

    def SetSelectedInputFilesTransferFunctionAuto(self):
        self.SetSelectedInputFilesTransferFunction(None)

    def SetSelectedInputFilesTransferFunction(self, transferName):
        entries = self.SelectedInputFileListEntries()
        if not entries:
            return

        transferName = str(transferName) if transferName else None
        startedUndoTransaction = False
        if not self.suppressProjectDirty and self.pendingUndoTransactionSnapshot is None:
            self.BeginUndoTransaction()
            startedUndoTransaction = True

        changed = False
        selectedIds = set()
        singleEntryEdit = len(entries) == 1
        entryById = {entry["id"]: entry for entry in self.inputFileEntries}
        try:
            for _filename, entryId in entries:
                entry = entryById.get(entryId)
                if not entry:
                    continue

                selectedIds.add(entryId)
                oldEnabled = bool(entry.get("transferOverrideEnabled", False))
                oldTransfer = entry.get("transferFunction", "sRGB / Display P3")

                if transferName is None:
                    detectedTransfer, _detectedAssumed = self.EntryDetectedTransferFunction(entry)
                    entry["transferOverrideEnabled"] = False
                    entry["transferFunction"] = detectedTransfer
                else:
                    useAuto = False
                    if singleEntryEdit:
                        detectedTransfer, detectedAssumed = self.EntryDetectedTransferFunction(entry)
                        useAuto = transferName == detectedTransfer and not detectedAssumed
                    entry["transferOverrideEnabled"] = not useAuto
                    entry["transferFunction"] = detectedTransfer if useAuto else transferName

                if oldEnabled != entry["transferOverrideEnabled"] or oldTransfer != entry["transferFunction"]:
                    changed = True
        finally:
            if startedUndoTransaction:
                self.EndUndoTransaction()

        if changed:
            if transferName is None:
                for entryId in selectedIds:
                    self.RefreshInputEntryTransferWarning(entryId, refreshList = False)
            else:
                self.transferWarningInputFilenames.difference_update(selectedIds)
            self.RefreshInputPreviewMetadata()
            self.inputFileModel.SetTransferWarnings(self.transferWarningInputFilenames, selectedIds)
            if startedUndoTransaction:
                self.SetProjectDirty(True)
            else:
                self.MarkProjectDirty(section = "Images")

    def MarkSelectedInputFilesPendingRemove(self):
        if not hasattr(self, "inputFileModel"):
            return
        selectedIds = {
            entryId
            for _filename, entryId in self.SelectedInputFileListEntries()
            if entryId is not None
        }
        self.MarkInputFilesPendingRemove(selectedIds)

    def MarkInputFilesPendingRemove(self, entryIds, startEventFilter = True):
        if not hasattr(self, "inputFileModel"):
            return
        selectedIds = {entryId for entryId in (entryIds or set()) if entryId is not None}
        if selectedIds and startEventFilter:
            self.StartPendingRemoveEventFilter()
        self.inputFileModel.SetPendingRemoveEntryIds(selectedIds)

    def ClearPendingInputRemoveHighlight(self):
        if hasattr(self, "inputFileModel"):
            self.inputFileModel.SetPendingRemoveEntryIds(set())
        self.StopPendingRemoveEventFilter()

    def StartPendingRemoveEventFilter(self):
        if self.removePendingEventFilterActive:
            return
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self.removePendingEventFilterActive = True

    def StopPendingRemoveEventFilter(self):
        if not self.removePendingEventFilterActive:
            return
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.removePendingEventFilterActive = False

    def ClearPendingInputRemoveIfCancelled(self):
        QtCore.QTimer.singleShot(0, self._ClearPendingInputRemoveIfCancelled)

    def _ClearPendingInputRemoveIfCancelled(self):
        if not hasattr(self, "removeInputFileButton") or not self.removeInputFileButton.underMouse():
            self.ClearPendingInputRemoveHighlight()

    def ClearPendingInputRemoveIfButtonCancelled(self, button):
        QtCore.QTimer.singleShot(0, lambda button = button: self._ClearPendingInputRemoveIfButtonCancelled(button))

    def _ClearPendingInputRemoveIfButtonCancelled(self, button):
        if button is None or not button.underMouse():
            self.ClearPendingInputRemoveHighlight()

    def InputEntryById(self, entryId):
        for entry in self.inputFileEntries:
            if entry["id"] == entryId:
                return entry
        return None

    def ShowSelectedInputFileInfo(self):
        entries = self.SelectedInputFileListEntries()
        if len(entries) != 1:
            return

        _selectedFilename, entryId = entries[0]
        entry = self.InputEntryById(entryId)
        if not entry:
            return

        self.ShowInputFileInfoDialog(entry)

    def OpenSelectedInputContainingFolder(self):
        entries = self.SelectedInputFileListEntries()
        if len(entries) != 1:
            return

        _selectedFilename, entryId = entries[0]
        entry = self.InputEntryById(entryId)
        if entry:
            self.OpenContainingFolder(entry["filename"])

    def ViewSelectedInputFile(self):
        entries = self.SelectedInputFileListEntries()
        if len(entries) != 1:
            return

        _selectedFilename, entryId = entries[0]
        entry = self.InputEntryById(entryId)
        if not entry:
            return

        self.manualInputViewportEntryId = entryId
        if hasattr(self, "viewportTabs"):
            self.viewportTabs.setCurrentIndex(0)
        self.LoadInputPreview(entry["filename"], entryId, preserveScrubberView = True)

    def ViewSelectedInputFileFromShortcut(self):
        if self.runActive or self.InputSelectionSyncChecked():
            return

        self.ViewSelectedInputFile()

    def ClearManualInputViewport(self):
        self.manualInputViewportEntryId = None

    def CurrentInputViewportEntry(self):
        entryId = self.currentInputPreviewEntryId
        if entryId is None and self.currentInputPreviewFile:
            entryId = self.EntryIdForInputFilename(self.currentInputPreviewFile)
        return self.InputEntryById(entryId) if entryId is not None else None

    def SetViewportInputFileEnabled(self, entryId, enabled):
        if self.SetInputFileEnabled(entryId, enabled):
            self.pendingInputSelectionEntryIds = {entryId}
            self.RefreshInputFileState(preserveScrubberView = True)
            self.MarkProjectDirty()

    def MarkViewportInputFile(self, markType, entryId):
        sourceFrame = self.SourceIndexForInputEntry(entryId)
        if sourceFrame is None:
            return
        self.MarkRangeFromSourceFrame(markType, sourceFrame)

    def RemoveViewportInputFile(self, entryId):
        selection = self.inputFileList.selectionModel() if hasattr(self, "inputFileList") else None
        self.pendingInputSelectionEntryIds = {
            index.data(ENTRY_ID_ROLE)
            for index in selection.selectedRows()
            if index.data(ENTRY_ID_ROLE) is not None
        } if selection else set()
        if self.RemoveInputFileFromList(entryId):
            self.RefreshInputFileState()

    def OpenContainingFolder(self, filename):
        folder = os.path.dirname(os.path.abspath(filename))
        if not os.path.isdir(folder):
            self.ShowWarningMessage("Open Folder", "Containing folder was not found.")
            return False

        return QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))

    def CreateFileInfoValueLabel(self, value, objectName = ""):
        valueLabel = QtWidgets.QLabel(value)
        valueLabel.setFixedWidth(FILE_INFO_VALUE_WIDTH)
        valueLabel.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        if objectName:
            valueLabel.setObjectName(objectName)
        if objectName == "richText":
            valueLabel.setTextFormat(QtCore.Qt.TextFormat.RichText)
        valueLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        valueLabel.setWordWrap(True)
        return valueLabel

    def ShowOutputFileInfoDialog(self, filename):
        if not filename:
            return

        exists = os.path.isfile(filename)
        if not exists:
            self.ShowWarningMessage("File Info", "File was not found.")
            return

        metadata = ReadImageMetadata(filename)
        dimensions = ReadImageDimensions(filename)
        try:
            fileSize = self.FormatByteSize(os.path.getsize(filename))
        except OSError:
            fileSize = "Unknown"

        warnUnknownMetadata = self.blendInLinear.isChecked()
        transferText = metadata.get("transfer", "Unknown")
        transferObjectName = ""
        if warnUnknownMetadata and IsUnknownTransferFunction(transferText):
            transferText = f'<span style="color: {ThemeColor("WARNING")}">{html.escape(str(transferText))}</span>'
            transferObjectName = "richText"
        rows = [
            ("Path", os.path.normpath(filename), ""),
            ("File type", os.path.splitext(filename)[1].lstrip(".").upper() or "Unknown", ""),
            ("File size", fileSize, ""),
            ("Dimensions", metadata.get("dimensions") or (f"{dimensions[0]}x{dimensions[1]}" if dimensions else "Unknown"), ""),
            ("Color space", metadata.get("colorSpace", "Unknown"), ""),
            ("Transfer function", transferText, transferObjectName),
        ]

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("File Info")
        dialog.setWindowIcon(StatusAssetIcon("info"))
        dialog.setFixedWidth(FILE_INFO_DIALOG_WIDTH)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QtWidgets.QWidget()
        header.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        headerLayout = QtWidgets.QHBoxLayout(header)
        headerLayout.setContentsMargins(0, 0, 0, 0)
        headerLayout.setSpacing(14)

        thumbnailLabel = QtWidgets.QLabel()
        thumbnailLabel.setFixedHeight(96)
        thumbnailLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        thumbnailPixmap = self.FileInfoThumbnail(filename, True, 96)
        thumbnailLabel.setFixedWidth(max(96, thumbnailPixmap.width()))
        thumbnailLabel.setPixmap(thumbnailPixmap)
        headerLayout.addWidget(thumbnailLabel, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        titleLabel = QtWidgets.QLabel(os.path.basename(filename))
        titleLabel.setObjectName("dialogHeading")
        titleLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        headerLayout.addWidget(titleLabel, 1, QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(header)

        form = QtWidgets.QFormLayout()
        ConfigureFormLayout(form)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignTop)
        for label, value, objectName in rows:
            form.addRow(label, self.CreateFileInfoValueLabel(value, objectName))

        layout.addLayout(form)
        layout.addSpacing(8)
        buttonRow = QtWidgets.QHBoxLayout()
        openFolderButton = QtWidgets.QPushButton(IconButtonText("Open containing folder"))
        openFolderButton.setIcon(AssetIcon("folder_open_24dp_E3E3E3.svg"))
        openFolderButton.clicked.connect(lambda: self.OpenContainingFolder(filename))
        buttonRow.addWidget(openFolderButton)
        buttonRow.addStretch(1)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        buttonRow.addWidget(buttons)
        layout.addLayout(buttonRow)
        dialog.setFixedHeight(max(430, dialog.sizeHint().height()))
        dialog.exec()

    def ShowInputFileInfoDialog(self, entry):
        filename = entry["filename"]
        entryId = entry["id"]
        exists = os.path.isfile(filename)
        self.SetInputEntryMissing(entryId, not exists)

        metadata = ReadImageMetadata(filename) if exists else {
            "dimensions": "",
            "colorSpace": "Unknown",
            "transfer": "Unknown",
        }
        dimensions = self.CachedImageDimensions(filename) if exists else None
        targetResolution = self.EffectiveOutputResolution()
        willRescale = bool(dimensions and targetResolution and dimensions != targetResolution)
        self.SetInputEntryRescaleWarning(entryId, willRescale)
        warnUnknownTransfer = (
            exists
            and self.blendInLinear.isChecked()
            and not self.InputEntryTransferOverride(entry)
            and IsUnknownTransferFunction(metadata.get("transfer"))
        )
        self.SetInputEntryTransferWarning(entryId, warnUnknownTransfer)

        activeFrameNumber = None
        activePosition = None
        activeFrameNumbers, manuallyEnabled = self.InputReadPlan()
        for index, (_filename, _sourceIndex, displayEntryId) in enumerate(self.DisplayInputFileEntries()):
            if displayEntryId == entryId:
                activePosition = index
                activeFrameNumber = activeFrameNumbers.get(index)
                break

        fileSize = ""
        if exists:
            try:
                fileSize = self.FormatByteSize(os.path.getsize(filename))
            except OSError:
                fileSize = "Unknown"

        errors = []
        if not exists:
            errors.append("File not found")

        pathText = os.path.normpath(filename)
        dimensionsText = metadata.get("dimensions") or (f"{dimensions[0]}x{dimensions[1]}" if dimensions else "Unknown")
        if willRescale:
            dimensionsText = (
                f'{html.escape(dimensionsText)} '
                f'<span style="color: {ThemeColor("WARNING")}">(Image will be scaled to export dimensions)</span>'
            )
        entryTransferOverride = self.InputEntryTransferOverride(entry)
        transferText = entryTransferOverride or metadata.get("transfer", "Unknown")
        transferObjectName = ""
        if entryTransferOverride:
            transferText = (
                f'{html.escape(str(entryTransferOverride))} '
                f'<span style="color: {ThemeColor("WARNING")}">(user override)</span>'
            )
            transferObjectName = "richText"
        elif warnUnknownTransfer:
            transferText = f'<span style="color: {ThemeColor("WARNING")}">{html.escape(str(transferText))}</span>'
            transferObjectName = "richText"
        frameDigits = max(4, len(str(max(activeFrameNumbers.values()))) if activeFrameNumbers else 4)
        renderFrameText = ("-" * frameDigits) if activeFrameNumber is None else f"{activeFrameNumber:0{frameDigits}d}"
        rows = [
            ("Path", pathText, "errorLabel" if not exists else "", "errorLabel" if not exists else ""),
            ("Render frame", renderFrameText),
            ("File type", os.path.splitext(filename)[1].lstrip(".").upper() or "Unknown"),
            ("File size", fileSize or "Unknown"),
            ("Dimensions", dimensionsText, "richText" if willRescale else ""),
            ("Color space", metadata.get("colorSpace", "Unknown")),
            ("Transfer function", transferText, transferObjectName),
        ]

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("File Info")
        dialog.setWindowIcon(StatusAssetIcon("info"))
        dialog.setFixedWidth(FILE_INFO_DIALOG_WIDTH)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QtWidgets.QWidget()
        header.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        headerLayout = QtWidgets.QHBoxLayout(header)
        headerLayout.setContentsMargins(0, 0, 0, 0)
        headerLayout.setSpacing(14)

        thumbnailLabel = QtWidgets.QLabel()
        thumbnailLabel.setFixedHeight(96)
        thumbnailLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        thumbnailPixmap = self.FileInfoThumbnail(filename, exists, 96)
        thumbnailLabel.setFixedWidth(max(96, thumbnailPixmap.width()))
        thumbnailLabel.setPixmap(thumbnailPixmap)
        headerLayout.addWidget(thumbnailLabel, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        headerText = QtWidgets.QWidget()
        headerTextLayout = QtWidgets.QVBoxLayout(headerText)
        headerTextLayout.setContentsMargins(0, 0, 0, 0)
        headerTextLayout.setSpacing(6)

        titleLabel = QtWidgets.QLabel(os.path.basename(filename))
        titleLabel.setObjectName("dialogHeading")
        titleLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        headerTextLayout.addWidget(titleLabel)

        for error in errors:
            errorLabel = QtWidgets.QLabel(error)
            errorLabel.setObjectName("errorLabel")
            errorLabel.setWordWrap(True)
            errorLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            headerTextLayout.addWidget(errorLabel)

        renderEnabled = entryId not in self.disabledInputFilenames
        renderSkipped = renderEnabled and activeFrameNumber is None and activePosition in manuallyEnabled
        renderStateRow = QtWidgets.QWidget()
        renderStateLayout = QtWidgets.QHBoxLayout(renderStateRow)
        renderStateLayout.setContentsMargins(0, 0, 0, 0)
        renderStateLayout.setSpacing(8)
        renderStateIcon = QtWidgets.QLabel()
        renderStateIcon.setFixedSize(18, 18)
        iconName = "visibility_24dp_E3E3E3.svg" if renderEnabled else "visibility_off_24dp_E3E3E3.svg"
        iconColor = "TEXT_DISABLED" if (not renderEnabled or renderSkipped) else "TEXT"
        renderStateIcon.setPixmap(self.TintedAssetPixmap(iconName, iconColor, 18))
        renderStateText = "Enabled"
        if not renderEnabled:
            renderStateText = "Disabled"
        elif renderSkipped:
            renderStateText = "Enabled (skipped)"
        renderStateLabel = QtWidgets.QLabel(renderStateText)
        if not renderEnabled or renderSkipped:
            renderStateLabel.setObjectName("mutedLabel")
        renderStateLayout.addWidget(renderStateIcon, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        renderStateLayout.addWidget(renderStateLabel, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        renderStateLayout.addStretch(1)
        headerTextLayout.addWidget(renderStateRow)
        headerLayout.addWidget(headerText, 1, QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(header)

        form = QtWidgets.QFormLayout()
        ConfigureFormLayout(form)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignTop)
        for row in rows:
            label, value = row[:2]
            objectName = row[2] if len(row) > 2 else ""
            labelObjectName = row[3] if len(row) > 3 else ""
            labelWidget = QtWidgets.QLabel(label)
            if labelObjectName:
                labelWidget.setObjectName(labelObjectName)
            form.addRow(labelWidget, self.CreateFileInfoValueLabel(value, objectName))

        layout.addLayout(form)
        layout.addSpacing(8)
        buttonRow = QtWidgets.QHBoxLayout()
        openFolderButton = QtWidgets.QPushButton(IconButtonText("Open containing folder"))
        openFolderButton.setIcon(AssetIcon("folder_open_24dp_E3E3E3.svg"))
        openFolderButton.clicked.connect(lambda: self.OpenContainingFolder(filename))
        buttonRow.addWidget(openFolderButton)
        buttonRow.addStretch(1)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        buttonRow.addWidget(buttons)
        layout.addLayout(buttonRow)
        dialog.setFixedHeight(max(430, dialog.sizeHint().height()))
        dialog.exec()

        self.RefreshInputFileList()

    def FileInfoThumbnail(self, filename, exists, targetHeight):
        targetHeight = int(targetHeight)
        if exists:
            reader = QtGui.QImageReader(filename)
            reader.setAutoTransform(True)
            sourceSize = reader.size()
            if sourceSize.isValid():
                sourceSize.scale(QtCore.QSize(10000, targetHeight), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(sourceSize)
            image = reader.read()
            if not image.isNull():
                return QtGui.QPixmap.fromImage(image).scaled(
                    QtCore.QSize(10000, targetHeight),
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )

        pixmap = AssetIcon("error_24dp_E3E3E3.svg").pixmap(targetHeight, targetHeight)
        tinted = QtGui.QPixmap(pixmap.size())
        tinted.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(tinted)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), ThemeQColor("ERROR"))
        painter.end()
        return tinted

    def FormatByteSize(self, byteCount):
        value = float(byteCount)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024.0 or unit == "TB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
            value /= 1024.0

    def EnabledInputFilenames(self):
        return [
            filename for filename, _sourceIndex, entryId in self.DisplayInputFileEntries()
            if entryId not in self.disabledInputFilenames
        ]

    def EnabledInputEntries(self):
        entryById = {entry["id"]: entry for entry in self.inputFileEntries}
        return [
            entryById[entryId]
            for _filename, _sourceIndex, entryId in self.DisplayInputFileEntries()
            if entryId not in self.disabledInputFilenames and entryId in entryById
        ]

    def InputEntryTransferOverride(self, entry):
        if not entry or not entry.get("transferOverrideEnabled", False):
            return None
        return entry.get("transferFunction") or "sRGB / Display P3"

    def EnabledInputFilenamesWithSourceIndices(self):
        result = []
        for filename, sourceIndex, entryId in self.DisplayInputFileEntries():
            if entryId in self.disabledInputFilenames:
                continue
            result.append((filename, sourceIndex))
        return result

    def RefreshInputFileList(self):
        if not hasattr(self, "inputFileModel"):
            return

        self.suppressInputFileSelectionSync = True
        selection = self.inputFileList.selectionModel()
        if self.pendingInputSelectionEntryIds is not None:
            selectedEntryIds = set(self.pendingInputSelectionEntryIds)
            self.pendingInputSelectionEntryIds = None
        else:
            selectedEntryIds = {
                index.data(ENTRY_ID_ROLE)
                for index in selection.selectedRows()
                if index.data(ENTRY_ID_ROLE) is not None
            } if selection else set()
        previousCurrent = self.inputFileList.currentIndex()
        previousCurrentId = previousCurrent.data(ENTRY_ID_ROLE) if previousCurrent.isValid() else None
        scrollValue = self.inputFileList.verticalScrollBar().value()
        entries = self.DisplayInputFileEntries()
        activeFrameNumbers, manuallyEnabled = self.InputReadPlan()
        rangeStart, rangeStop = self.InputTrimRange()
        digits = max(4, len(str(max(0, len(activeFrameNumbers) - 1))))
        inactivePrefix = "-" * digits
        currentPreviewEntryId = None if self.InputSelectionSyncChecked() else self.CurrentInputScrubberEntryId()
        try:
            rows = []
            restoredCurrentRow = None
            for index, (filename, sourceIndex, entryId) in enumerate(entries):
                inTrimRange = rangeStart <= sourceIndex < rangeStop
                frameNumber = activeFrameNumbers.get(index)
                prefix = f"{frameNumber:0{digits}d}" if inTrimRange and frameNumber is not None else inactivePrefix
                isActive = frameNumber is not None
                isManuallyEnabled = index in manuallyEnabled
                isMissing = entryId in self.missingInputFilenames
                isRescaleWarning = entryId in self.rescaleWarningInputFilenames
                isTransferWarning = entryId in self.transferWarningInputFilenames
                suffix = ""
                if isMissing:
                    suffix = " (missing)"
                elif not isActive:
                    if not isManuallyEnabled:
                        suffix = " (disabled)"
                    elif inTrimRange:
                        suffix = " (skipped)"
                tooltipLines = []
                if isRescaleWarning:
                    tooltipLines.append("Image will be scaled to export dimensions")
                if isTransferWarning:
                    tooltipLines.append("Unknown transfer function: sRGB assumed")
                if isMissing:
                    tooltipLines.append("File not found")
                rows.append({
                    "displayText": f"{prefix}\t{os.path.basename(filename)}{suffix}",
                    "tooltip": os.path.normpath(filename),
                    "filename": filename,
                    "displayIndex": index,
                    "isActive": isActive,
                    "isManuallyEnabled": isManuallyEnabled,
                    "entryId": entryId,
                    "isMissing": isMissing,
                    "isRescaleWarning": isRescaleWarning,
                    "isTransferWarning": isTransferWarning,
                    "isCurrentPreview": entryId == currentPreviewEntryId,
                    "showReorder": not self.InputSelectionSyncChecked(),
                })
                if entryId == previousCurrentId:
                    restoredCurrentRow = index

            self.inputFileModel.SetRows(rows)
            selection = self.inputFileList.selectionModel()
            if selection:
                selection.clearSelection()
                for row, rowData in enumerate(rows):
                    if rowData["entryId"] in selectedEntryIds:
                        selection.select(
                            self.inputFileModel.index(row, 0),
                            QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                        )

            pendingRow = self.pendingInputFileListRow
            pendingScroll = self.pendingInputFileListScroll
            self.pendingInputFileListRow = None
            self.pendingInputFileListScroll = None
            if restoredCurrentRow is None and pendingRow is not None and self.inputFileModel.rowCount() > 0:
                restoredCurrentRow = max(0, min(pendingRow, self.inputFileModel.rowCount() - 1))
                if selection:
                    selection.select(
                        self.inputFileModel.index(restoredCurrentRow, 0),
                        QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows,
                    )

            if restoredCurrentRow is not None:
                currentIndex = self.inputFileModel.index(restoredCurrentRow, 0)
                if selection:
                    selection.setCurrentIndex(currentIndex, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
            self.inputFileList.verticalScrollBar().setValue(pendingScroll if pendingScroll is not None else scrollValue)
        finally:
            self.suppressInputFileSelectionSync = False
        self.UpdateInputFileActionButtons()

    def UpdateCurrentInputPreviewMarker(self):
        if not hasattr(self, "inputFileModel"):
            return

        entryId = None if self.InputSelectionSyncChecked() else self.CurrentInputScrubberEntryId()
        self.inputFileModel.SetCurrentPreviewEntryId(entryId)

    def CurrentInputScrubberEntryId(self):
        if not hasattr(self, "frameScrubber"):
            return None
        entryIds = self.InputScrubberEntryIds()
        if not entryIds:
            return None
        index = max(0, min(int(self.frameScrubber.value), len(entryIds) - 1))
        return entryIds[index]

    def FocusFirstActiveInputFile(self):
        if not hasattr(self, "inputFileModel"):
            return

        for row in range(self.inputFileModel.rowCount()):
            index = self.inputFileModel.index(row, 0)
            if index.data(ACTIVE_ROLE):
                selection = self.inputFileList.selectionModel()
                selection.clearSelection()
                selection.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
                selection.setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
                self.inputFileList.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
                return

    def InputSelectionSyncEnabled(self):
        return (
            self.InputSelectionSyncChecked()
            and hasattr(self, "viewportTabs")
            and self.viewportTabs.currentIndex() == 0
        )

    def InputSelectionSyncChecked(self):
        return (
            hasattr(self, "syncInputSelectionButton")
            and self.syncInputSelectionButton.isChecked()
        )

    def EnabledInputEntryIds(self):
        return [
            entryId
            for _filename, _sourceIndex, entryId in self.DisplayInputFileEntries()
            if entryId not in self.disabledInputFilenames
        ]

    def SyncInputSelectionToggled(self, checked):
        if checked:
            self.ClearManualInputViewport()
        self.UpdateInputFileSelectionMode()
        self.UpdateCurrentInputPreviewMarker()
        if checked:
            self.EnforceSingleInputFileSelection()
            self.InputFileSelectionChanged()
            self.FrameScrubberChanged(self.frameScrubber.value, preserveView = True)

    def UpdateInputFileSelectionMode(self):
        if not hasattr(self, "inputFileList"):
            return

        mode = (
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
            if self.InputSelectionSyncChecked()
            else QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.inputFileList.setSelectionMode(mode)
        self.inputFileList.SetReorderEnabled(not self.InputSelectionSyncChecked())
        if hasattr(self, "inputFileModel"):
            self.RefreshInputFileList()
        self.UpdateInputFileActionButtons()

    def EnforceSingleInputFileSelection(self):
        if not self.InputSelectionSyncChecked() or not hasattr(self, "inputFileList"):
            return

        selection = self.inputFileList.selectionModel()
        selectedRows = selection.selectedRows() if selection else []
        if len(selectedRows) <= 1:
            return

        currentIndex = self.inputFileList.currentIndex()
        keepIndex = currentIndex if currentIndex in selectedRows else selectedRows[-1]
        self.suppressInputFileSelectionSync = True
        try:
            selection.clearSelection()
            selection.select(keepIndex, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
            selection.setCurrentIndex(keepIndex, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
        finally:
            self.suppressInputFileSelectionSync = False

    def InputFileSelectionChanged(self):
        if self.suppressInputFileSelectionSync:
            self.UpdateInputFileActionButtons()
            return

        self.EnforceSingleInputFileSelection()
        self.UpdateInputFileActionButtons()

        current = self.inputFileList.currentIndex()
        entryId = current.data(ENTRY_ID_ROLE) if current.isValid() else None
        filename = current.data(FILENAME_ROLE) if current.isValid() else None
        if entryId is None:
            return

        if filename:
            self.CheckInputEntryFileExists(entryId, filename)
            self.RefreshInputEntryTransferWarning(entryId, filename)

        if not self.InputSelectionSyncEnabled():
            return

        for index, scrubberEntryId in enumerate(self.InputScrubberEntryIds()):
            if scrubberEntryId == entryId:
                self.frameScrubber.SetValue(index, emit = True)
                return

    def SyncInputFileSelectionToEntryId(self, entryId):
        if not self.InputSelectionSyncEnabled() or entryId is None:
            return

        self.suppressInputFileSelectionSync = True
        try:
            row = self.inputFileModel.RowForEntryId(entryId)
            if row < 0:
                return
            index = self.inputFileModel.index(row, 0)
            selection = self.inputFileList.selectionModel()
            selection.clearSelection()
            selection.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
            selection.setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
            self.inputFileList.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
        finally:
            self.suppressInputFileSelectionSync = False

    def InputTrimRange(self):
        frameCount = len(self.inputPreviewFilenames)
        if hasattr(self, "rangeField"):
            rangeStart, rangeStop = self.rangeField.Values()
        else:
            rangeStart, rangeStop = 0, frameCount

        rangeStart = max(0, min(rangeStart, frameCount))
        rangeStop = max(rangeStart, min(rangeStop, frameCount))
        return rangeStart, rangeStop

    def TrimRangeIsActive(self):
        frameCount = len(self.inputPreviewFilenames)
        if frameCount <= 0:
            return False

        rangeStart, rangeStop = self.InputTrimRange()
        return rangeStart > 0 or rangeStop < frameCount

    def InputReadSequence(self):
        scrubberSequence, manuallyEnabled = self.InputScrubberSequence()
        if not scrubberSequence:
            return [], manuallyEnabled

        rangeStart, rangeStop = self.InputTrimRange()
        entries = self.DisplayInputFileEntries()
        return [
            (position, enabledIndex)
            for position, enabledIndex in scrubberSequence
            if rangeStart <= entries[position][1] < rangeStop
        ], manuallyEnabled

    def InputScrubberSequence(self):
        if not self.inputPreviewFilenames:
            return [], set()

        entries = self.DisplayInputFileEntries()
        scrubberPositions = []
        manuallyEnabled = set()
        enabledDisplayIndex = 0
        for position, (filename, sourceIndex, entryId) in enumerate(entries):
            isEnabled = entryId not in self.disabledInputFilenames
            if not isEnabled:
                continue

            manuallyEnabled.add(position)
            scrubberPositions.append((position, enabledDisplayIndex))
            enabledDisplayIndex += 1

        skip = max(1, self.skipInput.value())
        return scrubberPositions[::skip], manuallyEnabled

    def InputReadPlan(self):
        sequence, manuallyEnabled = self.InputReadSequence()
        frameNumbers = {}
        for frameNumber, (position, _enabledIndex) in enumerate(sequence):
            frameNumbers[position] = frameNumber

        return frameNumbers, manuallyEnabled

    def InputReadIndices(self):
        sequence, _manuallyEnabled = self.InputReadSequence()
        return [enabledIndex for _position, enabledIndex in sequence]

    def InputScrubberFilenames(self):
        filenames = self.EnabledInputFilenames()
        return [
            filenames[enabledIndex]
            for _position, enabledIndex in self.InputScrubberSequence()[0]
            if 0 <= enabledIndex < len(filenames)
        ]

    def InputScrubberEntryIds(self):
        entryIds = self.EnabledInputEntryIds()
        return [
            entryIds[enabledIndex]
            for _position, enabledIndex in self.InputScrubberSequence()[0]
            if 0 <= enabledIndex < len(entryIds)
        ]

    def InputScrubberTransferOverrides(self):
        entries = self.EnabledInputEntries()
        return [
            self.InputEntryTransferOverride(entries[enabledIndex])
            for _position, enabledIndex in self.InputScrubberSequence()[0]
            if 0 <= enabledIndex < len(entries)
        ]

    def InputReadFilenames(self):
        filenames = self.EnabledInputFilenames()
        return [
            filenames[enabledIndex]
            for _position, enabledIndex in self.InputReadSequence()[0]
            if 0 <= enabledIndex < len(filenames)
        ]

    def InputReadEntryIds(self):
        entryIds = self.EnabledInputEntryIds()
        return [
            entryIds[enabledIndex]
            for _position, enabledIndex in self.InputReadSequence()[0]
            if 0 <= enabledIndex < len(entryIds)
        ]

    def InputReadTransferOverrides(self):
        entries = self.EnabledInputEntries()
        return [
            self.InputEntryTransferOverride(entries[enabledIndex])
            for _position, enabledIndex in self.InputReadSequence()[0]
            if 0 <= enabledIndex < len(entries)
        ]

    def InputReadScrubberIndices(self):
        scrubberSequence, _manuallyEnabled = self.InputScrubberSequence()
        if not scrubberSequence:
            return []

        entries = self.DisplayInputFileEntries()
        rangeStart, rangeStop = self.InputTrimRange()
        return [
            scrubberIndex
            for scrubberIndex, (position, _enabledIndex) in enumerate(scrubberSequence)
            if rangeStart <= entries[position][1] < rangeStop
        ]

    def InputReadIndicesFromScrubber(self, frameCount, clampToTrim = False):
        scrubberSequence, _manuallyEnabled = self.InputScrubberSequence()
        entries = self.DisplayInputFileEntries()
        rangeStart, rangeStop = self.InputTrimRange()
        startPosition = self.InputScrubberStartIndex()
        if clampToTrim and scrubberSequence:
            trimPositions = [
                scrubberIndex
                for scrubberIndex, (position, _enabledIndex) in enumerate(scrubberSequence)
                if rangeStart <= entries[position][1] < rangeStop
            ]
            if trimPositions and startPosition not in trimPositions:
                startPosition = trimPositions[0]
        indices = [
            enabledIndex
            for scrubberIndex, (position, enabledIndex) in enumerate(scrubberSequence)
            if scrubberIndex >= startPosition and rangeStart <= entries[position][1] < rangeStop
        ]
        return indices[:max(1, int(frameCount))]

    def InputReadScrubberIndicesFromScrubber(self, frameCount, clampToTrim = False):
        scrubberSequence, _manuallyEnabled = self.InputScrubberSequence()
        entries = self.DisplayInputFileEntries()
        rangeStart, rangeStop = self.InputTrimRange()
        startPosition = self.InputScrubberStartIndex()
        if clampToTrim and scrubberSequence:
            trimPositions = [
                scrubberIndex
                for scrubberIndex, (position, _enabledIndex) in enumerate(scrubberSequence)
                if rangeStart <= entries[position][1] < rangeStop
            ]
            if trimPositions and startPosition not in trimPositions:
                startPosition = trimPositions[0]
        indices = [
            scrubberIndex
            for scrubberIndex, (position, _enabledIndex) in enumerate(scrubberSequence)
            if scrubberIndex >= startPosition and rangeStart <= entries[position][1] < rangeStop
        ]
        return indices[:max(1, int(frameCount))]

    def InputReadFilenamesFromScrubber(self, frameCount, clampToTrim = False):
        filenames = self.EnabledInputFilenames()
        return [
            filenames[index]
            for index in self.InputReadIndicesFromScrubber(frameCount, clampToTrim)
            if 0 <= index < len(filenames)
        ]

    def InputReadEntryIdsFromScrubber(self, frameCount, clampToTrim = False):
        entryIds = self.EnabledInputEntryIds()
        return [
            entryIds[index]
            for index in self.InputReadIndicesFromScrubber(frameCount, clampToTrim)
            if 0 <= index < len(entryIds)
        ]

    def InputReadTransferOverridesFromScrubber(self, frameCount, clampToTrim = False):
        entries = self.EnabledInputEntries()
        return [
            self.InputEntryTransferOverride(entries[index])
            for index in self.InputReadIndicesFromScrubber(frameCount, clampToTrim)
            if 0 <= index < len(entries)
        ]

    def UpdateInputEmptyAction(self):
        if not hasattr(self, "inputViewport"):
            return

        if self.currentInputPreviewEntryId in self.missingInputFilenames:
            self.inputViewport.SetEmptyError("File not found")
            return

        enabled = not self.inputPreviewFilenames
        self.inputViewport.SetEmptyAction(
            enabled,
            AssetIcon("add_photo_alternate_24dp_E3E3E3.svg"),
            "Drop images here to start blending",
        )

    def InputViewportEmptyClicked(self):
        if self.currentInputPreviewEntryId in self.missingInputFilenames:
            entry = self.InputEntryById(self.currentInputPreviewEntryId)
            if entry:
                self.ShowInputFileInfoDialog(entry)
                return

        self.OpenInputFileBrowser()

    def UpdateOutputEmptyAction(self):
        if not hasattr(self, "outputViewport"):
            return

        enabled = not self.outputDirectory.Text()
        self.outputViewport.SetEmptyAction(
            enabled,
            AssetIcon("folder_open_24dp_E3E3E3.svg"),
            "Choose an export folder" if enabled else None,
        )

    def SetOutputEmptyFramesMessage(self):
        self.outputViewport.Clear("Rendered exports can be viewed here")

    def CurrentRangeFilenames(self):
        if not self.inputPreviewFilenames or not hasattr(self, "rangeField"):
            return []

        return self.InputScrubberFilenames()

    def CachedImageDimensions(self, filename, readIfMissing = True):
        if filename not in self.inputDimensionCache and readIfMissing:
            self.inputDimensionCache[filename] = ReadImageDimensions(filename)
        return self.inputDimensionCache.get(filename)

    def CurrentRangeDimensionSummary(self):
        filenames = self.CurrentRangeFilenames()
        if not filenames:
            return False, []

        firstSize = self.CachedImageDimensions(filenames[0])
        if not firstSize:
            return False, []

        differingSizes = []
        for filename in filenames[1:]:
            size = self.CachedImageDimensions(filename, readIfMissing = False)
            if size and size != firstSize:
                differingSizes = [firstSize, size]
                break

        if not differingSizes:
            return False, [firstSize]

        # Keep the first rendered frame's size first; reverse/reordered lists depend on this.
        uniqueSizes = [firstSize]
        for filename in filenames[1:]:
            size = self.CachedImageDimensions(filename, readIfMissing = False)
            if size and size not in uniqueSizes:
                uniqueSizes.append(size)
        return True, uniqueSizes

    def RefreshInputStatusLabel(self):
        count = len(self.inputPreviewFilenames)
        noun = "image" if count == 1 else "images"

        self.inputHasMixedDimensions, uniqueDimensions = self.CurrentRangeDimensionSummary()

        if self.inputHasMixedDimensions:
            firstWidth, firstHeight = uniqueDimensions[0]
            foundText = html.escape(f"{count} {noun} in render list")
            warningText = html.escape("Image will be scaled to export dimensions")
            self.inputCountLabel.setText(
                f'{foundText} <span style="color: #d5a24a;">({warningText})</span>'
            )
            self.inputCountLabel.setToolTip(
                "Images in the selected range will be resized to the export dimensions. "
                f"Found {len(uniqueDimensions)} sizes in range, including {firstWidth}x{firstHeight}."
            )
        else:
            self.inputCountLabel.setText(f"{count} {noun} in render list")
            self.inputCountLabel.setToolTip("")

    def UpdateRangePreview(self, *_, preserveScrubberView = False):
        if self.runActive:
            return

        if self.suppressRangePreview:
            self.RefreshInputFileList()
            self.RefreshInputStatusLabel()
            self.RefreshInputPreviewMetadata()
            self.UpdateEffectiveOverrideValues()
            self.UpdateStackSizeMaximum()
            return

        if not self.inputPreviewFilenames or not self.EnabledInputFilenames():
            self.ClearInputPreview(preserveScrubberView = preserveScrubberView)
            self.UpdateFrameScrubber(preserveView = preserveScrubberView)
            self.UpdateStackSizeMaximum()
            return

        rangeStart, rangeStop = self.rangeField.Values()
        useRangeStop = self.previewRangeStopWhileDragging
        entries = self.DisplayInputFileEntries()
        enabledInRange = [
            (entries[position][0], entries[position][2])
            for position, _enabledIndex in self.InputReadSequence()[0]
            if 0 <= position < len(entries)
        ]
        if not enabledInRange:
            self.ClearInputPreview(preserveScrubberView = preserveScrubberView)
            self.RefreshInputFileList()
            self.RefreshInputStatusLabel()
            self.UpdateEffectiveOverrideValues()
            self.UpdateStackSizeMaximum()
            self.UpdateFrameScrubber(preserveView = preserveScrubberView)
            return
        filename, entryId = enabledInRange[-1] if useRangeStop else enabledInRange[0]
        self.RefreshInputFileList()
        self.RefreshInputStatusLabel()
        self.UpdateEffectiveOverrideValues()
        self.UpdateStackSizeMaximum()
        if self.manualInputViewportEntryId is not None:
            self.RefreshInputPreviewMetadata()
            self.UpdateFrameScrubber(preserveView = True)
            return
        if (
            entryId == self.currentInputPreviewEntryId
            and filename == self.currentInputPreviewFile
            and self.previewPixmap is not None
            and not self.previewPixmap.isNull()
        ):
            self.RefreshInputPreviewMetadata()
        else:
            self.LoadInputPreview(filename, entryId, preserveScrubberView = preserveScrubberView)
        self.UpdateFrameScrubber(preserveView = preserveScrubberView)

    def RangeHandleDragStarted(self, handle):
        if handle == "upper":
            self.previewRangeStopWhileDragging = True
            self.UpdateRangePreview()

    def RangeHandleDragEnded(self, handle):
        if handle == "upper":
            self.previewRangeStopWhileDragging = False
            self.UpdateRangePreview()

    def ReverseInputList(self):
        if not self.inputFileEntries:
            return

        selection = self.inputFileList.selectionModel() if hasattr(self, "inputFileList") else None
        selectedRows = sorted(index.row() for index in selection.selectedRows()) if selection else []
        currentIndex = self.inputFileList.currentIndex() if hasattr(self, "inputFileList") else QtCore.QModelIndex()
        currentRow = currentIndex.row() if currentIndex.isValid() else (selectedRows[0] if selectedRows else None)
        self.pendingInputSelectionEntryIds = set()
        self.inputFileEntries.reverse()
        self.RefreshInputFileState()
        self.RestoreInputFileSelectionRows(selectedRows, currentRow)
        self.MarkProjectDirty()

    def ClearInputPreview(self, preserveScrubberView = False):
        if self.runActive or not hasattr(self, "inputViewport"):
            return

        self.previewPixmap = None
        self.currentInputPreviewFile = None
        self.currentInputPreviewEntryId = None
        self.ClearManualInputViewport()
        self.UpdateCurrentInputPreviewMarker()
        self.inputViewport.Clear("Add Images" if not self.inputPreviewFilenames else "Preview")
        self.UpdateInputEmptyAction()
        self.UpdateFrameScrubber(preserveView = preserveScrubberView)

    def LoadInputPreview(self, filename, entryId = None, preserveScrubberView = False):
        if self.runActive or not hasattr(self, "inputViewport"):
            return

        if entryId is None:
            entryId = self.EntryIdForInputFilename(filename)
        self.currentInputPreviewEntryId = entryId
        self.UpdateCurrentInputPreviewMarker()
        if not self.CheckInputEntryFileExists(entryId, filename):
            self.previewPixmap = None
            self.currentInputPreviewFile = os.path.abspath(filename)
            self.inputViewport.Clear("File not found")
            self.inputViewport.SetEmptyError("File not found")
            self.UpdateFrameScrubber(preserveView = preserveScrubberView)
            return

        reader = QtGui.QImageReader(filename)
        reader.setAutoTransform(True)
        image = reader.read()
        self.inputViewport.SetEmptyAction(False)

        if image.isNull():
            self.SetInputEntryMissing(entryId, True)
            self.RefreshInputFileList()
            self.previewPixmap = None
            self.currentInputPreviewFile = None
            self.currentInputPreviewEntryId = entryId
            self.UpdateCurrentInputPreviewMarker()
            self.inputViewport.Clear("Could not load preview")
            self.UpdateFrameScrubber(preserveView = preserveScrubberView)
            return

        if self.SetInputEntryMissing(entryId, False):
            self.RefreshInputFileList()

        self.inputDimensionCache[filename] = (image.width(), image.height())
        self.RefreshInputDimensionWarnings()
        self.previewPixmap = QtGui.QPixmap.fromImage(image)
        self.currentInputPreviewFile = os.path.abspath(filename)
        self.currentInputPreviewEntryId = entryId
        self.UpdateCurrentInputPreviewMarker()
        self.inputViewport.SetPixmap(
            self.previewPixmap,
            os.path.basename(filename),
            self.InputPreviewMetadataLines(filename, image.width(), image.height()),
        )
        self.inputViewport.SetInfoWarningLines(self.InputPreviewWarningLines())

    def InputPreviewMetadataLines(self, filename, fallbackWidth = None, fallbackHeight = None):
        try:
            metadata = ReadImageMetadata(filename)
        except (OSError, FileNotFoundError):
            metadata = {"transfer": "Unknown", "colorSpace": "Unknown"}
        entry = self.InputEntryById(self.currentInputPreviewEntryId)
        self.RefreshInputEntryTransferWarning(
            self.currentInputPreviewEntryId,
            filename,
            metadata = metadata,
        )
        entryTransferOverride = self.InputEntryTransferOverride(entry)
        warnUnknownTransfer = (
            self.blendInLinear.isChecked()
            and not entryTransferOverride
            and not self.overrideInputTransfer.isChecked()
            and IsUnknownTransferFunction(metadata.get("transfer"))
        )
        transferLine = (
            TransferOverrideLine(entryTransferOverride)
            if entryTransferOverride else
            TransferOverrideLine(self._TransferFunctionValue(self.inputTransferFunction))
            if self.blendInLinear.isChecked() and self.overrideInputTransfer.isChecked() else
            TransferFunctionLine(metadata["transfer"])
            if warnUnknownTransfer else
            f'Transfer Function: {metadata["transfer"]}'
        )
        dimensions = self.CachedImageDimensions(filename)
        if not dimensions and fallbackWidth is not None and fallbackHeight is not None:
            dimensions = (fallbackWidth, fallbackHeight)
        dimensionsLine = ""
        if dimensions:
            dimensionsLine = DimensionsLine("Dimensions", dimensions[0], dimensions[1])
            if self.currentInputPreviewEntryId in self.rescaleWarningInputFilenames:
                dimensionsLine.extend([
                    (" ", "OVERLAY_TEXT"),
                    ("(Image will be scaled to export dimensions)", "WARNING"),
                ])
        metadataLines = [
            dimensionsLine,
            f'Color space: {metadata["colorSpace"]}',
            transferLine,
        ]
        return metadataLines

    def InputPreviewWarningLines(self):
        return []

    def RefreshInputPreviewMetadata(self):
        if (
            not hasattr(self, "inputViewport")
            or not self.currentInputPreviewFile
            or not self.previewPixmap
            or self.previewPixmap.isNull()
        ):
            return

        self.inputViewport.SetPixmap(
            self.previewPixmap,
            os.path.basename(self.currentInputPreviewFile),
            self.InputPreviewMetadataLines(
                self.currentInputPreviewFile,
                self.previewPixmap.width(),
                self.previewPixmap.height(),
            ),
        )
        self.inputViewport.SetInfoWarningLines(self.InputPreviewWarningLines())

    def OutputViewportFilenames(self):
        directory = self.outputDirectory.Text()
        if not directory or not os.path.isdir(directory):
            return []

        outputName = self.outputFileName.text().strip() or "frame"
        outputType = self._CleanFileType(self.outputFileType.currentText())
        if self.exportMode == "final":
            path = os.path.join(directory, f"{outputName}.{outputType}")
            return [path] if os.path.isfile(path) else []

        pattern = re.compile(rf"^{re.escape(outputName)}_(\d{{4,}})\.{re.escape(outputType)}$", re.IGNORECASE)
        filenames = []
        for filename in os.listdir(directory):
            path = os.path.join(directory, filename)
            if os.path.isfile(path) and pattern.match(filename):
                filenames.append(path)
        return sorted(
            filenames,
            key = lambda path: int(pattern.match(os.path.basename(path)).group(1)),
        )

    def UpdateOutputViewport(self, *_):
        if self.runActive or not hasattr(self, "outputViewport"):
            return

        self.UpdateOutputEmptyAction()
        filenames = self.OutputViewportFilenames()
        if not filenames:
            self.currentOutputPreviewFile = None
            if not self.outputDirectory.Text():
                self.outputViewport.Clear("Choose an export folder")
                self.UpdateOutputEmptyAction()
            else:
                self.SetOutputEmptyFramesMessage()
            if hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() == 2:
                self.UpdateFrameScrubber()
            return

        self.LoadOutputPreview(filenames[0])
        if hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() == 2:
            self.UpdateFrameScrubber()

    def LoadOutputPreview(self, filename):
        if not filename or not os.path.isfile(filename):
            self.currentOutputPreviewFile = None
            self.outputViewport.Clear("Export")
            self.UpdateOutputEmptyAction()
            if hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() == 2:
                self.UpdateFrameScrubber()
            return

        reader = QtGui.QImageReader(filename)
        reader.setAutoTransform(True)
        image = reader.read()
        self.outputViewport.SetEmptyAction(False)

        if image.isNull():
            self.currentOutputPreviewFile = None
            self.outputViewport.Clear("Could not load export")
            self.UpdateOutputEmptyAction()
            self.UpdateFrameScrubber()
            return

        metadata = ReadImageMetadata(filename)
        warnUnknownTransfer = self.blendInLinear.isChecked() and IsUnknownTransferFunction(metadata.get("transfer"))
        metadataLines = [
            f"Dimensions: {metadata['dimensions']}" if metadata["dimensions"] else "",
            f'Color space: {metadata["colorSpace"]}',
            TransferFunctionLine(metadata["transfer"])
            if warnUnknownTransfer else
            f'Transfer Function: {metadata["transfer"]}',
        ]
        self.currentOutputPreviewFile = os.path.abspath(filename)
        self.outputViewport.SetPixmap(QtGui.QPixmap.fromImage(image), os.path.basename(filename), metadataLines)

    def ClearPreviewCache(self):
        self.previewCache = []
        self.previewDecodedCache = OrderedDict()
        self.previewCacheBytes = 0
        self.previewCacheLimitReached = False
        self.currentPreviewCacheIndex = None
        if hasattr(self, "previewViewport"):
            self.previewViewport.Clear("Generated previews can be viewed  here")
        if hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() == 1:
            self.UpdateFrameScrubber()

    def EncodePreviewCacheImage(self, image):
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if image.save(buffer, "JPG", 85):
            buffer.close()
            return {
                "format": "jpg",
                "data": bytes(data),
                "width": image.width(),
                "height": image.height(),
                "byteSize": data.size(),
            }

        buffer.close()
        byteSize = image.sizeInBytes() if hasattr(image, "sizeInBytes") else image.width() * image.height() * 4
        return {
            "format": "raw",
            "image": image.copy(),
            "width": image.width(),
            "height": image.height(),
            "byteSize": byteSize,
        }

    def DecodePreviewCacheImage(self, index, entry):
        if index in self.previewDecodedCache:
            image = self.previewDecodedCache.pop(index)
            self.previewDecodedCache[index] = image
            return image

        if entry.get("format") == "jpg":
            image = QtGui.QImage.fromData(entry["data"], "JPG")
        else:
            image = entry["image"]

        if image.isNull():
            return QtGui.QImage()

        self.previewDecodedCache[index] = image
        while len(self.previewDecodedCache) > 6:
            self.previewDecodedCache.popitem(last = False)

        return image

    def CachePreviewFrame(self, image, title, metadataLines):
        cacheEntry = self.EncodePreviewCacheImage(image)
        byteSize = int(cacheEntry.get("byteSize", 0))
        cacheLimitMb = self.previewCacheLimit.value()
        if self.activeSettings:
            cacheLimitMb = self.activeSettings.get("preview", {}).get("cacheLimitMb", cacheLimitMb)
        cacheLimitBytes = int(cacheLimitMb) * 1024 * 1024
        if self.previewCache and self.previewCacheBytes + byteSize > cacheLimitBytes:
            self.previewCacheLimitReached = True
            return False

        cacheEntry.update({
            "title": title,
            "metadata": metadataLines,
            "progress": self.currentRenderFrame,
        })
        self.previewCache.append(cacheEntry)
        self.previewCacheBytes += byteSize
        self.currentPreviewCacheIndex = len(self.previewCache) - 1
        return True

    def LoadCachedPreviewFrame(self, index):
        if not self.previewCache:
            self.currentPreviewCacheIndex = None
            self.previewViewport.Clear("View generated previews here")
            return

        index = max(0, min(int(index), len(self.previewCache) - 1))
        entry = self.previewCache[index]
        self.currentPreviewCacheIndex = index
        image = self.DecodePreviewCacheImage(index, entry)
        if image.isNull():
            self.previewViewport.Clear("Could not load cached preview")
            return
        self.previewPixmap = QtGui.QPixmap.fromImage(image)
        title = "Rendering Preview..." if self.runActive and self.currentRunIsPreview else "Preview"
        self.previewViewport.SetPixmap(self.previewPixmap, title, entry["metadata"])

    def ActiveScrubberFilenames(self):
        if not hasattr(self, "viewportTabs"):
            return []

        if self.viewportTabs.currentIndex() == 1:
            return list(self.previewCache)

        if self.viewportTabs.currentIndex() == 2:
            return self.OutputViewportFilenames()

        return self.InputScrubberFilenames()

    def ActiveScrubberInputEntryIds(self):
        if not hasattr(self, "viewportTabs") or self.viewportTabs.currentIndex() != 0:
            return []
        return self.InputScrubberEntryIds()

    def CurrentScrubberFile(self):
        if not hasattr(self, "viewportTabs"):
            return None

        if self.viewportTabs.currentIndex() == 1:
            return self.currentPreviewCacheIndex

        if self.viewportTabs.currentIndex() == 2:
            return self.currentOutputPreviewFile

        return self.currentInputPreviewFile

    def UpdateFrameScrubber(self, *_, preserveView = False):
        if not hasattr(self, "frameScrubber"):
            return

        filenames = self.ActiveScrubberFilenames()
        self.frameScrubber.updating = True
        self.frameScrubber.SetFrameCount(len(filenames), resetZoom = not preserveView)

        currentFile = self.CurrentScrubberFile()
        if self.viewportTabs.currentIndex() == 1 and currentFile is not None:
            self.frameScrubber.SetValue(currentFile, emit = False)
        elif self.viewportTabs.currentIndex() == 0 and self.currentInputPreviewEntryId is not None:
            for index, entryId in enumerate(self.ActiveScrubberInputEntryIds()):
                if entryId == self.currentInputPreviewEntryId:
                    self.frameScrubber.SetValue(index, emit = False)
                    break
        elif currentFile:
            target = os.path.normcase(os.path.abspath(currentFile))
            for index, filename in enumerate(filenames):
                if os.path.normcase(os.path.abspath(filename)) == target:
                    self.frameScrubber.SetValue(index, emit = False)
                    break

        self.frameScrubber.updating = False
        scrubberEnabled = (not self.runActive) and bool(filenames)
        self.frameScrubber.setEnabled(scrubberEnabled)
        self.UpdateScrubberTransportEnabled(scrubberEnabled)
        self.UpdateFrameScrubberHighlight()
        self.UpdatePreviewOverlay()

    def UpdateScrubberTransportEnabled(self, enabled):
        for button in getattr(self, "scrubberTransportButtons", []):
            button.setEnabled(enabled)

        inputTabActive = hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() == 0
        for button in (
            getattr(self, "transportStartPlaceholderButton", None),
            getattr(self, "transportEndPlaceholderButton", None),
        ):
            if button is not None:
                button.setVisible(inputTabActive)
                button.setEnabled(enabled and inputTabActive)

        if not enabled:
            self.StopScrubberPlayback()
        self.RefreshScrubberTransportLayout()

    def RefreshScrubberTransportLayout(self):
        if not hasattr(self, "scrubberTransport"):
            return

        for button in getattr(self, "scrubberTransportButtons", []):
            width = 54 if button.property("wideTransportButton") else 36
            button.setIconSize(QtCore.QSize(22, 22))
            button.setMinimumSize(width, 32)
            button.setMaximumSize(width, 32)
            button.setFixedSize(width, 32)
            button.style().unpolish(button)
            button.style().polish(button)
            button.updateGeometry()

        self.scrubberTransport.layout().invalidate()
        self.scrubberTransport.adjustSize()
        self.scrubberTransport.updateGeometry()
        if hasattr(self, "viewportOverlay"):
            self.viewportOverlay.PositionOverlay()

    def SetScrubberPlaybackActive(self, active):
        if not hasattr(self, "transportPlayButton"):
            return

        if active:
            self.transportPlayButton.setIcon(AssetIcon("pause_24dp_E3E3E3.svg"))
            self.transportPlayButton.setToolTip("Pause")
        else:
            self.transportPlayButton.setIcon(AssetIcon("play_arrow_24dp_E3E3E3.svg"))
            self.transportPlayButton.setToolTip("Play")

    def UpdateScrubberPlaybackInterval(self, *_):
        if not hasattr(self, "scrubberPlaybackTimer"):
            return

        fps = self.playbackFps.value() if hasattr(self, "playbackFps") else 30
        self.scrubberPlaybackTimer.setInterval(max(1, round(1000 / max(1, fps))))

    def ResetPlaybackFps(self):
        self.playbackFps.setValue(30)

    def ResetPreviewFps(self):
        self.previewFps.setValue(1.0)

    def ToggleScrubberPlayback(self):
        if self.scrubberPlaybackTimer.isActive():
            self.StopScrubberPlayback()
            return

        if self.runActive or not self.ActiveScrubberFilenames():
            return

        trimBounds = self.ActiveInputTrimBounds()
        if trimBounds:
            trimStart, trimEnd = trimBounds
            if self.frameScrubber.value < trimStart or self.frameScrubber.value >= trimEnd:
                self.frameScrubber.SetValue(trimStart, emit = True)
        elif self.frameScrubber.value >= self.frameScrubber.frameCount - 1:
            self.frameScrubber.SetValue(0, emit = True)

        self.UpdateScrubberPlaybackInterval()
        self.scrubberPlaybackTimer.start()
        self.SetScrubberPlaybackActive(True)

    def StopScrubberPlayback(self):
        if hasattr(self, "scrubberPlaybackTimer") and self.scrubberPlaybackTimer.isActive():
            self.scrubberPlaybackTimer.stop()

        self.SetScrubberPlaybackActive(False)

    def AdvanceScrubberPlayback(self):
        if self.runActive or not self.ActiveScrubberFilenames():
            self.StopScrubberPlayback()
            return

        trimBounds = self.ActiveInputTrimBounds()
        if trimBounds:
            _, trimEnd = trimBounds
            if self.frameScrubber.value >= trimEnd:
                self.StopScrubberPlayback()
                return

            nextIndex = min(trimEnd, self.frameScrubber.value + 1)
            self.frameScrubber.SetValue(nextIndex, emit = True)
            if nextIndex >= trimEnd:
                self.StopScrubberPlayback()
            return

        if self.frameScrubber.value >= self.frameScrubber.frameCount - 1:
            self.StopScrubberPlayback()
            return

        self.StepActiveFrame(1)

    def ActiveInputTrimBounds(self):
        if (
            not hasattr(self, "viewportTabs")
            or self.viewportTabs.currentIndex() != 0
            or not self.inputPreviewFilenames
        ):
            return None

        frameCount = len(self.inputPreviewFilenames)
        rangeStart, rangeStop = self.InputTrimRange()
        if rangeStart <= 0 and rangeStop >= frameCount:
            return None

        scrubberSequence, _manuallyEnabled = self.InputScrubberSequence()
        entries = self.DisplayInputFileEntries()
        trimPositions = [
            scrubberIndex
            for scrubberIndex, (position, _enabledIndex) in enumerate(scrubberSequence)
            if rangeStart <= entries[position][1] < rangeStop
        ]
        if not trimPositions:
            return None

        return trimPositions[0], trimPositions[-1]

    def UpdateFrameScrubberHighlight(self):
        if not hasattr(self, "frameScrubber"):
            return

        trimBounds = self.ActiveInputTrimBounds()
        if not trimBounds:
            self.frameScrubber.SetHighlightRange(None, None)
            self.UpdateFullscreenScrubberView()
            return

        self.frameScrubber.SetHighlightRange(*trimBounds)
        self.UpdateFullscreenScrubberView()

    def FrameScrubberChanged(self, index, preserveView = False):
        if self.runActive:
            return

        filenames = self.ActiveScrubberFilenames()
        if not filenames:
            return

        index = max(0, min(int(index), len(filenames) - 1))
        if self.viewportTabs.currentIndex() == 1:
            self.LoadCachedPreviewFrame(index)
        elif self.viewportTabs.currentIndex() == 2:
            self.LoadOutputPreview(filenames[index])
        else:
            self.ClearManualInputViewport()
            entryIds = self.ActiveScrubberInputEntryIds()
            entryId = entryIds[index] if index < len(entryIds) else None
            self.LoadInputPreview(filenames[index], entryId, preserveScrubberView = preserveView)
            self.SyncInputFileSelectionToEntryId(entryId)

        self.UpdateFrameScrubber(preserveView = preserveView)
        self.UpdatePreviewOverlay()

    def StepActiveFrame(self, step, wrap = False):
        if self.runActive or not hasattr(self, "frameScrubber"):
            return

        filenames = self.ActiveScrubberFilenames()
        if not filenames:
            return

        step = int(step)
        currentIndex = max(0, min(len(filenames) - 1, self.frameScrubber.value))
        trimBounds = self.ActiveInputTrimBounds()
        if trimBounds:
            trimStart, trimEnd = trimBounds
            if currentIndex < trimStart or currentIndex > trimEnd:
                nextIndex = trimStart if step >= 0 else trimEnd
            else:
                nextIndex = currentIndex + step
                if nextIndex > trimEnd and wrap:
                    nextIndex = trimStart
                elif nextIndex < trimStart and wrap:
                    nextIndex = trimEnd
                else:
                    nextIndex = max(trimStart, min(trimEnd, nextIndex))
        else:
            if wrap:
                nextIndex = (currentIndex + step) % len(filenames)
            else:
                nextIndex = max(0, min(len(filenames) - 1, currentIndex + step))

        self.frameScrubber.SetValue(nextIndex, emit = True)

    def JumpActiveFrame(self, target):
        if self.runActive or not hasattr(self, "frameScrubber"):
            return

        filenames = self.ActiveScrubberFilenames()
        if not filenames:
            return

        trimBounds = self.ActiveInputTrimBounds()
        if trimBounds:
            trimStart, trimEnd = trimBounds
            index = trimStart if target == "first" else trimEnd
        else:
            index = 0 if target == "first" else len(filenames) - 1
        self.frameScrubber.SetValue(index, emit = True)

    def MarkCurrentScrubberFrame(self, markType):
        if not hasattr(self, "frameScrubber"):
            return

        self.MarkRangeFromScrubber(markType, self.frameScrubber.value)

    def ResetTrimRange(self):
        if (
            self.runActive
            or not self.inputPreviewFilenames
            or not hasattr(self, "rangeField")
        ):
            return

        frameCount = len(self.inputPreviewFilenames)
        if self.InputTrimRange() == (0, frameCount):
            return

        self.ApplyTrimRange(0, frameCount, preserveScrubberView = True)
        self.MarkProjectDirty()

    def MarkRangeFromFileList(self, markType):
        if self.runActive or not self.inputPreviewFilenames or not hasattr(self, "rangeField"):
            return

        entryId = self.fileListContextEntryId
        if entryId is None:
            current = self.inputFileList.currentIndex()
            entryId = current.data(ENTRY_ID_ROLE) if current.isValid() else None
        sourceFrame = self.SourceIndexForInputEntry(entryId)
        if sourceFrame is None:
            return

        self.MarkRangeFromSourceFrame(markType, sourceFrame)

    def MarkRangeFromSourceFrame(self, markType, sourceFrame):
        rangeStart, rangeStop = self.rangeField.Values()
        frameCount = len(self.inputPreviewFilenames)
        if frameCount <= 0:
            return

        sourceFrame = max(0, min(int(sourceFrame), frameCount - 1))
        sourceStop = min(frameCount, sourceFrame + 1)

        if markType == "reset":
            rangeStart = 0
            rangeStop = frameCount
        else:
            if markType == "in":
                if sourceFrame >= rangeStop:
                    rangeStop = frameCount
                    rangeStart = min(sourceFrame, max(0, rangeStop - 1))
                else:
                    rangeStart = min(sourceFrame, max(0, rangeStop - 1))
            elif markType == "out":
                if sourceFrame <= rangeStart:
                    rangeStart = 0
                    rangeStop = max(1, sourceStop)
                else:
                    rangeStop = max(1, sourceStop)
            else:
                return

        rangeStart = max(0, min(rangeStart, frameCount - 1))
        rangeStop = max(rangeStart + 1, min(rangeStop, frameCount))
        self.ApplyTrimRange(rangeStart, rangeStop, preserveScrubberView = True)

    def ApplyTrimRange(self, rangeStart, rangeStop, preserveScrubberView = False):
        snapshot = self.ScrubberViewSnapshot() if preserveScrubberView else None
        try:
            self.suppressRangePreview = True
            self.rangeField.SetValues(rangeStart, rangeStop)
        finally:
            self.suppressRangePreview = False

        self.RefreshInputStatusLabel()
        self.RefreshInputPreviewMetadata()
        self.UpdateEffectiveOverrideValues()
        self.UpdateFrameScrubberHighlight()
        self.RefreshInputFileList()
        self.UpdateInputFileActionButtons()
        if preserveScrubberView:
            self.UpdateFrameScrubber(preserveView = True)
            self.RestoreScrubberViewSnapshot(snapshot)
            self.UpdateFrameScrubberHighlight()
            self.UpdatePreviewOverlay()

    def TrimDragStarted(self, *_):
        self.scrubberTrimDragStartRange = self.rangeField.Values()

    def TrimDragEnded(self):
        self.scrubberTrimDragStartRange = None

    def MarkRangeFromScrubber(self, markType, frame):
        if self.runActive or not self.inputPreviewFilenames:
            return

        if hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() != 0:
            return

        sequence, _manuallyEnabled = self.InputScrubberSequence()
        entries = self.DisplayInputFileEntries()
        if not sequence:
            return

        frame = max(0, min(int(frame), len(sequence) - 1))
        rangeStart, rangeStop = self.rangeField.Values()
        frameCount = len(self.inputPreviewFilenames)
        sourcePosition = sequence[frame][0]
        if sourcePosition < 0 or sourcePosition >= len(entries):
            return

        sourceFrame = entries[sourcePosition][1]
        sourceStop = min(frameCount, sourceFrame + 1)
        dragMark = markType.startswith("drag-")
        if dragMark:
            markType = markType[5:]

        if dragMark and self.scrubberTrimDragStartRange is not None:
            dragStart, dragStop = self.scrubberTrimDragStartRange
            if markType == "in":
                if sourceFrame < dragStop:
                    rangeStart = sourceFrame
                    rangeStop = dragStop
                else:
                    rangeStart = max(0, dragStop - 1)
                    rangeStop = sourceStop
            elif markType == "out":
                if sourceStop > dragStart:
                    rangeStart = dragStart
                    rangeStop = sourceStop
                else:
                    rangeStart = sourceFrame
                    rangeStop = dragStart + 1
            else:
                return

            rangeStart = max(0, min(rangeStart, frameCount - 1))
            rangeStop = max(rangeStart + 1, min(rangeStop, frameCount))
            self.ApplyTrimRange(rangeStart, rangeStop, preserveScrubberView = True)
            return

        if markType == "reset":
            rangeStart = 0
            rangeStop = frameCount
        else:
            if markType == "in":
                if dragMark:
                    rangeStart, rangeStop = sorted((sourceFrame, rangeStop))
                    rangeStop = max(rangeStart + 1, rangeStop)
                elif sourceFrame >= rangeStop:
                    rangeStop = len(self.inputPreviewFilenames)
                    rangeStart = min(sourceFrame, max(0, rangeStop - 1))
                else:
                    rangeStart = min(sourceFrame, max(0, rangeStop - 1))
            elif markType == "out":
                if dragMark:
                    rangeStart, rangeStop = sorted((rangeStart, sourceFrame))
                    rangeStop = max(rangeStart + 1, rangeStop)
                elif sourceFrame <= rangeStart:
                    rangeStart = 0
                    rangeStop = max(1, sourceStop)
                else:
                    rangeStop = max(1, sourceStop)
            else:
                return

        rangeStart = max(0, min(rangeStart, frameCount - 1))
        rangeStop = max(rangeStart + 1, min(rangeStop, frameCount))

        self.ApplyTrimRange(rangeStart, rangeStop, preserveScrubberView = True)

    def _BuildSettings(self):
        outputType = self._CleanFileType(self.outputFileType.currentText())
        renderPath = self.RenderPath()
        pairBlur = self.pairBlurSpinBox.value()
        pairBlurActive = renderPath == 1 and pairBlur > 0
        if pairBlurActive:
            inputFilenames = self.InputScrubberFilenames()
            inputIndices = self.InputReadScrubberIndices()
            transferOverrides = self.InputScrubberTransferOverrides()
        else:
            inputFilenames = self.InputReadFilenames()
            inputIndices = None
            transferOverrides = self.InputReadTransferOverrides()
        stopAfter = len(inputFilenames)
        if inputIndices is not None:
            stopAfter = len(inputIndices)
        previewEnabled = self.previewEnabled.isChecked()
        startAt = 0
        blendInLinear = self.blendInLinear.isChecked()
        inputTransferOverride = blendInLinear and self.overrideInputTransfer.isChecked()
        outputTransferOverride = blendInLinear and self.overrideOutputTransfer.isChecked()
        exportResolution = self.EffectiveExportResolution() or (self.overrideWidth.value(), self.overrideHeight.value())

        return {
            "render": {
                "path": renderPath,
                "windowSize": max(0, self.stackSizeSpinBox.value() - 1),
                "pairOffset": self.CurrentShift(),
                "pairBlur": pairBlur,
                "pairKernel": self.pairBlurKernel.currentText(),
                "stackDirection": self.stackDirection.currentText().lower(),
                "blendInLinear": blendInLinear,
            },
            "input": {
                "inputDirectory": self.inputDirectory.Text(),
                "inputFileType": "mixed",
                "startAt": startAt,
                "skipInput": 1,
                "inputIndices": inputIndices,
                "inputFilenames": inputFilenames,
                "transferOverrides": transferOverrides,
                "excludedFilenames": [],
                "overrideTransferFunction": inputTransferOverride,
                "transferFunction": self._TransferFunctionValue(self.inputTransferFunction),
                "overrideResolution": self.overrideResolution.isChecked(),
                "resizeFilter": self.resizeFilter.currentText(),
                "width": exportResolution[0],
                "height": exportResolution[1],
                "mixedDimensions": self.inputHasMixedDimensions,
            },
            "blend": {
                "mode": self.blendMode.currentData(),
                "decay": self.decay.Value(),
                "scale": self.blendScaleSpinBox.value(),
                "lift": self.blendOffsetSpinBox.value(),
                "absolute": self.absoluteValues.isChecked(),
                "opacity": self.opacity.Value(),
                "middleGray": self.middleGray.Value() if self.useCustomMiddleGray.isChecked() else 0.5,
            },
            "output": {
                "outputDirectory": self.outputDirectory.Text(),
                "outputFileName": self.outputFileName.text().strip() or "frame",
                "outputFileType": outputType,
                "onlyExportFinalFrame": self.exportMode == "final",
                "stopAfter": stopAfter,
                "skipOutput": self.skipOutput.value(),
                "outputParms": self._BuildOutputParms(outputType),
                "overrideTransferFunction": outputTransferOverride,
                "transferFunction": self._TransferFunctionValue(self.outputTransferFunction),
            },
            "preview": {
                "enabled": previewEnabled,
                "scale": self.previewScale.currentData(),
                "fps": self.previewFps.value(),
                "renderScale": 1,
                "cacheLimitMb": self.previewCacheLimit.value(),
            },
        }

    def _EntryFilenameAndTransferOverride(self, entryId):
        entry = self.InputEntryById(entryId)
        if not entry:
            return None, None
        return entry.get("filename"), self.InputEntryTransferOverride(entry)

    def _ApplyFinalOnlyIndependentRenderOptimization(self, settings):
        if settings["output"].get("onlyExportFinalFrame") is not True:
            return None

        renderPath = int(settings["render"].get("path", 0))
        if renderPath not in (1, 2):
            return None

        readEntryIds = self.InputReadEntryIds()
        if not readEntryIds:
            return None

        optimizedEntryIds = []
        if renderPath == 1:
            if int(settings["render"].get("pairBlur", 0)) > 0:
                return None

            shift = int(settings["render"].get("pairOffset", 0))
            currentEntryId = readEntryIds[-1]
            pairedEntryId = None

            if shift < 0:
                pairedIndex = len(readEntryIds) - 1 + shift
                if pairedIndex >= 0:
                    pairedEntryId = readEntryIds[pairedIndex]
            elif shift > 0:
                scrubberEntryIds = self.InputScrubberEntryIds()
                try:
                    currentScrubberIndex = scrubberEntryIds.index(currentEntryId)
                except ValueError:
                    currentScrubberIndex = -1

                pairedScrubberIndex = currentScrubberIndex + shift
                if 0 <= pairedScrubberIndex < len(scrubberEntryIds):
                    pairedEntryId = scrubberEntryIds[pairedScrubberIndex]
                else:
                    currentIndex = max(0, len(readEntryIds) - 1 - shift)
                    currentEntryId = readEntryIds[currentIndex]
                    pairedEntryId = readEntryIds[-1]
            else:
                pairedEntryId = currentEntryId

            optimizedEntryIds = [currentEntryId]
            if pairedEntryId is not None:
                optimizedEntryIds.append(pairedEntryId)
            settings["render"]["pairOffset"] = 1

        elif renderPath == 2:
            stackLength = max(1, int(settings["render"].get("windowSize", 0)) + 1)
            optimizedEntryIds = readEntryIds[-stackLength:][::-1]
            settings["render"]["windowSize"] = max(0, len(optimizedEntryIds) - 1)
            settings["render"]["stackDirection"] = "future"

        filenames = []
        transferOverrides = []
        for entryId in optimizedEntryIds:
            filename, transferOverride = self._EntryFilenameAndTransferOverride(entryId)
            if filename:
                filenames.append(filename)
                transferOverrides.append(transferOverride)

        if not filenames:
            return None

        settings["input"]["inputFilenames"] = filenames
        settings["input"]["transferOverrides"] = transferOverrides
        settings["input"]["inputIndices"] = None
        settings["output"]["stopAfter"] = 1
        settings["output"]["skipOutput"] = 1
        return optimizedEntryIds[:1]

    def InputScrubberStartIndex(self):
        if not self.inputPreviewFilenames:
            return 0

        activeInputFiles = self.InputScrubberFilenames()
        if hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() == 0:
            return max(0, min(self.frameScrubber.value, len(activeInputFiles) - 1))

        if self.currentInputPreviewFile:
            target = os.path.normcase(os.path.abspath(self.currentInputPreviewFile))
            for index, filename in enumerate(activeInputFiles):
                if os.path.normcase(os.path.abspath(filename)) == target:
                    return index

        return 0

    def ApplyPreviewRenderRange(self, settings):
        pairBlurActive = int(settings["render"].get("path", 0)) == 1 and int(settings["render"].get("pairBlur", 0)) > 0
        if self.previewFrameCount == "range":
            frameIndices = settings["input"].get("inputIndices")
            if frameIndices is None:
                settings["output"]["stopAfter"] = max(1, len(settings["input"].get("inputFilenames") or []))
            else:
                settings["output"]["stopAfter"] = max(1, len(frameIndices))
        elif pairBlurActive:
            settings["input"]["inputFilenames"] = self.InputScrubberFilenames()
            settings["input"]["transferOverrides"] = self.InputScrubberTransferOverrides()
            settings["input"]["inputIndices"] = self.InputReadScrubberIndicesFromScrubber(self.previewFrameCount, clampToTrim = True)
            settings["output"]["stopAfter"] = max(1, len(settings["input"]["inputIndices"]))
        else:
            settings["input"]["inputFilenames"] = self.InputReadFilenamesFromScrubber(self.previewFrameCount, clampToTrim = True)
            settings["input"]["transferOverrides"] = self.InputReadTransferOverridesFromScrubber(self.previewFrameCount, clampToTrim = True)
            settings["input"]["inputIndices"] = None
            settings["output"]["stopAfter"] = max(1, len(settings["input"]["inputFilenames"]))
        settings["output"]["skipOutput"] = 1
        settings["output"]["onlyExportFinalFrame"] = False

    def _BuildOutputParms(self, outputType):
        outputType = self._CleanFileType(outputType)

        if outputType == "jpg":
            parms = {
                "quality": self.jpgQuality.value(),
            }
            if self.jpgOptimize.isChecked():
                parms["optimize"] = True
            if self.jpgProgressive.isChecked():
                parms["progressive"] = True

            subsampling = self.jpgSubsampling.currentData()
            if subsampling is not None:
                parms["subsampling"] = subsampling

            return parms

        if outputType == "png":
            parms = {
                "compress_level": self.pngCompressLevel.value(),
            }
            if self.pngOptimize.isChecked():
                parms["optimize"] = True
            return parms

        if outputType == "tiff":
            compression = self.tiffCompression.currentData()
            if compression:
                return {"compression": compression}
            return {}

        return {}

    def _ValidateSettings(self, settings, previewOnly = False):
        outputDirectory = settings["output"]["outputDirectory"]
        outputType = settings["output"]["outputFileType"]
        inputFilenames = settings["input"].get("inputFilenames") or []

        if not inputFilenames:
            self.ShowErrorMessage("Input Files", "Add at least one image to the render list.")
            return False

        missingFilenames = [filename for filename in inputFilenames if not os.path.isfile(filename)]
        if missingFilenames:
            self.MarkMissingInputFiles(missingFilenames)
            self.ShowMissingRenderFilesMessage(missingFilenames)
            return False

        if not previewOnly and not outputDirectory:
            self.ShowWarningMessage("Export Folder", "Choose an export folder.")
            return False

        if not previewOnly and not outputType:
            self.ShowWarningMessage("Export Type", "Choose an export file type.")
            return False

        return True

    def ShowMissingRenderFilesMessage(self, missingFilenames):
        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle("Render Failed")
        message.setWindowIcon(StatusAssetIcon("error"))
        message.setIconPixmap(self.TintedAssetPixmap("error_24dp_E3E3E3.svg", "ERROR", 48))
        message.setText("Source images for some of the files in the render region are missing:")
        imageList = "\n".join(f"- {os.path.basename(filename)}" for filename in missingFilenames)
        message.setInformativeText(f"{imageList}\n\nRender can't continue.")
        message.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
        message.exec()

    def ShowAppMessage(self, title, text, iconName, colorKey, informativeText = None, standardButtons = None, defaultButton = None):
        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle(title)
        message.setWindowIcon(StatusAssetIcon(colorKey))
        message.setIconPixmap(self.TintedAssetPixmap(iconName, colorKey, 48))
        message.setText(text)
        if informativeText:
            message.setInformativeText(informativeText)
        message.setStandardButtons(standardButtons or QtWidgets.QMessageBox.StandardButton.Ok)
        if defaultButton is not None:
            message.setDefaultButton(defaultButton)
        return message.exec()

    def ShowWarningMessage(self, title, text, informativeText = None, standardButtons = None, defaultButton = None):
        return self.ShowAppMessage(title, text, "warning_24dp_E3E3E3.svg", "WARNING", informativeText, standardButtons, defaultButton)

    def ShowErrorMessage(self, title, text, informativeText = None, standardButtons = None, defaultButton = None):
        return self.ShowAppMessage(title, text, "error_24dp_E3E3E3.svg", "ERROR", informativeText, standardButtons, defaultButton)

    def ShowInfoMessage(self, title, text, informativeText = None, standardButtons = None, defaultButton = None):
        return self.ShowAppMessage(title, text, "info_24dp_E3E3E3.svg", "INFO", informativeText, standardButtons, defaultButton)

    def TintedAssetPixmap(self, iconName, colorKey, size):
        pixmap = AssetIcon(iconName).pixmap(size, size)
        tinted = QtGui.QPixmap(pixmap.size())
        tinted.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(tinted)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), ThemeQColor(colorKey))
        painter.end()
        return tinted

    def StartExport(self):
        if self.thread and self.thread.isRunning():
            if self.currentRunIsPreview and self.pauseEvent and self.pauseEvent.is_set():
                self.pendingExportAfterCancel = True
                self.CancelRender(resetUi = False)
            return

        if getattr(self, "stackMemoryExceeded", False):
            self.ShowErrorMessage(
                "Stack Memory",
                "Estimated stack memory exceeds currently available RAM.",
                "Reduce the stack size or close other applications before exporting.",
            )
            return

        self.StartRender(previewOnly = False)

    def StartPreview(self):
        if self.thread and self.thread.isRunning():
            return

        self.StartRender(previewOnly = True)

    def StartRender(self, previewOnly = False):
        if not previewOnly and not self.outputDirectory.Text():
            if not self.OpenOutputFolderBrowser():
                return

        settings = self._BuildSettings()
        renderEntryIds = self.InputReadEntryIds()
        if previewOnly:
            if self.previewFrameCount != "range":
                renderEntryIds = self.InputReadEntryIdsFromScrubber(self.previewFrameCount, clampToTrim = True)
            self.ApplyPreviewRenderRange(settings)
        else:
            optimizedEntryIds = self._ApplyFinalOnlyIndependentRenderOptimization(settings)
            if optimizedEntryIds is not None:
                renderEntryIds = optimizedEntryIds
        if not self._ValidateSettings(settings, previewOnly):
            return
        renderFrameCount = max(0, int(settings["output"].get("stopAfter", len(renderEntryIds)) or len(renderEntryIds)))
        self.activeRenderEntryIds = renderEntryIds[:renderFrameCount]
        settings["preview"]["renderScale"] = settings["preview"]["scale"] if previewOnly else 1
        self.currentRunIsPreview = previewOnly
        self.pendingExportAfterCancel = False
        self.activeSettings = settings
        if hasattr(self, "sidebarTabs"):
            self.sidebarTabs.setCurrentIndex(0)
        self.viewportTabs.setCurrentIndex(1 if previewOnly else 2)
        self.UpdateInputSyncForViewportTab()
        self.BeginRenderInputSync()
        self.ClearPreviewCache()
        self.ClearRenderLog()

        self.ResetRunDisplay("Preview" if (settings["preview"]["enabled"] or previewOnly) else "Preview disabled")

        self.cancelEvent = threading.Event()
        self.pauseEvent = threading.Event()
        self.thread = QtCore.QThread(self)
        self.worker = RenderWorker(settings, self.cancelEvent, self.pauseEvent, previewOnly)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.Run)
        self.worker.progress.connect(self.UpdateProgress)
        self.worker.fps.connect(self.UpdateFps)
        self.worker.remaining.connect(self.UpdateRemaining)
        self.worker.preview.connect(self.UpdatePreview)
        self.worker.log.connect(self.AppendRenderLog)
        self.worker.finished.connect(self.RenderFinished)
        self.worker.cancelled.connect(self.RenderCancelled)
        self.worker.error.connect(self.RenderFailed)

        self.worker.finished.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.worker.error.connect(lambda _: self.thread.quit())
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.ThreadFinished)

        self.SetRunning(True)
        self.thread.start()

    def ResetRunDisplay(self, previewText = "Preview"):
        self.previewPixmap = None
        self.RenderViewport().Clear(previewText)
        self.progressBar.setRange(0, 1)
        self.progressBar.setValue(0)
        self.progressText = "0/0"
        self.fpsText = "0.0 fps"
        self.remainingText = "-- remaining"
        self.UpdatePreviewOverlay()

    def RenderViewport(self):
        if self.currentRunIsPreview:
            return self.previewViewport
        return self.outputViewport

    def CancelRender(self, resetUi = True):
        if self.cancelEvent:
            self.cancelEvent.set()
            self.cancelButton.setEnabled(False)
            if resetUi:
                if self.currentRunIsPreview:
                    self.UpdateFrameScrubber()
                else:
                    self.UpdateOutputViewport()
                    self.UpdateRangePreview()
            self.UpdateStatusBar()

    def TogglePause(self):
        if not self.pauseEvent:
            return

        if self.pauseEvent.is_set():
            self.pauseEvent.clear()
            self.UpdateStatusBar()
        else:
            self.pauseEvent.set()
            self.UpdateStatusBar()

        self.UpdateRunButtons()
        self.UpdatePreviewOptionsEnabled()

    def SetRunning(self, running):
        if running:
            self.StopScrubberPlayback()

        self.runActive = running
        if hasattr(self, "scrubberTransport"):
            self.scrubberTransport.setVisible(not running)
        self.progressBar.setVisible(running)
        if hasattr(self, "progressRow"):
            self.progressRow.setVisible(running and (not self.viewportOnlyMode))
        self.progressBar.setObjectName("runningProgress" if running else "idleProgress")
        self.progressBar.style().unpolish(self.progressBar)
        self.progressBar.style().polish(self.progressBar)
        for widget in self.settingsWidgets:
            if hasattr(widget, "SetEnabled"):
                widget.SetEnabled(not running)
            else:
                widget.setEnabled(not running)

        self.advancedButton.setEnabled(not running)
        self.frameScrubber.setEnabled(not running and self.frameScrubber.frameCount > 0)
        self.UpdateScrubberTransportEnabled(not running and self.frameScrubber.frameCount > 0)
        self.UpdateRunButtons()
        self.UpdateViewportFooterControls()
        self.UpdateViewportInfoVisibility()
        self.UpdateRenderPathControls()
        self.UpdateBlendControlsEnabled()
        self.UpdateTransferOverrideControls()
        self.UpdateMiddleGrayControls()
        self.UpdatePreviewOptionsEnabled()
        self.UpdateBlendResetButtons()
        self.UpdateStatusBar()

    def BeginRenderInputSync(self):
        if not hasattr(self, "syncInputSelectionButton"):
            return

        self.renderSyncPreviousChecked = (
            bool(self.inputSyncRestoreChecked)
            if getattr(self, "inputSyncSuspendedByViewport", False) else
            self.syncInputSelectionButton.isChecked()
        )
        self.renderSyncActive = True
        if getattr(self, "inputSyncSuspendedByViewport", False):
            return

        if not self.renderSyncPreviousChecked:
            self.syncInputSelectionButton.blockSignals(True)
            self.syncInputSelectionButton.setChecked(True)
            self.syncInputSelectionButton.blockSignals(False)
            self.UpdateInputFileSelectionMode()

    def EndRenderInputSync(self):
        if not getattr(self, "renderSyncActive", False) or not hasattr(self, "syncInputSelectionButton"):
            return

        previousChecked = bool(getattr(self, "renderSyncPreviousChecked", False))
        self.renderSyncActive = False
        if getattr(self, "inputSyncSuspendedByViewport", False):
            self.inputSyncRestoreChecked = previousChecked
            self.UpdateInputSyncForViewportTab()
            return

        if self.syncInputSelectionButton.isChecked() != previousChecked:
            self.syncInputSelectionButton.blockSignals(True)
            self.syncInputSelectionButton.setChecked(previousChecked)
            self.syncInputSelectionButton.blockSignals(False)
            self.UpdateInputFileSelectionMode()
        self.UpdateInputSyncForViewportTab()

    def FixedFormLabel(self, text, width):
        label = QtWidgets.QLabel(text)
        label.setFixedWidth(width)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        return label

    def BlendResetField(self, field, key, tooltip):
        if not hasattr(self, "blendResetButtons"):
            self.blendResetButtons = {}

        button = QtWidgets.QPushButton()
        button.setIcon(AssetIcon("refresh_24dp_E3E3E3.svg"))
        button.setToolTip(tooltip)
        button.setFixedWidth(34)
        button.clicked.connect(lambda checked = False, key = key: self.ResetBlendControl(key))
        self.blendResetButtons[key] = button

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return widget

    def AddFixedFormRow(self, layout, text, field, width):
        label = self.FixedFormLabel(text, width)
        layout.addRow(label, field)
        self.RefreshScrubberTransportLayout()
        return label

    def AddFormGap(self, layout, height = 8):
        spacer = QtWidgets.QWidget()
        spacer.setFixedHeight(height)
        layout.addRow(spacer)
        return spacer

    def UpdateRunButtons(self):
        if not all(hasattr(self, name) for name in ("previewButton", "exportButton", "cancelButton")):
            return

        running = self.runActive
        hasRenderFrames = bool(self.InputReadFilenames())
        memoryExceeded = bool(getattr(self, "stackMemoryExceeded", False))

        self.previewButton.setEnabled((not running) and hasRenderFrames)
        self.exportButton.setEnabled((not running) and hasRenderFrames and not memoryExceeded)
        self.previewButton.setToolTip("" if hasRenderFrames else "Add at least one image to the render list")
        if not hasRenderFrames:
            self.exportButton.setToolTip("Add at least one image to the render list")
        elif memoryExceeded:
            self.exportButton.setToolTip("Estimated stack memory exceeds currently available RAM")
        else:
            self.exportButton.setToolTip("")
        self.cancelButton.setEnabled(running)
        self.cancelButton.setText(IconButtonText("Stop"))
        self.UpdateViewportFooterControls()

    def UpdateStatusBar(self):
        pass

    @QtCore.Slot(int, int)
    def UpdateProgress(self, currentFrame, frameCount):
        self.currentRenderFrame = currentFrame
        self.currentRenderFrameCount = frameCount
        self.progressBar.setRange(0, max(1, frameCount))
        self.progressBar.setValue(currentFrame)
        self.progressText = f"{currentFrame}/{frameCount}"
        self.UpdateRenderInputSelection(currentFrame)
        self.UpdatePreviewOverlay()

    def UpdateRenderInputSelection(self, currentFrame):
        if not getattr(self, "renderSyncActive", False) or not hasattr(self, "inputFileModel"):
            return

        renderIndex = max(0, int(currentFrame) - 1)
        if renderIndex >= len(self.activeRenderEntryIds):
            return

        entryId = self.activeRenderEntryIds[renderIndex]
        row = self.inputFileModel.RowForEntryId(entryId)
        if row is None:
            return

        index = self.inputFileModel.index(row, 0)
        selection = self.inputFileList.selectionModel()
        if selection is None:
            return

        self.suppressInputFileSelectionSync = True
        try:
            selection.clearSelection()
            selection.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
            selection.setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
            self.inputFileList.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
        finally:
            self.suppressInputFileSelectionSync = False

    @QtCore.Slot(float)
    def UpdateFps(self, fps):
        self.fpsText = f"{fps:.1f} fps"
        self.UpdatePreviewOverlay()

    @QtCore.Slot(float)
    def UpdateRemaining(self, seconds):
        self.remainingText = f"{self.FormatDuration(seconds)} remaining"
        self.UpdatePreviewOverlay()

    def UpdatePreviewOverlay(self):
        if hasattr(self, "inputViewport"):
            self.inputViewport.SetOverlayLines([])
        if hasattr(self, "previewViewport"):
            self.previewViewport.SetOverlayLines([])
        if hasattr(self, "outputViewport"):
            self.outputViewport.SetOverlayLines([])

        if self.runActive:
            self.RenderViewport().SetOverlayLines([self.progressText, self.fpsText, self.remainingText])
            return

        viewport = self.ActiveViewport()
        if viewport is not None:
            viewport.SetOverlayLines(self.IdleViewportOverlayLines(viewport))

    def ActiveViewport(self):
        if not hasattr(self, "viewportTabs"):
            return None

        tabIndex = self.viewportTabs.currentIndex()
        if tabIndex == 1:
            return self.previewViewport
        if tabIndex == 2:
            return self.outputViewport
        return self.inputViewport

    def ActiveViewportHasImage(self):
        return self.ViewportHasImage(self.ActiveViewport())

    def ViewportHasImage(self, viewport):
        if viewport is None:
            return False
        pixmap = getattr(viewport, "pixmap", None)
        return pixmap is not None and not pixmap.isNull()

    def CopyActiveViewportToClipboard(self):
        viewport = self.ActiveViewport()
        pixmap = getattr(viewport, "pixmap", None)
        if pixmap is None or pixmap.isNull():
            return
        QtWidgets.QApplication.clipboard().setPixmap(pixmap)

    def ScrubberCounterText(self):
        if not hasattr(self, "frameScrubber") or self.frameScrubber.frameCount <= 0:
            return "0/0"

        currentFrame = max(0, min(self.frameScrubber.value, self.frameScrubber.frameCount - 1)) + 1
        return f"{currentFrame}/{self.frameScrubber.frameCount}"

    def IdleViewportOverlayLines(self, viewport):
        if viewport is self.inputViewport:
            lines = []
            if self.overlayShowFrameIndex:
                lines.append(self.InputRenderFrameIndexText())
            if self.overlayShowImageIndex:
                lines.append(self.InputImageIndexText())
            return lines

        return [self.ScrubberCounterText()] if self.overlayShowFrameIndex else []

    def InputImageIndexText(self):
        return self.ScrubberCounterText()

    def InputRenderFrameIndexText(self):
        if not hasattr(self, "frameScrubber") or self.frameScrubber.frameCount <= 0:
            return "----"

        entryIds = self.ActiveScrubberInputEntryIds()
        scrubberIndex = max(0, min(self.frameScrubber.value, len(entryIds) - 1)) if entryIds else None
        if scrubberIndex is None:
            return "----"

        currentEntryId = entryIds[scrubberIndex]
        activeFrameNumbers, _manuallyEnabled = self.InputReadPlan()
        displayPosition = None
        for position, (_filename, _sourceIndex, entryId) in enumerate(self.DisplayInputFileEntries()):
            if entryId == currentEntryId:
                displayPosition = position
                break

        frameNumber = activeFrameNumbers.get(displayPosition) if displayPosition is not None else None
        if frameNumber is None:
            return "----"

        maxFrameNumber = max(activeFrameNumbers.values()) if activeFrameNumbers else 0
        digits = max(4, len(str(maxFrameNumber)))
        return f"{frameNumber:0{digits}d}/{maxFrameNumber:0{digits}d}"

    def FormatDuration(self, seconds):
        seconds = max(0, int(round(seconds)))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"

        return f"{minutes:d}:{seconds:02d}"

    @QtCore.Slot(QtGui.QImage, bool)
    def UpdatePreview(self, image, displayFrame):
        dimensionLabel = "Preview Dimensions"
        metadataLines = []
        if not self.currentRunIsPreview and self.activeSettings:
            inputSettings = self.activeSettings.get("input", {})
            exportWidth = int(inputSettings.get("width", image.width()))
            exportHeight = int(inputSettings.get("height", image.height()))
            metadataLines.append(DimensionsLine("Export Dimensions", exportWidth, exportHeight))
        metadataLines.append(DimensionsLine(dimensionLabel, image.width(), image.height()))
        if self.activeSettings and self.activeSettings.get("input", {}).get("overrideTransferFunction"):
            metadataLines.append(TransferOverrideLine(self.activeSettings["input"].get("transferFunction", "sRGB / Display P3")))
        title = "Rendering Preview..." if self.currentRunIsPreview else "Rendering..."
        if self.currentRunIsPreview:
            cached = self.CachePreviewFrame(image, title, metadataLines)
            if not cached and self.cancelEvent:
                self.cancelEvent.set()
            if displayFrame:
                if cached:
                    self.LoadCachedPreviewFrame(self.currentPreviewCacheIndex)
                else:
                    self.previewPixmap = QtGui.QPixmap.fromImage(image)
                    self.previewViewport.SetPixmap(self.previewPixmap, title, metadataLines)
                self.UpdateFrameScrubber()
            else:
                return
        else:
            self.previewPixmap = QtGui.QPixmap.fromImage(image)
            self.currentOutputPreviewFile = None
            self.outputViewport.SetPixmap(self.previewPixmap, title, metadataLines)
        self._RefreshPreview()

    def _RefreshPreview(self):
        for viewport in (
            getattr(self, "inputViewport", None),
            getattr(self, "previewViewport", None),
            getattr(self, "outputViewport", None),
        ):
            if viewport is not None:
                viewport.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._RefreshPreview()

    @QtCore.Slot()
    def RenderFinished(self):
        self.SetRunning(False)
        self.EndRenderInputSync()
        if not self.currentRunIsPreview:
            self.UpdateOutputViewport()
        else:
            self.UpdateFrameScrubber()
            if self.currentPreviewCacheIndex is not None:
                self.LoadCachedPreviewFrame(self.currentPreviewCacheIndex)
        self.UpdateStatusBar()
        if not self.currentRunIsPreview:
            self.ShowInfoMessage("Stacker", "Export finished.")

    @QtCore.Slot()
    def RenderCancelled(self):
        self.SetRunning(False)
        self.EndRenderInputSync()
        if self.pendingExportAfterCancel:
            self.UpdateStatusBar()
        else:
            if self.currentRunIsPreview:
                self.UpdateFrameScrubber()
                if self.currentPreviewCacheIndex is not None:
                    self.LoadCachedPreviewFrame(self.currentPreviewCacheIndex)
                if self.previewCacheLimitReached:
                    limitMb = self.activeSettings.get("preview", {}).get("cacheLimitMb", self.previewCacheLimit.value()) if self.activeSettings else self.previewCacheLimit.value()
                    self.ShowWarningMessage(
                        "Preview Cache Limit",
                        f"Preview cache limit hit at {limitMb} MB. Increase the limit in Settings > System to cache more frames.",
                    )
            else:
                self.UpdateOutputViewport()
                self.UpdateRangePreview()
            self.UpdateStatusBar()

    @QtCore.Slot(str)
    def RenderFailed(self, err):
        self.pendingExportAfterCancel = False
        self.SetRunning(False)
        self.EndRenderInputSync()
        self.MarkMissingInputFilesFromError(err)
        if self.currentRunIsPreview:
            self.UpdateFrameScrubber()
            if self.currentPreviewCacheIndex is not None:
                self.LoadCachedPreviewFrame(self.currentPreviewCacheIndex)
            elif not self.previewCache:
                self.previewViewport.Clear("View generated previews here")
        else:
            self.UpdateOutputViewport()
            self.UpdateRangePreview()
        self.UpdateStatusBar()
        self.ShowErrorMessage(
            "Render Failed",
            "The render could not be completed. See the log for details.",
            self.RenderErrorSummary(err),
        )

    def RenderErrorSummary(self, err):
        lines = [line.strip() for line in str(err or "").splitlines() if line.strip()]
        if not lines:
            return None
        return "\n".join(lines[-3:])

    @QtCore.Slot()
    def ThreadFinished(self):
        if self.renderQuitDialog is not None:
            self.renderQuitDialog.close()
            self.renderQuitDialog = None
        startExport = self.pendingExportAfterCancel
        self.thread = None
        self.worker = None
        self.cancelEvent = None
        self.pauseEvent = None
        self.runActive = False
        self.activeSettings = None
        self.activeRenderEntryIds = []
        self.UpdateRunButtons()
        self.UpdatePreviewOptionsEnabled()
        self.UpdateBlendControlsEnabled()
        self.UpdateBlendResetButtons()

        if startExport:
            self.pendingExportAfterCancel = False
            self.StartExport()
        elif self.quitAfterRenderCancel:
            self.quitAfterRenderCancel = False
            self.close()

    def ShowRenderQuitDialog(self):
        if self.renderQuitDialog is not None:
            self.renderQuitDialog.raise_()
            self.renderQuitDialog.activateWindow()
            return

        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle("Stacker")
        message.setWindowIcon(StatusAssetIcon("warning"))
        message.setText("A render is currently in progess. It will be stopped if you quit now.")
        quitButton = message.addButton("Quit", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        continueButton = message.addButton("Continue", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        message.setDefaultButton(continueButton)
        message.setEscapeButton(continueButton)
        message.setIconPixmap(self.TintedAssetPixmap("warning_24dp_E3E3E3.svg", "WARNING", 48))

        def Finished(_result):
            if self.renderQuitDialog is not message:
                return
            self.renderQuitDialog = None
            if message.clickedButton() is quitButton:
                self.quitAfterRenderCancel = True
                self.CancelRender(resetUi = False)
            else:
                self.quitAfterRenderCancel = False

        message.finished.connect(Finished)
        self.renderQuitDialog = message
        message.open()

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.ShowRenderQuitDialog()
            event.ignore()
            return

        self.SaveUiConfig()
        super().closeEvent(event)
