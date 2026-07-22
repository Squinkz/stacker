import json
import os
import ctypes

from PySide6 import QtCore, QtWidgets

from .config import CONFIG_FILENAME
from .file_list import ENTRY_ID_ROLE
from .resources import AppRoot, ThemeColor, ThemeDisplayName, ThemeName
from render.renderer import TransferFunctionNames


class ProjectMixin:
    def ConfigPath(self):
        return os.path.join(AppRoot(), CONFIG_FILENAME)

    def _SetComboText(self, comboBox, text):
        if text is None:
            return

        index = comboBox.findText(str(text))
        if index >= 0:
            comboBox.setCurrentIndex(index)

    def _SetComboData(self, comboBox, data):
        for index in range(comboBox.count()):
            if comboBox.itemData(index) == data:
                comboBox.setCurrentIndex(index)
                return

    def _AddTransferFunctionItems(self, comboBox):
        for name in TransferFunctionNames():
            comboBox.addItem(name, name)

    def _TransferFunctionValue(self, comboBox):
        return comboBox.currentData() or comboBox.currentText()

    def _SetTransferFunctionValue(self, comboBox, value):
        if value is None:
            return

        value = str(value)
        if value.startswith("Unknown"):
            value = "sRGB / Display P3"
        if value not in TransferFunctionNames() and "(" in value:
            value = value.split("(", 1)[0].strip()
        self._SetComboData(comboBox, value)

    def _TransferFunctionFromMetadata(self, metadata):
        transfer = metadata.get("transfer", "sRGB / Display P3")
        return "sRGB / Display P3" if str(transfer).startswith("Unknown") else transfer

    def RenderPath(self):
        if not hasattr(self, "renderPathGroup"):
            return 0

        checkedId = self.renderPathGroup.checkedId()
        return checkedId if checkedId in (0, 1, 2) else 0

    def SetRenderPath(self, path):
        if not hasattr(self, "renderPathGroup"):
            return

        try:
            path = int(path)
        except (TypeError, ValueError):
            path = 0
        path = max(0, min(2, path))
        button = self.renderPathGroup.button(path)
        if button:
            button.setChecked(True)
        self.UpdateRenderPathControls()

    def UpdateRenderPathControls(self, *_):
        if not hasattr(self, "stackSizeField"):
            return

        self.UpdateStackSizeMaximum()
        renderPath = self.RenderPath()
        pairVisible = renderPath == 1
        stackVisible = renderPath == 2
        decayVisible = renderPath == 0
        self.pairDistanceLabel.setVisible(pairVisible)
        self.pairDistanceField.setVisible(pairVisible)
        self.pairDistanceField.setEnabled((not self.runActive) and pairVisible)
        self.pairBlurLabel.setVisible(pairVisible)
        self.pairBlurField.setVisible(pairVisible)
        self.pairBlurField.setEnabled((not self.runActive) and pairVisible)
        self.pairKernelLabel.setVisible(pairVisible)
        self.pairBlurKernel.setVisible(pairVisible)
        self.pairBlurKernel.setEnabled((not self.runActive) and pairVisible)
        self.stackSizeLabel.setVisible(stackVisible)
        self.stackSizeField.setVisible(stackVisible)
        self.stackSizeField.setEnabled((not self.runActive) and stackVisible)
        if hasattr(self, "stackMemoryLabel"):
            self.stackMemoryField.setVisible(stackVisible)
            self.stackMemorySpacer.setVisible(stackVisible)
        self.stackDirectionLabel.setVisible(stackVisible)
        self.stackDirection.setVisible(stackVisible)
        self.stackDirection.setEnabled((not self.runActive) and stackVisible)
        self.UpdateStackMemoryEstimate()
        self.UpdateStackSizeWarning()
        self.decayLabel.setVisible(decayVisible)
        self.decayField.setVisible(decayVisible)
        self.UpdateBlendControlsEnabled()
        self.UpdateBlendResetButtons()

    def BlendResetTarget(self, key):
        preset = self.activePresetCleanData if isinstance(getattr(self, "activePresetCleanData", None), dict) else {}
        renderMode = preset.get("renderMode")
        if key in ("scale", "lift", "intensity") and key in preset:
            return preset[key]
        if key == "spread" and renderMode == "Gather" and "spread" in preset:
            return preset["spread"]
        if key == "shift" and renderMode == "Pair" and "shift" in preset:
            return preset["shift"]
        if key == "blur" and renderMode == "Pair" and "blur" in preset:
            return preset["blur"]
        if key == "size" and renderMode == "Stack" and "size" in preset:
            return preset["size"]

        if key == "size":
            return min(10, self.EffectiveStackSizeMaximum())

        defaults = {
            "spread": 1.0,
            "shift": -1,
            "blur": 0,
            "scale": 1.0,
            "lift": 0.0,
            "intensity": 1.0,
        }
        return defaults[key]

    def ResetBlendControl(self, key):
        if self.runActive:
            return

        value = self.BlendResetTarget(key)
        if key == "spread":
            self.decay.SetValue(float(value))
        elif key == "shift":
            self.pairDistanceSpinBox.setValue(int(value))
        elif key == "blur":
            self.pairBlurSpinBox.setValue(int(value))
        elif key == "size":
            self.stackSizeSpinBox.setValue(int(value))
        elif key == "scale":
            self.blendScaleSpinBox.setValue(float(value))
        elif key == "lift":
            self.blendOffsetSpinBox.setValue(float(value))
        elif key == "intensity":
            self.opacity.SetValue(float(value))
        self.UpdateBlendResetButtons()

    def BlendControlValue(self, key):
        if key == "spread":
            return self.decay.Value()
        if key == "shift":
            return self.pairDistanceSpinBox.value()
        if key == "blur":
            return self.pairBlurSpinBox.value()
        if key == "size":
            return self.stackSizeSpinBox.value()
        if key == "scale":
            return self.blendScaleSpinBox.value()
        if key == "lift":
            return self.blendOffsetSpinBox.value()
        if key == "intensity":
            return self.opacity.Value()
        return 0

    def UpdateBlendResetButtons(self, *_):
        if not hasattr(self, "blendResetButtons"):
            return

        for key, button in self.blendResetButtons.items():
            field = button.parentWidget()
            if field is not None and field.isHidden():
                button.setEnabled(False)
                continue

            current = float(self.BlendControlValue(key))
            target = float(self.BlendResetTarget(key))
            button.setEnabled((not self.runActive) and abs(current - target) > 0.0005)

    def EffectiveStackSizeMaximum(self):
        if not getattr(self, "inputPreviewFilenames", None) or not hasattr(self, "rangeField"):
            return 1

        return max(1, len(self.InputReadIndices()))

    def EffectivePairDistanceMaximum(self):
        return max(1, self.EffectiveStackSizeMaximum() - 1)

    def UpdatePairDistanceMaximum(self):
        if not hasattr(self, "pairDistanceSpinBox"):
            return

        maximum = self.EffectivePairDistanceMaximum()
        currentValue = max(-maximum, min(self.pairDistanceSpinBox.value(), maximum))
        self.pairDistanceSpinBox.setMinimum(-maximum)
        self.pairDistanceSpinBox.setMaximum(maximum)
        if self.pairDistanceSpinBox.value() != currentValue:
            self.pairDistanceSpinBox.setValue(currentValue)

        sliderMaximum = min(20, maximum)
        sliderMinimum = -sliderMaximum
        self.pairDistanceSlider.setMinimum(sliderMinimum)
        self.pairDistanceSlider.setMaximum(sliderMaximum)
        self.pairDistanceSlider.blockSignals(True)
        self.pairDistanceSlider.setValue(max(sliderMinimum, min(currentValue, sliderMaximum)))
        self.pairDistanceSlider.blockSignals(False)

    def UpdateStackSizeMaximum(self):
        if not hasattr(self, "stackSizeSpinBox"):
            return

        self.UpdatePairDistanceMaximum()
        maximum = self.EffectiveStackSizeMaximum()
        currentValue = min(self.stackSizeSpinBox.value(), maximum)
        self.stackSizeSpinBox.setMaximum(maximum)
        if self.stackSizeSpinBox.value() != currentValue:
            self.stackSizeSpinBox.setValue(currentValue)

        sliderMaximum = max(1, min(20, maximum))
        self.stackSizeSlider.setMaximum(sliderMaximum)
        self.stackSizeSlider.blockSignals(True)
        self.stackSizeSlider.setValue(min(currentValue, sliderMaximum))
        self.stackSizeSlider.blockSignals(False)
        self.UpdateStackMemoryEstimate()
        self.UpdateStackSizeWarning()
        self.UpdateBlendResetButtons()

    def StackSizeSpinBoxChanged(self, value):
        if not hasattr(self, "stackSizeSlider"):
            return

        sliderValue = min(int(value), self.stackSizeSlider.maximum())
        self.stackSizeSlider.blockSignals(True)
        self.stackSizeSlider.setValue(sliderValue)
        self.stackSizeSlider.blockSignals(False)
        self.UpdateStackMemoryEstimate()
        self.UpdateStackSizeWarning()

    def AvailableSystemMemoryBytes(self):
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except (AttributeError, OSError):
            pass
        return None

    def UpdateStackMemoryEstimate(self):
        if not hasattr(self, "stackMemoryLabel"):
            return

        self.stackMemoryExceeded = False
        if hasattr(self, "stackMemoryIcon"):
            self.stackMemoryIcon.hide()
        if hasattr(self, "stackMemoryDetailLabel"):
            self.stackMemoryDetailLabel.hide()
            self.stackMemoryDetailLabel.setText("")

        filenames = self.InputReadFilenames() if hasattr(self, "InputReadFilenames") else []
        if not filenames:
            self.stackMemoryLabel.setText("Memory Required: --")
            self.stackMemoryLabel.setStyleSheet(f"font-style: italic; color: {ThemeColor('TEXT')};")
            if hasattr(self, "UpdateRunButtons"):
                self.UpdateRunButtons()
            return

        dimensions = self.CachedImageDimensions(filenames[0])
        if not dimensions:
            self.stackMemoryLabel.setText("Memory Required: --")
            self.stackMemoryLabel.setStyleSheet(f"font-style: italic; color: {ThemeColor('TEXT')};")
            if hasattr(self, "UpdateRunButtons"):
                self.UpdateRunButtons()
            return

        width, height = dimensions
        stackSize = max(1, int(self.stackSizeSpinBox.value()))
        byteCount = int(width) * int(height) * 3 * 4 * stackSize
        availableBytes = self.AvailableSystemMemoryBytes()
        colorKey = "TEXT"
        detailText = ""
        iconName = None
        if availableBytes:
            if byteCount > availableBytes:
                colorKey = "ERROR"
                iconName = "error_24dp_E3E3E3.svg"
                detailText = f"Exceeds available RAM: {self.FormatByteSize(availableBytes)}"
                self.stackMemoryExceeded = self.RenderPath() == 2
            elif byteCount > availableBytes * 0.7:
                colorKey = "WARNING"
                iconName = "warning_24dp_E3E3E3.svg"
                detailText = f"High usage; available RAM: {self.FormatByteSize(availableBytes)}"

        if hasattr(self, "stackMemoryIcon"):
            self.stackMemoryIcon.setVisible(bool(iconName))
            if iconName:
                self.stackMemoryIcon.setPixmap(self.TintedAssetPixmap(iconName, colorKey, 18))

        self.stackMemoryLabel.setText(f"Memory Required: {self.FormatByteSize(byteCount)}")
        self.stackMemoryLabel.setStyleSheet(f"font-style: italic; color: {ThemeColor(colorKey)};")
        if hasattr(self, "stackMemoryDetailLabel"):
            self.stackMemoryDetailLabel.setText(detailText)
            self.stackMemoryDetailLabel.setVisible(bool(detailText))
            self.stackMemoryDetailLabel.setStyleSheet(f"font-style: italic; color: {ThemeColor(colorKey)};")
        if hasattr(self, "UpdateRunButtons"):
            self.UpdateRunButtons()

    def PairDistanceSpinBoxChanged(self, value):
        if not hasattr(self, "pairDistanceSlider"):
            return

        value = int(value)
        sliderValue = max(self.pairDistanceSlider.minimum(), min(value, self.pairDistanceSlider.maximum()))
        self.pairDistanceSlider.blockSignals(True)
        self.pairDistanceSlider.setValue(sliderValue)
        self.pairDistanceSlider.blockSignals(False)

    def PairBlurSpinBoxChanged(self, value):
        if not hasattr(self, "pairBlurSlider"):
            return

        value = int(value)
        sliderValue = max(self.pairBlurSlider.minimum(), min(value, self.pairBlurSlider.maximum()))
        self.pairBlurSlider.blockSignals(True)
        self.pairBlurSlider.setValue(sliderValue)
        self.pairBlurSlider.blockSignals(False)

    def BlendScaleSliderChanged(self, value):
        if not hasattr(self, "blendScaleSpinBox"):
            return

        self.blendScaleSpinBox.blockSignals(True)
        self.blendScaleSpinBox.setValue(float(value) / 1000.0)
        self.blendScaleSpinBox.blockSignals(False)
        self.blendScaleSpinBox.valueChanged.emit(self.blendScaleSpinBox.value())

    def BlendScaleSpinBoxChanged(self, value):
        if not hasattr(self, "blendScaleSlider"):
            return

        sliderValue = max(self.blendScaleSlider.minimum(), min(round(float(value) * 1000), self.blendScaleSlider.maximum()))
        self.blendScaleSlider.blockSignals(True)
        self.blendScaleSlider.setValue(sliderValue)
        self.blendScaleSlider.blockSignals(False)

    def BlendOffsetSliderChanged(self, value):
        if not hasattr(self, "blendOffsetSpinBox"):
            return

        self.blendOffsetSpinBox.blockSignals(True)
        self.blendOffsetSpinBox.setValue(float(value) / 1000.0)
        self.blendOffsetSpinBox.blockSignals(False)
        self.blendOffsetSpinBox.valueChanged.emit(self.blendOffsetSpinBox.value())

    def BlendOffsetSpinBoxChanged(self, value):
        if not hasattr(self, "blendOffsetSlider"):
            return

        sliderValue = max(self.blendOffsetSlider.minimum(), min(round(float(value) * 1000), self.blendOffsetSlider.maximum()))
        self.blendOffsetSlider.blockSignals(True)
        self.blendOffsetSlider.setValue(sliderValue)
        self.blendOffsetSlider.blockSignals(False)

    def UpdateStackSizeWarning(self):
        if not hasattr(self, "stackSizeWarningLabel"):
            return

        visible = (
            self.RenderPath() == 2
            and self.stackSizeSpinBox.value() > self.stackSizeSlider.maximum()
        )
        self.stackSizeWarningField.setVisible(visible)
        self.stackSizeWarningSpacer.setVisible(visible)

    def _UiConfig(self):
        rangeStart, rangeStop = self.rangeField.Values()
        return {
            "version": 1,
            "layout": {
                "sidebarWidth": self.CurrentSidebarWidth(),
            },
            "project": {
                "path": self.currentProjectPath,
                "dirty": self.projectDirty,
            },
            "paths": {
                "lastInputBrowseFolder": self.lastInputBrowserDirectory,
            },
            "appearance": {
                "theme": ThemeName(),
                "viewportBackground": self.viewportBackgroundOverride,
            },
            "viewportOverlay": {
                "showDimensions": self.overlayShowDimensions,
                "showColorSpace": self.overlayShowColorSpace,
                "showCoordinates": self.overlayShowCoordinates,
                "showZoom": self.overlayShowZoom,
                "showFrameIndex": self.overlayShowFrameIndex,
                "showImageIndex": self.overlayShowImageIndex,
            },
            "input": {
                "files": [
                    ({
                        "path": entry["filename"],
                        "enabled": entry["id"] not in self.disabledInputFilenames,
                    } | ({
                        "transferOverrideEnabled": bool(entry.get("transferOverrideEnabled", False)),
                        "transferFunction": entry.get("transferFunction", "sRGB / Display P3"),
                    } if entry.get("transferOverrideEnabled", False) or entry.get("transferFunction") else {}))
                    for entry in self.inputFileEntries
                ],
                "rangeStart": rangeStart,
                "rangeStop": rangeStop,
                "skip": self.skipInput.value(),
            },
            "blend": {
                "preset": self.SelectedPresetIdentity(),
                "renderMode": self.PresetRenderModeName(),
                "blend": self.blendMode.currentText(),
                "spread": self.decay.Value(),
                "scale": self.blendScaleSpinBox.value(),
                "lift": self.blendOffsetSpinBox.value(),
                "absolute": self.absoluteValues.isChecked(),
                "intensity": self.opacity.Value(),
                "size": self.stackSizeSpinBox.value(),
                "direction": self.stackDirection.currentText(),
                "shift": self.CurrentShift(),
                "blur": self.pairBlurSpinBox.value(),
                "kernel": self.pairBlurKernel.currentText(),
            },
            "output": {
                "directory": self.outputDirectory.Text(),
                "type": self.outputFileType.currentText(),
                "name": self.outputFileName.text(),
                "skip": self.skipOutput.value(),
                "exportMode": self.exportMode,
            },
            "preview": {
                "enabled": self.previewEnabled.isChecked(),
                "scale": self.previewScale.currentData(),
                "fps": self.previewFps.value(),
                "playbackFps": self.playbackFps.value(),
                "frameCount": self.previewFrameCount,
                "cacheLimitMb": self.previewCacheLimit.value(),
            },
            "outputOptions": {
                "jpg": {
                    "quality": self.jpgQuality.value(),
                    "optimize": self.jpgOptimize.isChecked(),
                    "progressive": self.jpgProgressive.isChecked(),
                    "subsampling": self.jpgSubsampling.currentData(),
                },
                "png": {
                    "compression": self.pngCompressLevel.value(),
                    "optimize": self.pngOptimize.isChecked(),
                },
                "tiff": {
                    "compression": self.tiffCompression.currentData(),
                },
            },
            "transferOverrides": {
                "inputEnabled": self.overrideInputTransfer.isChecked(),
                "inputFunction": self._TransferFunctionValue(self.inputTransferFunction),
                "outputEnabled": self.overrideOutputTransfer.isChecked(),
                "outputFunction": self._TransferFunctionValue(self.outputTransferFunction),
                "blendInLinear": self.blendInLinear.isChecked(),
                "customMiddleGrayEnabled": self.useCustomMiddleGray.isChecked(),
                "middleGray": self.middleGray.Value(),
                "viewportScaling": self.viewportScaling.currentText(),
                "resizeFilter": self.resizeFilter.currentText(),
                "resolutionEnabled": self.overrideResolution.isChecked(),
                "width": self.overrideWidth.value(),
                "height": self.overrideHeight.value(),
            },
        }

    def CurrentSidebarWidth(self):
        if hasattr(self, "mainSplitter"):
            sizes = self.mainSplitter.sizes()
            if len(sizes) >= 2 and sizes[1] > 0:
                return sizes[1]
        return getattr(self, "defaultSidebarWidth", 480)

    def RestoreSidebarWidth(self, width):
        if not hasattr(self, "mainSplitter"):
            return

        self.UpdateSidebarWidthLimits()

        try:
            sidebarWidth = int(width)
        except (TypeError, ValueError):
            return

        sidebar = self.mainSplitter.widget(1)
        sidebarWidth = max(sidebar.minimumWidth(), sidebarWidth)
        maximumWidth = max(self.sidebarMinimumWidth, round(self.WindowContentWidth() * self.sidebarMaximumRatio))
        sidebarWidth = min(maximumWidth, sidebarWidth)

        totalWidth = max(self.mainSplitter.width(), sum(self.mainSplitter.sizes()), 1200)
        self.mainSplitter.setSizes([max(160, totalWidth - sidebarWidth), sidebarWidth])

    def SaveUiConfig(self):
        try:
            with open(self.ConfigPath(), "w", encoding = "utf-8") as configFile:
                json.dump(self._UiConfig(), configFile, indent = 2)
        except OSError:
            pass

    def _ProjectConfig(self):
        uiConfig = self._UiConfig()
        outputConfig = dict(uiConfig.get("output", {}))
        outputConfig["previewWhileExporting"] = self.previewEnabled.isChecked()
        transferConfig = uiConfig.get("transferOverrides", {})
        previewConfig = dict(uiConfig.get("preview", {}))
        previewConfig.pop("playbackFps", None)

        return {
            "version": 1,
            "type": "stackerProject",
            "input": uiConfig.get("input", {}),
            "blend": uiConfig.get("blend", {}),
            "output": outputConfig,
            "preview": previewConfig,
            "outputOptions": uiConfig.get("outputOptions", {}),
            "transferOverrides": {
                "inputEnabled": transferConfig.get("inputEnabled", False),
                "inputFunction": transferConfig.get("inputFunction"),
                "outputEnabled": transferConfig.get("outputEnabled", False),
                "outputFunction": transferConfig.get("outputFunction"),
                "blendInLinear": transferConfig.get("blendInLinear", True),
                "customMiddleGrayEnabled": transferConfig.get("customMiddleGrayEnabled", False),
                "middleGray": transferConfig.get("middleGray", 0.5),
                "resizeFilter": transferConfig.get("resizeFilter", self.resizeFilter.currentText()),
                "resolutionEnabled": transferConfig.get("resolutionEnabled", False),
                "width": transferConfig.get("width", self.overrideWidth.value()),
                "height": transferConfig.get("height", self.overrideHeight.value()),
            },
        }

    def ProjectFileFilter(self):
        return "Stacker Project (*.stack)"

    def ProjectBrowserStartDirectory(self):
        if self.currentProjectPath:
            return os.path.dirname(self.currentProjectPath)
        return AppRoot()

    def NormalizeProjectPath(self, path):
        path = str(path or "").strip()
        if not path:
            return ""
        if not path.lower().endswith(".stack"):
            path += ".stack"
        return os.path.normpath(path)

    def SaveProject(self):
        if self.currentProjectPath:
            return self.SaveProjectToPath(self.currentProjectPath)
        return self.SaveProjectAs()

    def ConfirmSaveUnsavedProject(self):
        if not self.projectDirty:
            return True

        projectName = (
            os.path.splitext(os.path.basename(self.currentProjectPath))[0]
            if self.currentProjectPath else
            "New Project"
        )
        result = self.ShowWarningMessage(
            "Unsaved Project",
            f"Save changes to {projectName} before continuing?",
            standardButtons = (
                QtWidgets.QMessageBox.StandardButton.Save
                | QtWidgets.QMessageBox.StandardButton.Discard
                | QtWidgets.QMessageBox.StandardButton.Cancel
            ),
            defaultButton = QtWidgets.QMessageBox.StandardButton.Save,
        )
        if result == QtWidgets.QMessageBox.StandardButton.Save:
            return bool(self.SaveProject())
        if result == QtWidgets.QMessageBox.StandardButton.Discard:
            return True
        return False

    def CloseProject(self):
        if not self.ConfirmSaveUnsavedProject():
            return False

        self.suppressProjectDirty = True
        self.suppressUndoCapture = True
        try:
            self.ApplyProjectConfig(self.DefaultProjectConfig())
        finally:
            self.suppressUndoCapture = False
            self.suppressProjectDirty = False
        self.SetCurrentProjectPath(None)
        self.SetProjectDirty(False)
        self.ResetUndoHistory(clean = True)
        return True

    def SaveProjectAs(self):
        filename, _selectedFilter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Project",
            self.ProjectBrowserStartDirectory(),
            self.ProjectFileFilter(),
        )
        filename = self.NormalizeProjectPath(filename)
        if filename:
            return self.SaveProjectToPath(filename)
        return False

    def SaveProjectToPath(self, filename):
        filename = self.NormalizeProjectPath(filename)
        if not filename:
            return False

        try:
            with open(filename, "w", encoding = "utf-8") as projectFile:
                json.dump(self._ProjectConfig(), projectFile, indent = 2)
        except OSError as error:
            self.ShowErrorMessage("Save Project", f"Could not save project:\n\n{error}")
            return False

        self.SetCurrentProjectPath(filename)
        self.SetProjectDirty(False)
        self.MarkProjectSnapshotClean()
        return True

    def OpenProjectFile(self):
        if not self.ConfirmSaveUnsavedProject():
            return False

        filename, _selectedFilter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Project",
            self.ProjectBrowserStartDirectory(),
            self.ProjectFileFilter(),
        )
        filename = self.NormalizeProjectPath(filename)
        if filename:
            return self.LoadProjectFromPath(filename)
        return False

    def LoadProjectFromPath(self, filename):
        filename = self.NormalizeProjectPath(filename)
        try:
            with open(filename, "r", encoding = "utf-8") as projectFile:
                config = json.load(projectFile)
        except (OSError, json.JSONDecodeError) as error:
            self.ShowErrorMessage("Open Project", f"Could not open project:\n\n{error}")
            return False

        if not isinstance(config, dict):
            self.ShowErrorMessage("Open Project", "The selected file is not a valid Stacker project.")
            return False

        self.suppressProjectDirty = True
        self.suppressUndoCapture = True
        try:
            self.ApplyProjectConfig(config)
        finally:
            self.suppressUndoCapture = False
            self.suppressProjectDirty = False
        self.SetCurrentProjectPath(filename)
        self.SetProjectDirty(False)
        self.ResetUndoHistory(clean = True)
        return True

    def SetCurrentProjectPath(self, filename):
        self.currentProjectPath = self.NormalizeProjectPath(filename) if filename else None
        self.UpdateProjectTitle()

    def SetProjectDirty(self, dirty):
        self.projectDirty = bool(dirty)
        self.UpdateProjectTitle()

    def MarkProjectDirty(self, *args, section = None):
        if self.suppressProjectDirty:
            return
        if self.pendingUndoTransactionSnapshot is not None:
            self.SetProjectDirty(True)
            return
        self.CaptureUndoState(section = section)
        self.UpdateProjectDirtyFromSnapshot()

    def ProjectSnapshot(self):
        return json.loads(json.dumps(self._ProjectConfig(), sort_keys = True))

    def ProjectSnapshotKey(self, snapshot):
        return json.dumps(snapshot, sort_keys = True, separators = (",", ":"))

    def SidebarSectionName(self):
        if not hasattr(self, "sidebarTabs"):
            return None

        index = self.sidebarTabs.currentIndex()
        return self.sidebarTabs.tabText(index) if index >= 0 else None

    def FocusSidebarSection(self, section):
        if not section or not hasattr(self, "sidebarTabs"):
            return

        for index in range(self.sidebarTabs.count()):
            if self.sidebarTabs.tabText(index) == section:
                self.sidebarTabs.setCurrentIndex(index)
                return

    def RegisterUndoSection(self, snapshot, section):
        section = section or self.pendingUndoSection or self.SidebarSectionName()
        if section:
            self.undoSectionBySnapshotKey[self.ProjectSnapshotKey(snapshot)] = section

    def ResetUndoHistory(self, clean = False):
        snapshot = self.ProjectSnapshot()
        self.undoStack = [snapshot]
        self.redoStack = []
        self.lastProjectSnapshot = snapshot
        self.undoSectionBySnapshotKey = {}
        self.cleanProjectSnapshot = snapshot if clean else None
        self.lastProjectPresetIdentity = self.SelectedPresetIdentity()

    def MarkProjectSnapshotClean(self):
        self.cleanProjectSnapshot = self.ProjectSnapshot()
        self.lastProjectSnapshot = self.cleanProjectSnapshot
        self.UpdateProjectDirtyFromSnapshot()

    def UpdateProjectDirtyFromSnapshot(self):
        if self.cleanProjectSnapshot is None:
            self.SetProjectDirty(True)
        else:
            self.SetProjectDirty(self.ProjectSnapshot() != self.cleanProjectSnapshot)

    def CaptureUndoState(self, section = None):
        if self.suppressUndoCapture:
            return

        snapshot = self.ProjectSnapshot()
        previousSnapshot = self.lastProjectSnapshot
        if previousSnapshot is not None and previousSnapshot != snapshot:
            if not self.undoStack or self.undoStack[-1] != previousSnapshot:
                self.undoStack.append(previousSnapshot)
            if not self.undoStack or self.undoStack[-1] != snapshot:
                self.undoStack.append(snapshot)
                self.RegisterUndoSection(snapshot, section)
            if len(self.undoStack) > self.undoStackLimit:
                self.undoStack = self.undoStack[-self.undoStackLimit:]
            self.redoStack = []
            self.lastProjectSnapshot = snapshot
            return

        if self.undoStack and snapshot == self.undoStack[-1]:
            self.lastProjectSnapshot = snapshot
            return

        self.undoStack.append(snapshot)
        self.RegisterUndoSection(snapshot, section)
        if len(self.undoStack) > self.undoStackLimit:
            self.undoStack = self.undoStack[-self.undoStackLimit:]
        self.redoStack = []
        self.lastProjectSnapshot = snapshot

    def BeginUndoTransaction(self, *args, section = None):
        if self.suppressProjectDirty or self.pendingUndoTransactionSnapshot is not None:
            return

        self.pendingUndoTransactionSnapshot = self.ProjectSnapshot()
        self.pendingUndoSection = section or self.SidebarSectionName()
        self.suppressUndoCapture = True

    def EndUndoTransaction(self, *args):
        startSnapshot = self.pendingUndoTransactionSnapshot
        if startSnapshot is None:
            return

        section = self.pendingUndoSection
        self.pendingUndoTransactionSnapshot = None
        self.pendingUndoSection = None
        self.suppressUndoCapture = False
        endSnapshot = self.ProjectSnapshot()
        if endSnapshot == startSnapshot:
            self.lastProjectSnapshot = endSnapshot
            self.UpdateProjectDirtyFromSnapshot()
            return

        if not self.undoStack or self.undoStack[-1] != startSnapshot:
            self.undoStack.append(startSnapshot)
        if not self.undoStack or self.undoStack[-1] != endSnapshot:
            self.undoStack.append(endSnapshot)
            self.RegisterUndoSection(endSnapshot, section)
        if len(self.undoStack) > self.undoStackLimit:
            self.undoStack = self.undoStack[-self.undoStackLimit:]
        self.redoStack = []
        self.lastProjectSnapshot = endSnapshot
        self.UpdateProjectDirtyFromSnapshot()

    def ProjectTransientUiState(self):
        selectionEntryIds = set()
        selectionFileKeys = []
        currentEntryId = None
        currentFileKey = None
        fileScroll = None
        if hasattr(self, "inputFileList"):
            selection = self.inputFileList.selectionModel()
            if selection:
                selectionEntryIds = {
                    index.data(ENTRY_ID_ROLE)
                    for index in selection.selectedRows()
                    if index.data(ENTRY_ID_ROLE) is not None
                }
                selectionFileKeys = [
                    self.InputFileOccurrenceKeyForRow(index.row())
                    for index in selection.selectedRows()
                    if self.InputFileOccurrenceKeyForRow(index.row()) is not None
                ]
            current = self.inputFileList.currentIndex()
            currentEntryId = current.data(ENTRY_ID_ROLE) if current.isValid() else None
            currentFileKey = self.InputFileOccurrenceKeyForRow(current.row()) if current.isValid() else None
            fileScroll = self.inputFileList.verticalScrollBar().value()

        scrubberState = None
        if hasattr(self, "frameScrubber"):
            scrubberState = {
                "value": self.frameScrubber.value,
                "viewStart": self.frameScrubber.viewStart,
                "viewEnd": self.frameScrubber.viewEnd,
            }

        return {
            "selectionEntryIds": selectionEntryIds,
            "selectionFileKeys": selectionFileKeys,
            "currentEntryId": currentEntryId,
            "currentFileKey": currentFileKey,
            "fileScroll": fileScroll,
            "scrubber": scrubberState,
        }

    def RestoreProjectTransientUiState(self, state):
        if not state:
            return

        if hasattr(self, "inputFileList") and hasattr(self, "inputFileModel"):
            selectionEntryIds = self.EntryIdsForInputFileOccurrenceKeys(state.get("selectionFileKeys") or [])
            if not selectionEntryIds:
                selectionEntryIds = state.get("selectionEntryIds") or set()
            if selectionEntryIds:
                self.RestoreInputFileSelection(selectionEntryIds)
            currentEntryIds = self.EntryIdsForInputFileOccurrenceKeys([state.get("currentFileKey")])
            currentEntryId = next(iter(currentEntryIds), None) if currentEntryIds else state.get("currentEntryId")
            currentRow = self.inputFileModel.RowForEntryId(currentEntryId) if currentEntryId is not None else None
            if currentRow is not None:
                self.suppressInputFileSelectionSync = True
                try:
                    selection = self.inputFileList.selectionModel()
                    if selection:
                        selection.setCurrentIndex(
                            self.inputFileModel.index(currentRow, 0),
                            QtCore.QItemSelectionModel.SelectionFlag.NoUpdate,
                        )
                finally:
                    self.suppressInputFileSelectionSync = False
            if state.get("fileScroll") is not None:
                self.inputFileList.verticalScrollBar().setValue(int(state["fileScroll"]))

        scrubberState = state.get("scrubber")
        if scrubberState and hasattr(self, "frameScrubber"):
            self.frameScrubber.SetValue(scrubberState.get("value", self.frameScrubber.value), emit = False)
            maxFrame = float(max(0, self.frameScrubber.frameCount - 1))
            viewStart = max(0.0, min(maxFrame, float(scrubberState.get("viewStart", self.frameScrubber.viewStart))))
            viewEnd = max(0.0, min(maxFrame, float(scrubberState.get("viewEnd", self.frameScrubber.viewEnd))))
            if viewEnd <= viewStart:
                viewEnd = min(maxFrame, viewStart + self.frameScrubber.MinimumVisibleSpan())
            self.frameScrubber.viewStart = viewStart
            self.frameScrubber.viewEnd = viewEnd
            self.frameScrubber.update()

    def ApplyUndoRedoSnapshot(self, snapshot):
        transientState = self.ProjectTransientUiState()
        changedSections = self.ChangedProjectSections(self.ProjectSnapshot(), snapshot)
        self.suppressProjectDirty = True
        self.suppressUndoCapture = True
        try:
            self.ApplyProjectConfig(snapshot, sections = changedSections, focusFirstInput = False)
        finally:
            self.suppressUndoCapture = False
            self.suppressProjectDirty = False
        self.RestoreProjectTransientUiState(transientState)
        self.lastProjectPresetIdentity = self.SelectedPresetIdentity()
        self.lastProjectSnapshot = snapshot
        self.UpdateProjectDirtyFromSnapshot()

    def ChangedProjectSections(self, currentSnapshot, targetSnapshot):
        sections = set()
        for section in ("input", "blend", "output", "outputOptions", "transferOverrides"):
            if currentSnapshot.get(section) != targetSnapshot.get(section):
                sections.add(section)
        return sections

    def UndoProjectAction(self):
        if self.runActive:
            return

        currentSnapshot = self.ProjectSnapshot()
        if not self.undoStack or currentSnapshot != self.undoStack[-1]:
            self.undoStack.append(currentSnapshot)
            if len(self.undoStack) > self.undoStackLimit:
                self.undoStack = self.undoStack[-self.undoStackLimit:]

        if len(self.undoStack) <= 1:
            return

        undoneSnapshot = self.undoStack.pop()
        self.redoStack.append(undoneSnapshot)
        self.FocusSidebarSection(self.undoSectionBySnapshotKey.get(self.ProjectSnapshotKey(undoneSnapshot)))
        self.ApplyUndoRedoSnapshot(self.undoStack[-1])

    def RedoProjectAction(self):
        if self.runActive or not self.redoStack:
            return

        snapshot = self.redoStack.pop()
        self.undoStack.append(snapshot)
        if len(self.undoStack) > self.undoStackLimit:
            self.undoStack = self.undoStack[-self.undoStackLimit:]
        self.FocusSidebarSection(self.undoSectionBySnapshotKey.get(self.ProjectSnapshotKey(snapshot)))
        self.ApplyUndoRedoSnapshot(snapshot)

    def UpdateProjectTitle(self):
        projectName = (
            os.path.splitext(os.path.basename(self.currentProjectPath))[0]
            if self.currentProjectPath else
            "New Project"
        )
        dirtyMark = "*" if self.projectDirty else ""
        title = f"{projectName}{dirtyMark} - Stacker"
        self.setWindowTitle(title)

    def DefaultProjectConfig(self):
        return {
            "version": 1,
            "type": "stackerProject",
            "input": {
                "files": [],
                "rangeStart": 0,
                "rangeStop": 0,
                "skip": 1,
            },
            "blend": {
                "preset": None,
                "renderMode": "Gather",
                "blend": "Max (Lighten)",
                "spread": 1.0,
                "scale": 1.0,
                "lift": 0.0,
                "absolute": False,
                "intensity": 1.0,
                "size": 10,
                "direction": "Past",
                "shift": -1,
                "blur": 0,
                "kernel": "Gaussian",
            },
            "output": {
                "directory": "",
                "type": "jpg",
                "name": "frame",
                "skip": 1,
                "exportMode": "sequence",
                "previewWhileExporting": True,
            },
            "outputOptions": {
                "jpg": {
                    "quality": 95,
                    "optimize": False,
                    "progressive": False,
                    "subsampling": None,
                },
                "png": {
                    "compression": 6,
                    "optimize": False,
                },
                "tiff": {
                    "compression": None,
                },
            },
            "transferOverrides": {
                "inputEnabled": False,
                "inputFunction": "sRGB / Display P3",
                "outputEnabled": False,
                "outputFunction": "sRGB / Display P3",
                "blendInLinear": True,
                "customMiddleGrayEnabled": False,
                "middleGray": 0.5,
                "resizeFilter": "Lanczos",
                "resolutionEnabled": False,
                "width": 1920,
                "height": 1080,
            },
        }

    def ApplyProjectConfig(self, config, sections = None, focusFirstInput = True):
        allSections = sections is None
        sections = set(("input", "blend", "output", "outputOptions", "transferOverrides") if sections is None else sections)
        applyInput = "input" in sections
        applyBlend = "blend" in sections
        applyOutput = "output" in sections
        applyOutputOptions = "outputOptions" in sections
        applyTransfer = "transferOverrides" in sections
        inputConfig = config.get("input", {})
        outputConfig = config.get("output", {})
        blendConfig = config.get("blend", {})
        outputOptionsConfig = config.get("outputOptions", {})
        transferOverridesConfig = config.get("transferOverrides", {})

        if applyInput:
            currentInputConfig = self._ProjectConfig().get("input", {})
            targetFiles = inputConfig.get("files", [])
            pathsChanged = self.ProjectInputFilePaths(currentInputConfig.get("files", [])) != self.ProjectInputFilePaths(targetFiles)
            if pathsChanged:
                self.RestoreInputFileEntries(inputConfig.get("files", []), refresh = False)
            else:
                self.ApplyInputEnabledState(targetFiles)
            self.skipInput.setValue(int(inputConfig.get("skip", self.skipInput.value())))
            if "rangeStart" in inputConfig or "rangeStop" in inputConfig:
                self.rangeField.SetValues(
                    int(inputConfig.get("rangeStart", self.rangeField.Values()[0])),
                    int(inputConfig.get("rangeStop", self.rangeField.Values()[1])),
                )

        if applyOutput:
            self.outputDirectory.lineEdit.setText(str(outputConfig.get("directory", self.outputDirectory.Text())))
            self._SetComboText(self.outputFileType, outputConfig.get("type"))
            self.outputFileName.setText(str(outputConfig.get("name", self.outputFileName.text())))
            self.skipOutput.setValue(int(outputConfig.get("skip", self.skipOutput.value())))
            self.SetExportMode(outputConfig.get("exportMode", self.exportMode))
            if "previewWhileExporting" in outputConfig:
                self.previewEnabled.setChecked(bool(outputConfig.get("previewWhileExporting")))

        if applyBlend:
            self._SetComboText(self.blendMode, blendConfig.get("blend"))
            self.SetRenderPath(self.PresetRenderPathFromData(blendConfig))
            self.pairDistanceSpinBox.setValue(self.ShiftFromData(blendConfig))
            self.pairBlurSpinBox.setValue(int(blendConfig.get("blur", self.pairBlurSpinBox.value())))
            self._SetComboText(self.pairBlurKernel, blendConfig.get("kernel", self.pairBlurKernel.currentText()))
            self.stackSizeSpinBox.setValue(int(blendConfig.get("size", self.stackSizeSpinBox.value())))
            self._SetComboText(self.stackDirection, blendConfig.get("direction", self.stackDirection.currentText()))
            self.decay.SetValue(float(blendConfig.get("spread", self.decay.Value())))
            self.blendScaleSpinBox.setValue(float(blendConfig.get("scale", self.blendScaleSpinBox.value())))
            self.blendOffsetSpinBox.setValue(float(blendConfig.get("lift", self.blendOffsetSpinBox.value())))
            self.absoluteValues.setChecked(bool(blendConfig.get("absolute", self.absoluteValues.isChecked())))
            self.opacity.SetValue(float(blendConfig.get("intensity", self.opacity.Value())))
            if self.SelectPresetByIdentity(blendConfig.get("preset")):
                data = self.presetComboBox.itemData(self.presetComboBox.currentIndex())
                try:
                    if data["kind"] == "builtin":
                        self.activePresetCleanData = self.BlendPresetComparableData(data["preset"])
                    else:
                        with open(data["path"], "r", encoding = "utf-8") as presetFile:
                            self.activePresetCleanData = self.BlendPresetComparableData(json.load(presetFile))
                except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                    self.activePresetCleanData = None
                self.UpdatePresetDirtyIndicator()
            else:
                self.presetComboBox.blockSignals(True)
                self.presetComboBox.setCurrentIndex(0)
                self.presetComboBox.blockSignals(False)
                self.activePresetCleanData = None
                self.UpdatePresetDirtyIndicator()
            self.UpdateBlendControlsEnabled()

        if applyTransfer:
            self.overrideInputTransfer.setChecked(bool(transferOverridesConfig.get("inputEnabled", self.overrideInputTransfer.isChecked())))
            self._SetTransferFunctionValue(self.inputTransferFunction, transferOverridesConfig.get("inputFunction"))
            self.overrideOutputTransfer.setChecked(bool(transferOverridesConfig.get("outputEnabled", self.overrideOutputTransfer.isChecked())))
            self._SetTransferFunctionValue(self.outputTransferFunction, transferOverridesConfig.get("outputFunction"))
            self.blendInLinear.setChecked(bool(transferOverridesConfig.get("blendInLinear", self.blendInLinear.isChecked())))
            self.useCustomMiddleGray.setChecked(bool(transferOverridesConfig.get("customMiddleGrayEnabled", self.useCustomMiddleGray.isChecked())))
            self.middleGray.SetValue(float(transferOverridesConfig.get("middleGray", self.middleGray.Value())))
            self._SetComboText(self.resizeFilter, transferOverridesConfig.get("resizeFilter"))
            self.overrideResolution.setChecked(bool(transferOverridesConfig.get("resolutionEnabled", self.overrideResolution.isChecked())))
            self.overrideWidth.setValue(int(transferOverridesConfig.get("width", self.overrideWidth.value())))
            self.overrideHeight.setValue(int(transferOverridesConfig.get("height", self.overrideHeight.value())))
            self.UpdateTransferOverrideControls()
            self.UpdateMiddleGrayControls()

        if applyOutputOptions:
            jpgConfig = outputOptionsConfig.get("jpg", {})
            self.jpgQuality.setValue(int(jpgConfig.get("quality", self.jpgQuality.value())))
            self.jpgOptimize.setChecked(bool(jpgConfig.get("optimize", self.jpgOptimize.isChecked())))
            self.jpgProgressive.setChecked(bool(jpgConfig.get("progressive", self.jpgProgressive.isChecked())))
            self._SetComboData(self.jpgSubsampling, jpgConfig.get("subsampling", self.jpgSubsampling.currentData()))

            pngConfig = outputOptionsConfig.get("png", {})
            self.pngCompressLevel.setValue(int(pngConfig.get("compression", self.pngCompressLevel.value())))
            self.pngOptimize.setChecked(bool(pngConfig.get("optimize", self.pngOptimize.isChecked())))

            tiffConfig = outputOptionsConfig.get("tiff", {})
            self._SetComboData(self.tiffCompression, tiffConfig.get("compression", self.tiffCompression.currentData()))
            self.UpdateOutputOptionsPanel()

        if applyInput or allSections:
            self.ClearPreviewCache()
            self.RefreshMissingInputFiles()
            self.RefreshInputFileState()
            if focusFirstInput:
                self.FocusFirstActiveInputFile()
        elif applyTransfer:
            self.RefreshInputDimensionWarnings()
            self.RefreshInputPreviewMetadata()
            self.UpdateEffectiveOverrideValues()
            self.UpdateStackSizeMaximum()

        self.UpdateViewportInfoVisibility()
        self.UpdatePreviewOverlay()
        outputTabActive = hasattr(self, "viewportTabs") and self.viewportTabs.currentIndex() == 2
        if (applyOutput or applyOutputOptions or allSections) and (outputTabActive or allSections):
            self.UpdateOutputViewport()

    def ProjectInputFilePaths(self, files):
        paths = []
        for item in files if isinstance(files, list) else []:
            if isinstance(item, dict):
                filename = str(item.get("path", "")).strip()
            else:
                filename = str(item).strip()
            paths.append(os.path.normpath(filename) if filename else "")
        return paths

    def ApplyInputEnabledState(self, files):
        disabledIds = set()
        for index, item in enumerate(files if isinstance(files, list) else []):
            if index >= len(self.inputFileEntries):
                break
            isItemDict = isinstance(item, dict)
            enabled = bool(item.get("enabled", True)) if isItemDict else True
            if isItemDict:
                self.inputFileEntries[index]["transferOverrideEnabled"] = bool(item.get("transferOverrideEnabled", False))
                if item.get("transferFunction"):
                    self.inputFileEntries[index]["transferFunction"] = str(item.get("transferFunction"))
            if not enabled:
                disabledIds.add(self.inputFileEntries[index]["id"])
        self.disabledInputFilenames = disabledIds

    def LoadUiConfig(self):
        try:
            with open(self.ConfigPath(), "r", encoding = "utf-8") as configFile:
                config = json.load(configFile)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(config, dict):
            return

        inputConfig = config.get("input", {})
        projectConfig = config.get("project", {})
        pathsConfig = config.get("paths", {})
        layoutConfig = config.get("layout", {})
        appearanceConfig = config.get("appearance", {})
        overlayConfig = config.get("viewportOverlay", {})
        outputConfig = config.get("output", {})
        blendConfig = config.get("blend", {})
        previewConfig = config.get("preview", {})
        outputOptionsConfig = config.get("outputOptions", {})
        transferOverridesConfig = config.get("transferOverrides", {})

        self.lastInputBrowserDirectory = str(pathsConfig.get("lastInputBrowseFolder", ""))
        if not os.path.isdir(self.lastInputBrowserDirectory):
            self.lastInputBrowserDirectory = ""
        self.inputDirectory.SetStartPath(self.lastInputBrowserDirectory)
        loadedTheme = ThemeDisplayName(appearanceConfig.get("theme", ThemeName()))
        self._SetComboText(self.themeSelector, loadedTheme)
        self.SetTheme(self.themeSelector.currentText())
        viewportBackground = appearanceConfig.get("viewportBackground", None)
        if viewportBackground is None:
            self.viewportBackgroundOverride = None
        else:
            try:
                self.viewportBackgroundOverride = max(0, min(255, int(viewportBackground)))
            except (TypeError, ValueError):
                self.viewportBackgroundOverride = None
        self.SyncViewportBackgroundControls()
        self.ApplyViewportBackground()
        self.overlayShowDimensions = bool(overlayConfig.get("showDimensions", self.overlayShowDimensions))
        self.overlayShowColorSpace = bool(overlayConfig.get("showColorSpace", self.overlayShowColorSpace))
        self.overlayShowCoordinates = bool(overlayConfig.get("showCoordinates", self.overlayShowCoordinates))
        self.overlayShowZoom = bool(overlayConfig.get("showZoom", self.overlayShowZoom))
        self.overlayShowFrameIndex = bool(overlayConfig.get("showFrameIndex", self.overlayShowFrameIndex))
        self.overlayShowImageIndex = bool(overlayConfig.get("showImageIndex", self.overlayShowImageIndex))

        self.outputDirectory.lineEdit.setText(str(outputConfig.get("directory", self.outputDirectory.Text())))
        self._SetComboText(self.outputFileType, outputConfig.get("type"))
        self.outputFileName.setText(str(outputConfig.get("name", self.outputFileName.text())))
        self.skipOutput.setValue(int(outputConfig.get("skip", self.skipOutput.value())))
        self.SetExportMode(outputConfig.get("exportMode", self.exportMode))

        self.skipInput.setValue(int(inputConfig.get("skip", self.skipInput.value())))

        self._SetComboText(self.blendMode, blendConfig.get("blend"))
        self.SetRenderPath(self.PresetRenderPathFromData(blendConfig))
        self.pairDistanceSpinBox.setValue(self.ShiftFromData(blendConfig))
        self.pairBlurSpinBox.setValue(int(blendConfig.get("blur", self.pairBlurSpinBox.value())))
        self._SetComboText(self.pairBlurKernel, blendConfig.get("kernel", self.pairBlurKernel.currentText()))
        self.stackSizeSpinBox.setValue(int(blendConfig.get("size", self.stackSizeSpinBox.value())))
        self._SetComboText(self.stackDirection, blendConfig.get("direction", self.stackDirection.currentText()))
        self.decay.SetValue(float(blendConfig.get("spread", self.decay.Value())))
        self.blendScaleSpinBox.setValue(float(blendConfig.get("scale", self.blendScaleSpinBox.value())))
        self.blendOffsetSpinBox.setValue(float(blendConfig.get("lift", self.blendOffsetSpinBox.value())))
        self.absoluteValues.setChecked(bool(blendConfig.get("absolute", self.absoluteValues.isChecked())))
        self.opacity.SetValue(float(blendConfig.get("intensity", self.opacity.Value())))
        self.UpdateBlendControlsEnabled()
        if self.SelectPresetByIdentity(blendConfig.get("preset")):
            data = self.presetComboBox.itemData(self.presetComboBox.currentIndex())
            try:
                if data["kind"] == "builtin":
                    self.activePresetCleanData = self.BlendPresetComparableData(data["preset"])
                else:
                    with open(data["path"], "r", encoding = "utf-8") as presetFile:
                        self.activePresetCleanData = self.BlendPresetComparableData(json.load(presetFile))
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                self.activePresetCleanData = None
            self.UpdatePresetDirtyIndicator()

        self.previewEnabled.setChecked(bool(previewConfig.get("enabled", self.previewEnabled.isChecked())))
        self._SetComboData(self.previewScale, previewConfig.get("scale", self.previewScale.currentData()))
        self.previewFps.setValue(float(previewConfig.get("fps", self.previewFps.value())))
        self.playbackFps.setValue(int(previewConfig.get("playbackFps", self.playbackFps.value())))
        self.UpdateScrubberPlaybackInterval()
        self.SetPreviewFrameCount(previewConfig.get("frameCount", self.previewFrameCount))
        self.previewCacheLimit.setValue(int(previewConfig.get("cacheLimitMb", self.previewCacheLimit.value())))
        self.UpdatePreviewOptionsEnabled()

        self.overrideInputTransfer.setChecked(bool(transferOverridesConfig.get("inputEnabled", self.overrideInputTransfer.isChecked())))
        self._SetTransferFunctionValue(self.inputTransferFunction, transferOverridesConfig.get("inputFunction"))
        self.overrideOutputTransfer.setChecked(bool(transferOverridesConfig.get("outputEnabled", self.overrideOutputTransfer.isChecked())))
        self._SetTransferFunctionValue(self.outputTransferFunction, transferOverridesConfig.get("outputFunction"))
        self.blendInLinear.setChecked(bool(transferOverridesConfig.get("blendInLinear", self.blendInLinear.isChecked())))
        self.useCustomMiddleGray.setChecked(bool(transferOverridesConfig.get("customMiddleGrayEnabled", self.useCustomMiddleGray.isChecked())))
        self.middleGray.SetValue(float(transferOverridesConfig.get("middleGray", self.middleGray.Value())))
        self._SetComboText(self.viewportScaling, transferOverridesConfig.get("viewportScaling"))
        self._SetComboText(self.resizeFilter, transferOverridesConfig.get("resizeFilter"))
        self.overrideResolution.setChecked(bool(transferOverridesConfig.get("resolutionEnabled", self.overrideResolution.isChecked())))
        self.overrideWidth.setValue(int(transferOverridesConfig.get("width", self.overrideWidth.value())))
        self.overrideHeight.setValue(int(transferOverridesConfig.get("height", self.overrideHeight.value())))
        self.UpdateTransferOverrideControls()
        self.UpdateMiddleGrayControls()
        self.UpdateViewportScaling()

        jpgConfig = outputOptionsConfig.get("jpg", {})
        self.jpgQuality.setValue(int(jpgConfig.get("quality", self.jpgQuality.value())))
        self.jpgOptimize.setChecked(bool(jpgConfig.get("optimize", self.jpgOptimize.isChecked())))
        self.jpgProgressive.setChecked(bool(jpgConfig.get("progressive", self.jpgProgressive.isChecked())))
        self._SetComboData(self.jpgSubsampling, jpgConfig.get("subsampling", self.jpgSubsampling.currentData()))

        pngConfig = outputOptionsConfig.get("png", {})
        self.pngCompressLevel.setValue(int(pngConfig.get("compression", self.pngCompressLevel.value())))
        self.pngOptimize.setChecked(bool(pngConfig.get("optimize", self.pngOptimize.isChecked())))

        tiffConfig = outputOptionsConfig.get("tiff", {})
        self._SetComboData(self.tiffCompression, tiffConfig.get("compression", self.tiffCompression.currentData()))
        self.UpdateOutputOptionsPanel()

        self.RestoreInputFileEntries(inputConfig.get("files", []))
        if "rangeStart" in inputConfig or "rangeStop" in inputConfig:
            self.rangeField.SetValues(
                int(inputConfig.get("rangeStart", self.rangeField.Values()[0])),
                int(inputConfig.get("rangeStop", self.rangeField.Values()[1])),
            )
        self.RefreshMissingInputFiles()
        self.FocusFirstActiveInputFile()
        self.RestoreSidebarWidth(layoutConfig.get("sidebarWidth"))
        self.UpdateViewportInfoVisibility()
        self.UpdatePreviewOverlay()
        projectPath = self.NormalizeProjectPath(projectConfig.get("path", ""))
        self.currentProjectPath = projectPath if projectPath else None
        self.projectDirty = bool(projectConfig.get("dirty", False))
        self.UpdateProjectTitle()
