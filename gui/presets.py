import json
import os
import re

from PySide6 import QtWidgets

from .builtin_presets import BUILTIN_PRESETS
from .resources import AppRoot


class PresetMixin:
    PRESET_RENDER_MODES = {
        0: "Gather",
        1: "Pair",
        2: "Stack",
    }
    PRESET_RENDER_PATHS = {name: path for path, name in PRESET_RENDER_MODES.items()}

    def PresetsDirectory(self):
        return os.path.join(AppRoot(), "presets")

    def PresetPath(self, presetName):
        return os.path.join(self.PresetsDirectory(), f"{presetName}.prs")

    def CleanPresetName(self, name):
        name = self.PresetDisplayName(name).strip()
        if name.lower().endswith(".prs"):
            name = name[:-4].strip()
        return name

    def IsValidPresetName(self, name):
        return bool(name) and re.fullmatch(r"[A-Za-z0-9 _-]+", name) is not None

    def PresetRenderModeName(self, path = None):
        return self.PRESET_RENDER_MODES.get(self.RenderPath() if path is None else int(path), "Gather")

    def PresetRenderPathFromData(self, data):
        return self.PRESET_RENDER_PATHS[str(data["renderMode"])]

    def BlendPresetData(self, name = None):
        renderPath = self.RenderPath()
        data = {
            "version": 1,
            "name": str(name or self.CurrentPresetName()).strip(),
            "renderMode": self.PresetRenderModeName(renderPath),
            "blend": self.blendMode.currentText(),
            "scale": self.blendScaleSpinBox.value(),
            "lift": self.blendOffsetSpinBox.value(),
            "absolute": self.absoluteValues.isChecked(),
            "intensity": self.opacity.Value(),
        }
        if renderPath == 0:
            data["spread"] = self.decay.Value()
        if renderPath == 1:
            data["shift"] = self.CurrentShift()
            data["blur"] = self.pairBlurSpinBox.value()
            data["kernel"] = self.pairBlurKernel.currentText()
        if renderPath == 2:
            data["size"] = self.stackSizeSpinBox.value()
            data["direction"] = self.stackDirection.currentText()
        return data

    def ShiftFromData(self, data):
        return int(data["shift"])

    def CurrentShift(self):
        return int(self.pairDistanceSpinBox.value())

    def BlendPresetComparableData(self, data = None):
        data = data or self.BlendPresetData()
        renderPath = self.PresetRenderPathFromData(data)
        renderMode = self.PresetRenderModeName(renderPath)
        comparable = {
            "renderMode": renderMode,
            "blend": str(data["blend"]),
            "scale": float(data["scale"]),
            "lift": float(data["lift"]),
            "absolute": bool(data["absolute"]),
            "intensity": float(data["intensity"]),
        }
        if renderPath == 0:
            comparable["spread"] = float(data["spread"])
        if renderPath == 1:
            comparable["shift"] = self.ShiftFromData(data)
            comparable["blur"] = int(data["blur"])
            comparable["kernel"] = str(data["kernel"])
        if renderPath == 2:
            comparable["size"] = int(data["size"])
            comparable["direction"] = str(data["direction"])
        return comparable

    def PresetDataMatches(self, left, right):
        if not left or not right:
            return False

        left = self.BlendPresetComparableData(left)
        right = self.BlendPresetComparableData(right)
        return (
            left["renderMode"] == right["renderMode"]
            and left["blend"] == right["blend"]
            and abs(left["scale"] - right["scale"]) <= 0.00075
            and abs(left["lift"] - right["lift"]) <= 0.00075
            and left["absolute"] == right["absolute"]
            and abs(left["intensity"] - right["intensity"]) <= 0.00075
            and (
                left["renderMode"] != "Gather"
                or abs(left["spread"] - right["spread"]) <= 0.00075
            )
            and (
                left["renderMode"] != "Pair"
                or (
                    left["shift"] == right["shift"]
                    and left["blur"] == right["blur"]
                    and left["kernel"] == right["kernel"]
                )
            )
            and (
                left["renderMode"] != "Stack"
                or (
                    left["size"] == right["size"]
                    and left["direction"] == right["direction"]
                )
            )
        )

    def PresetDisplayName(self, name, dirty = False):
        name = str(name).rstrip("*")
        return f"{name}*" if dirty else name

    def CurrentPresetName(self):
        if not hasattr(self, "presetComboBox"):
            return ""

        index = self.presetComboBox.currentIndex()
        data = self.presetComboBox.itemData(index) if index >= 0 else None
        if isinstance(data, dict) and data.get("kind") in ("builtin", "user"):
            return str(data.get("name", self.presetComboBox.itemText(index)))
        return ""

    def AddPresetHeading(self, text):
        self.presetComboBox.addItem(text, {"kind": "heading"})
        item = self.presetComboBox.model().item(self.presetComboBox.count() - 1)
        if item is not None:
            item.setEnabled(False)

    def AddPresetItem(self, name, source):
        self.presetComboBox.addItem(name, {**source, "name": name})

    def SelectedPresetIdentity(self):
        if not hasattr(self, "presetComboBox"):
            return None

        index = self.presetComboBox.currentIndex()
        data = self.presetComboBox.itemData(index) if index >= 0 else None
        if isinstance(data, dict) and data.get("kind") in ("builtin", "user"):
            return {
                "kind": data["kind"],
                "name": str(data.get("name", self.presetComboBox.itemText(index))),
            }
        return None

    def SelectPresetByIdentity(self, identity, emit = False):
        if not hasattr(self, "presetComboBox") or not isinstance(identity, dict):
            return False

        selectedKind = identity.get("kind")
        selectedName = self.PresetDisplayName(identity.get("name", ""))
        for index in range(self.presetComboBox.count()):
            data = self.presetComboBox.itemData(index)
            if (
                isinstance(data, dict)
                and data.get("kind") == selectedKind
                and self.PresetDisplayName(self.presetComboBox.itemText(index)) == selectedName
            ):
                if emit:
                    self.presetComboBox.setCurrentIndex(index)
                else:
                    self.presetComboBox.blockSignals(True)
                    self.presetComboBox.setCurrentIndex(index)
                    self.presetComboBox.blockSignals(False)
                return True

        if not emit:
            self.presetComboBox.blockSignals(True)
            self.presetComboBox.setCurrentIndex(0)
            self.presetComboBox.blockSignals(False)
        return False

    def ClearPresetDirtyIndicators(self):
        for index in range(self.presetComboBox.count()):
            data = self.presetComboBox.itemData(index)
            if not isinstance(data, dict) or data.get("kind") not in ("builtin", "user"):
                continue
            cleanName = self.PresetDisplayName(self.presetComboBox.itemText(index))
            if cleanName != self.presetComboBox.itemText(index):
                self.presetComboBox.setItemText(index, cleanName)

    def UpdatePresetDirtyIndicator(self, *args):
        if not hasattr(self, "presetComboBox"):
            return

        index = self.presetComboBox.currentIndex()
        data = self.presetComboBox.itemData(index)
        if not isinstance(data, dict) or data.get("kind") not in ("builtin", "user"):
            self.activePresetCleanData = None
            self.savePresetButton.setEnabled(True)
            self.UpdateBlendResetButtons()
            return

        baseName = self.PresetDisplayName(self.presetComboBox.itemText(index))
        dirty = not self.PresetDataMatches(self.activePresetCleanData, self.BlendPresetData())
        displayName = self.PresetDisplayName(baseName, dirty)

        if self.presetComboBox.itemText(index) != displayName:
            self.presetComboBox.setItemText(index, displayName)

        self.savePresetButton.setEnabled(dirty)
        self.UpdateBlendResetButtons()

    def ClearLoadedPreset(self):
        if not hasattr(self, "presetComboBox"):
            return

        self.ClearPresetDirtyIndicators()
        if self.presetComboBox.currentIndex() != 0:
            self.presetComboBox.blockSignals(True)
            self.presetComboBox.setCurrentIndex(0)
            self.presetComboBox.blockSignals(False)
        self.activePresetCleanData = None
        self.lastProjectPresetIdentity = self.SelectedPresetIdentity()
        self.savePresetButton.setEnabled(True)
        self.UpdateBlendResetButtons()

    def RefreshPresetList(self, selectedName = None, selectedKind = None):
        if not hasattr(self, "presetComboBox"):
            return

        selectedName = self.PresetDisplayName(selectedName or self.CurrentPresetName())
        selectedKind = selectedKind or "user"
        self.presetComboBox.blockSignals(True)
        self.presetComboBox.clear()
        self.presetComboBox.addItem("Select preset...", "")

        self.AddPresetHeading("--Built-in")
        for preset in BUILTIN_PRESETS.values():
            presetName = str(preset["name"])
            self.AddPresetItem(presetName, {"kind": "builtin", "preset": preset})

        presetsDir = self.PresetsDirectory()
        self.AddPresetHeading("--User")
        if os.path.isdir(presetsDir):
            for filename in sorted(os.listdir(presetsDir)):
                if filename.lower().endswith(".prs"):
                    path = os.path.join(presetsDir, filename)
                    try:
                        with open(path, "r", encoding = "utf-8") as presetFile:
                            preset = json.load(presetFile)
                        presetName = str(preset["name"])
                    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                        continue
                    self.AddPresetItem(presetName, {"kind": "user", "path": path})

        self.SelectPresetByIdentity({"kind": selectedKind, "name": selectedName}, emit = True)

        self.presetComboBox.blockSignals(False)
        self.UpdatePresetDirtyIndicator()

    def LoadSelectedPreset(self, index):
        self.ClearPresetDirtyIndicators()

        data = self.presetComboBox.itemData(index)
        if not isinstance(data, dict) or data.get("kind") not in ("builtin", "user"):
            self.activePresetCleanData = None
            self.savePresetButton.setEnabled(True)
            self.lastProjectPresetIdentity = self.SelectedPresetIdentity()
            self.UpdateBlendResetButtons()
            return

        try:
            if data["kind"] == "builtin":
                preset = data["preset"]
            else:
                with open(data["path"], "r", encoding = "utf-8") as presetFile:
                    preset = json.load(presetFile)
            self.activePresetCleanData = self.BlendPresetComparableData(preset)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            self.ShowErrorMessage("Preset", "Could not load the selected preset.")
            return

        startedUndoTransaction = False
        if not self.suppressProjectDirty and self.pendingUndoTransactionSnapshot is None:
            startSnapshot = self.ProjectSnapshot()
            startSnapshot.setdefault("blend", {})["preset"] = self.lastProjectPresetIdentity
            self.pendingUndoTransactionSnapshot = startSnapshot
            self.pendingUndoSection = "Blend"
            self.suppressUndoCapture = True
            startedUndoTransaction = True

        self.presetComboBox.setItemText(index, self.PresetDisplayName(self.presetComboBox.itemText(index)))

        try:
            renderPath = self.PresetRenderPathFromData(preset)
            self.SetRenderPath(renderPath)
            self._SetComboText(self.blendMode, preset["blend"])
            if renderPath == 0:
                self.decay.SetValue(float(preset["spread"]))
            if renderPath == 1:
                self.pairDistanceSpinBox.setValue(self.ShiftFromData(preset))
                self.pairBlurSpinBox.setValue(int(preset["blur"]))
                self._SetComboText(self.pairBlurKernel, preset["kernel"])
            if renderPath == 2:
                self.stackSizeSpinBox.setValue(int(preset["size"]))
                self._SetComboText(self.stackDirection, preset["direction"])
            self.blendScaleSpinBox.setValue(float(preset["scale"]))
            self.blendOffsetSpinBox.setValue(float(preset["lift"]))
            self.absoluteValues.setChecked(bool(preset["absolute"]))
            self.opacity.SetValue(float(preset["intensity"]))
            self.UpdatePresetDirtyIndicator()
        finally:
            self.lastProjectPresetIdentity = self.SelectedPresetIdentity()
            if startedUndoTransaction:
                self.EndUndoTransaction()

    def SaveBlendPreset(self):
        os.makedirs(self.PresetsDirectory(), exist_ok = True)

        currentIndex = self.presetComboBox.currentIndex()
        defaultName = ""
        currentPresetPath = None
        currentData = self.presetComboBox.itemData(currentIndex)
        if isinstance(currentData, dict) and currentData.get("kind") in ("builtin", "user"):
            defaultName = self.CleanPresetName(currentData.get("name", self.presetComboBox.itemText(currentIndex)))
            currentPresetPath = currentData.get("path")

        presetName, accepted = QtWidgets.QInputDialog.getText(
            self,
            "Save Blend Preset",
            "Enter preset name:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            defaultName,
        )
        if not accepted:
            return

        presetName = self.CleanPresetName(presetName)
        if not self.IsValidPresetName(presetName):
            self.ShowWarningMessage(
                "Preset",
                "Preset names can only use letters, numbers, spaces, underscores, and hyphens.",
            )
            return

        path = self.PresetPath(presetName)
        if os.path.exists(path) and os.path.normcase(path) != os.path.normcase(currentPresetPath or ""):
            response = self.ShowWarningMessage(
                "Preset",
                f'Replace existing preset "{presetName}"?',
                standardButtons = QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                defaultButton = QtWidgets.QMessageBox.StandardButton.No,
            )
            if response != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        try:
            with open(path, "w", encoding = "utf-8") as presetFile:
                json.dump(self.BlendPresetData(presetName), presetFile, indent = 2)
        except OSError:
            self.ShowErrorMessage("Preset", "Could not save the preset.")
            return

        self.activePresetCleanData = self.BlendPresetComparableData()
        self.RefreshPresetList(presetName, selectedKind = "user")
        self.UpdateBlendResetButtons()
