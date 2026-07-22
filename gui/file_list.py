import os

from PySide6 import QtCore, QtGui, QtWidgets

from .resources import AssetIcon, ThemeQColor

FILENAME_ROLE = QtCore.Qt.ItemDataRole.UserRole
DISPLAY_INDEX_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
ACTIVE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2
MANUALLY_ENABLED_ROLE = QtCore.Qt.ItemDataRole.UserRole + 3
ENTRY_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 4
MISSING_ROLE = QtCore.Qt.ItemDataRole.UserRole + 5
RESCALE_WARNING_ROLE = QtCore.Qt.ItemDataRole.UserRole + 6
REORDER_VISIBLE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 7
PENDING_REMOVE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 8
TRANSFER_WARNING_ROLE = QtCore.Qt.ItemDataRole.UserRole + 9
CURRENT_PREVIEW_ROLE = QtCore.Qt.ItemDataRole.UserRole + 10

class InputFileListModel(QtCore.QAbstractListModel):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.rows = []
        self.pendingRemoveEntryIds = set()

    def SetRows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent = QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None

        row = self.rows[index.row()]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return row.get("displayText", "")
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return row.get("tooltip", "")
        if role == FILENAME_ROLE:
            return row.get("filename")
        if role == DISPLAY_INDEX_ROLE:
            return row.get("displayIndex")
        if role == ACTIVE_ROLE:
            return row.get("isActive", False)
        if role == MANUALLY_ENABLED_ROLE:
            return row.get("isManuallyEnabled", False)
        if role == ENTRY_ID_ROLE:
            return row.get("entryId")
        if role == MISSING_ROLE:
            return row.get("isMissing", False)
        if role == RESCALE_WARNING_ROLE:
            return row.get("isRescaleWarning", False)
        if role == TRANSFER_WARNING_ROLE:
            return row.get("isTransferWarning", False)
        if role == CURRENT_PREVIEW_ROLE:
            return row.get("isCurrentPreview", False)
        if role == REORDER_VISIBLE_ROLE:
            return row.get("showReorder", True)
        if role == PENDING_REMOVE_ROLE:
            return row.get("entryId") in self.pendingRemoveEntryIds
        return None

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        return (
            QtCore.Qt.ItemFlag.ItemIsEnabled
            | QtCore.Qt.ItemFlag.ItemIsSelectable
        )

    def EntryIdAt(self, row):
        if 0 <= row < len(self.rows):
            return self.rows[row].get("entryId")
        return None

    def FilenameAt(self, row):
        if 0 <= row < len(self.rows):
            return self.rows[row].get("filename")
        return None

    def RowForEntryId(self, entryId):
        for row, data in enumerate(self.rows):
            if data.get("entryId") == entryId:
                return row
        return None

    def SetPendingRemoveEntryIds(self, entryIds):
        newEntryIds = set(entryIds or [])
        if newEntryIds == self.pendingRemoveEntryIds:
            return
        self.pendingRemoveEntryIds = newEntryIds
        if self.rows:
            topLeft = self.index(0, 0)
            bottomRight = self.index(len(self.rows) - 1, 0)
            self.dataChanged.emit(topLeft, bottomRight, [PENDING_REMOVE_ROLE])

    def SetCurrentPreviewEntryId(self, entryId):
        changed = False
        for row in self.rows:
            isCurrent = row.get("entryId") == entryId if entryId is not None else False
            if row.get("isCurrentPreview", False) != isCurrent:
                row["isCurrentPreview"] = isCurrent
                changed = True
        if changed and self.rows:
            topLeft = self.index(0, 0)
            bottomRight = self.index(len(self.rows) - 1, 0)
            self.dataChanged.emit(topLeft, bottomRight, [CURRENT_PREVIEW_ROLE])

    def SetTransferWarnings(self, warningEntryIds, entryIds = None):
        warningEntryIds = set(warningEntryIds or set())
        targetEntryIds = set(entryIds or [])
        changedRows = []
        for row, data in enumerate(self.rows):
            entryId = data.get("entryId")
            if targetEntryIds and entryId not in targetEntryIds:
                continue
            isWarning = entryId in warningEntryIds
            if data.get("isTransferWarning", False) != isWarning:
                data["isTransferWarning"] = isWarning
                changedRows.append(row)

        for row in changedRows:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [TRANSFER_WARNING_ROLE])

class InputFileListView(QtWidgets.QListView):
    reorderRequested = QtCore.Signal(list, int)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.reorderEnabled = True
        self._reorderPressPos = None
        self._reorderPressRow = None
        self._reorderEntryIds = []
        self._draggingReorder = False
        self._dropRow = None
        self._lastDropRow = None
        self._dropIndicatorRect = QtCore.QRect()
        self._autoScrollMargin = 36
        self._autoScrollStep = 3
        self._autoScrollPosition = QtCore.QPoint()
        self._autoScrollTimer = QtCore.QTimer(self)
        self._autoScrollTimer.setInterval(35)
        self._autoScrollTimer.timeout.connect(self._AutoScrollReorder)

    def SetReorderEnabled(self, enabled):
        self.reorderEnabled = bool(enabled)
        if not self.reorderEnabled:
            self._ClearReorderDrag()
        self.viewport().update()

    def ReorderIconRect(self, row):
        index = self.model().index(row, 0) if self.model() is not None else QtCore.QModelIndex()
        rect = self.visualRect(index)
        iconSize = 18
        return QtCore.QRect(
            rect.left() + 8,
            rect.top() + ((rect.height() - iconSize) // 2),
            iconSize,
            iconSize,
        )

    def VisibilityIconRect(self, row):
        index = self.model().index(row, 0) if self.model() is not None else QtCore.QModelIndex()
        rect = self.visualRect(index)
        iconSize = 18
        iconMargin = 8
        return QtCore.QRect(
            rect.right() - iconMargin - iconSize,
            rect.top() + ((rect.height() - iconSize) // 2),
            iconSize,
            iconSize,
        )

    def SideIconRect(self, row, slot):
        index = self.model().index(row, 0) if self.model() is not None else QtCore.QModelIndex()
        rect = self.visualRect(index)
        iconSize = 18
        iconMargin = 8
        return QtCore.QRect(
            rect.right() - (iconMargin * (slot + 2)) - (iconSize * (slot + 2)),
            rect.top() + ((rect.height() - iconSize) // 2),
            iconSize,
            iconSize,
        )

    def WarningIconRect(self, row):
        index = self.model().index(row, 0) if self.model() is not None else QtCore.QModelIndex()
        slot = 1 if bool(index.data(MISSING_ROLE)) else 0
        return self.SideIconRect(row, slot)

    def ErrorIconRect(self, row):
        return self.SideIconRect(row, 0)

    def TextRect(self, row):
        index = self.model().index(row, 0) if self.model() is not None else QtCore.QModelIndex()
        rect = self.visualRect(index)
        iconSize = 18
        iconMargin = 8
        sideIconCount = int(bool(index.data(RESCALE_WARNING_ROLE) or index.data(TRANSFER_WARNING_ROLE))) + int(bool(index.data(MISSING_ROLE)))
        rightReserved = iconSize + (iconMargin * 2)
        if sideIconCount:
            rightReserved += (iconSize + iconMargin) * sideIconCount
        return rect.adjusted(8 + iconSize + 22, 0, -rightReserved, 0)

    def FrameNumberRect(self, row):
        index = self.model().index(row, 0) if self.model() is not None else QtCore.QModelIndex()
        textRect = self.TextRect(row)
        metrics = QtGui.QFontMetrics(self.font())
        frameNumber = (index.data(QtCore.Qt.ItemDataRole.DisplayRole) or "").partition("\t")[0]
        digitWidth = max(4, len(frameNumber))
        return QtCore.QRect(
            textRect.left(),
            textRect.top(),
            metrics.horizontalAdvance("0" * digitWidth),
            textRect.height(),
        )

    def FilenameRect(self, row):
        index = self.model().index(row, 0) if self.model() is not None else QtCore.QModelIndex()
        textRect = self.TextRect(row)
        metrics = QtGui.QFontMetrics(self.font())
        frameNumber = (index.data(QtCore.Qt.ItemDataRole.DisplayRole) or "").partition("\t")[0]
        digitWidth = max(4, len(frameNumber))
        return textRect.adjusted(metrics.horizontalAdvance("0" * digitWidth) + 22, 0, 0, 0)

    def viewportEvent(self, event):
        if event.type() == QtCore.QEvent.Type.ToolTip:
            position = event.pos() if hasattr(event, "pos") else event.position().toPoint()
            globalPosition = event.globalPos() if hasattr(event, "globalPos") else event.globalPosition().toPoint()
            index = self.indexAt(position)
            if not index.isValid():
                QtWidgets.QToolTip.hideText()
                return True

            row = index.row()
            tooltip = ""
            if bool(index.data(REORDER_VISIBLE_ROLE)) and self.ReorderIconRect(row).contains(position):
                tooltip = "Drag to reorder"
            elif bool(index.data(RESCALE_WARNING_ROLE) or index.data(TRANSFER_WARNING_ROLE)) and self.WarningIconRect(row).contains(position):
                tooltipLines = []
                if bool(index.data(RESCALE_WARNING_ROLE)):
                    tooltipLines.append("Image will be scaled to export dimensions")
                if bool(index.data(TRANSFER_WARNING_ROLE)):
                    tooltipLines.append("Unknown transfer function: sRGB assumed")
                tooltip = "\n".join(tooltipLines)
            elif bool(index.data(MISSING_ROLE)) and self.ErrorIconRect(row).contains(position):
                tooltip = "File not found"
            elif self.VisibilityIconRect(row).contains(position):
                tooltip = "Disable" if bool(index.data(MANUALLY_ENABLED_ROLE)) else "Enable"
            elif self.FrameNumberRect(row).contains(position):
                frameNumber = (index.data(QtCore.Qt.ItemDataRole.DisplayRole) or "").partition("\t")[0]
                tooltip = f"Frame number: {frameNumber}" if frameNumber else "Frame number"
            elif self.FilenameRect(row).contains(position):
                tooltip = os.path.normpath(index.data(FILENAME_ROLE) or "")

            if tooltip:
                QtWidgets.QToolTip.showText(globalPosition, tooltip, self.viewport())
            else:
                QtWidgets.QToolTip.hideText()
            return True

        return super().viewportEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.reorderEnabled:
            index = self.indexAt(event.position().toPoint())
            if (
                index.isValid()
                and bool(index.data(REORDER_VISIBLE_ROLE))
                and self.ReorderIconRect(index.row()).contains(event.position().toPoint())
            ):
                selection = self.selectionModel()
                selectedRows = sorted(rowIndex.row() for rowIndex in selection.selectedRows()) if selection else []
                if selection is not None and not selection.isSelected(index):
                    selection.clearSelection()
                    selection.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows)
                    selection.setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
                    selectedRows = [index.row()]
                self._reorderEntryIds = [
                    self.model().data(self.model().index(row, 0), ENTRY_ID_ROLE)
                    for row in selectedRows
                    if self.model().data(self.model().index(row, 0), ENTRY_ID_ROLE) is not None
                ]
                self._reorderPressPos = event.position().toPoint()
                self._reorderPressRow = index.row()
                self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._reorderPressPos is not None and self._reorderEntryIds:
            distance = (event.position().toPoint() - self._reorderPressPos).manhattanLength()
            if distance >= QtWidgets.QApplication.startDragDistance():
                self._draggingReorder = True
            self._autoScrollPosition = event.position().toPoint()
            self._UpdateReorderDropIndicator(self._autoScrollPosition)
            self._UpdateReorderAutoScroll()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def _UpdateReorderDropIndicator(self, position):
        dropRow = self.DropTargetRow(position)
        if dropRow != self._lastDropRow:
            oldRect = QtCore.QRect(self._dropIndicatorRect)
            self._dropRow = dropRow
            self._lastDropRow = dropRow
            self._dropIndicatorRect = self.DropIndicatorRect(dropRow)
            updateRect = oldRect.united(self._dropIndicatorRect).adjusted(-2, -3, 2, 3)
            self.viewport().update(updateRect)

    def _UpdateReorderAutoScroll(self):
        if self._draggingReorder and self._AutoScrollDirection(self._autoScrollPosition) != 0:
            if not self._autoScrollTimer.isActive():
                self._autoScrollTimer.start()
        elif self._autoScrollTimer.isActive():
            self._autoScrollTimer.stop()

    def _AutoScrollDirection(self, position):
        viewportHeight = self.viewport().height()
        if position.y() < self._autoScrollMargin:
            return -1
        if position.y() > viewportHeight - self._autoScrollMargin:
            return 1
        return 0

    def _AutoScrollReorder(self):
        if not self._draggingReorder or self._reorderPressPos is None:
            self._autoScrollTimer.stop()
            return

        direction = self._AutoScrollDirection(self._autoScrollPosition)
        if direction == 0:
            self._autoScrollTimer.stop()
            return

        scrollbar = self.verticalScrollBar()
        oldValue = scrollbar.value()
        scrollbar.setValue(oldValue + (direction * self._autoScrollStep))
        if scrollbar.value() == oldValue:
            return

        self._UpdateReorderDropIndicator(self._autoScrollPosition)
        self.viewport().update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._reorderPressPos is not None:
            entryIds = list(self._reorderEntryIds)
            targetRow = self._dropRow
            shouldReorder = self._draggingReorder and bool(entryIds)
            if targetRow is None:
                targetRow = self.DropTargetRow(event.position().toPoint())
            self._ClearReorderDrag()
            if shouldReorder:
                self.reorderRequested.emit(entryIds, targetRow)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def selectionCommand(self, index, event = None):
        if self._reorderPressPos is not None:
            return QtCore.QItemSelectionModel.SelectionFlag.NoUpdate
        if (
            event is not None
            and event.type() in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonRelease)
            and hasattr(event, "button")
            and event.button() == QtCore.Qt.MouseButton.LeftButton
            and index.isValid()
            and self.VisibilityIconRect(index.row()).contains(event.position().toPoint())
        ):
            return QtCore.QItemSelectionModel.SelectionFlag.NoUpdate
        return super().selectionCommand(index, event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._draggingReorder or self._dropIndicatorRect.isNull():
            return

        painter = QtGui.QPainter(self.viewport())
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        pen = QtGui.QPen(ThemeQColor("TEXT"), 2)
        painter.setPen(pen)
        y = self._dropIndicatorRect.center().y()
        painter.drawLine(self._dropIndicatorRect.left(), y, self._dropIndicatorRect.right(), y)

    def DropTargetRow(self, position):
        model = self.model()
        rowCount = model.rowCount() if model is not None else 0
        if rowCount <= 0:
            return 0

        if position.y() < 0:
            return 0
        if position.y() > self.viewport().height():
            return rowCount

        index = self.indexAt(position)
        if not index.isValid():
            return 0 if position.y() < 0 else rowCount

        rect = self.visualRect(index)
        return index.row() if position.y() < rect.center().y() else index.row() + 1

    def DropIndicatorRect(self, row):
        model = self.model()
        rowCount = model.rowCount() if model is not None else 0
        if rowCount <= 0:
            return QtCore.QRect(8, 0, max(0, self.viewport().width() - 16), 3)

        if row >= rowCount:
            rect = self.visualRect(model.index(rowCount - 1, 0))
            y = rect.bottom() + 1
        else:
            rect = self.visualRect(model.index(max(0, row), 0))
            y = rect.top()
        return QtCore.QRect(8, y - 1, max(0, self.viewport().width() - 16), 3)

    def _ClearReorderDrag(self):
        self._reorderPressPos = None
        self._reorderPressRow = None
        self._reorderEntryIds = []
        self._draggingReorder = False
        self._dropRow = None
        self._lastDropRow = None
        self._autoScrollTimer.stop()
        oldRect = QtCore.QRect(self._dropIndicatorRect)
        self._dropIndicatorRect = QtCore.QRect()
        self.unsetCursor()
        if not oldRect.isNull():
            self.viewport().update(oldRect.adjusted(-2, -3, 2, 3))

class InputFileListDelegate(QtWidgets.QStyledItemDelegate):
    toggleRequested = QtCore.Signal(int)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.RefreshIcons()

    def RefreshIcons(self):
        self.reorderIcon = AssetIcon("reorder_24dp_E3E3E3.svg")
        self.visibleIcon = AssetIcon("visibility_24dp_E3E3E3.svg")
        self.hiddenIcon = AssetIcon("visibility_off_24dp_E3E3E3.svg")
        self.warningIcon = AssetIcon("warning_24dp_E3E3E3.svg")
        self.errorIcon = AssetIcon("error_24dp_E3E3E3.svg")

    def TintedIconPixmap(self, icon, color, size):
        pixmap = icon.pixmap(size, size)
        tinted = QtGui.QPixmap(pixmap.size())
        tinted.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(tinted)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        return tinted

    def paint(self, painter, option, index):
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = index.data(QtCore.Qt.ItemDataRole.DisplayRole) or ""
        opt.text = ""

        widget = opt.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()
        style.drawPrimitive(QtWidgets.QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)

        isActive = bool(index.data(ACTIVE_ROLE))
        isManuallyEnabled = bool(index.data(MANUALLY_ENABLED_ROLE))
        isMissing = bool(index.data(MISSING_ROLE))
        isRescaleWarning = bool(index.data(RESCALE_WARNING_ROLE))
        isTransferWarning = bool(index.data(TRANSFER_WARNING_ROLE))
        hasWarning = isRescaleWarning or isTransferWarning
        showReorder = bool(index.data(REORDER_VISIBLE_ROLE))
        isPendingRemove = bool(index.data(PENDING_REMOVE_ROLE))
        isCurrentPreview = bool(index.data(CURRENT_PREVIEW_ROLE))
        isSelected = bool(opt.state & QtWidgets.QStyle.StateFlag.State_Selected)
        isHovered = bool(opt.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        if isCurrentPreview and not isSelected:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            previewRect = opt.rect.adjusted(2, 2, -2, -2)
            painter.setPen(QtGui.QPen(ThemeQColor("TEXT_MUTED"), 1))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(previewRect, 3, 3)
            painter.restore()

        if isPendingRemove:
            textColor = ThemeQColor("ERROR")
        elif isMissing:
            textColor = ThemeQColor("ERROR")
        elif isSelected and not isActive:
            textColor = ThemeQColor("TEXT_MUTED")
        else:
            textColor = ThemeQColor("SELECTION_TEXT" if isSelected else ("TEXT" if isActive else "TEXT_DISABLED"))

        painter.save()
        painter.setPen(textColor)
        font = opt.font
        painter.setFont(font)

        iconSize = 18
        iconMargin = 8
        iconRect = self.IconRect(opt)
        warningIconRect = self.SideIconRect(opt, 1 if isMissing else 0)
        errorIconRect = self.SideIconRect(opt, 0)
        prefixIconRect = QtCore.QRect(
            opt.rect.left() + 8,
            opt.rect.top() + ((opt.rect.height() - iconSize) // 2),
            iconSize,
            iconSize,
        )
        rightReserved = iconSize + (iconMargin * 2)
        sideIconCount = int(hasWarning) + int(isMissing)
        if sideIconCount:
            rightReserved += (iconSize + iconMargin) * sideIconCount
        textRect = opt.rect.adjusted(8 + iconSize + 22, 0, -rightReserved, 0)
        if showReorder:
            if isPendingRemove:
                painter.drawPixmap(prefixIconRect, self.TintedIconPixmap(self.reorderIcon, ThemeQColor("ERROR"), iconSize))
            elif isHovered:
                self.reorderIcon.paint(painter, prefixIconRect)
            elif isSelected:
                painter.drawPixmap(prefixIconRect, self.TintedIconPixmap(self.reorderIcon, ThemeQColor("TEXT_MUTED"), iconSize))
            else:
                painter.drawPixmap(prefixIconRect, self.TintedIconPixmap(self.reorderIcon, ThemeQColor("SCRUBBER_TICK"), iconSize))
        frameNumber, separator, filename = text.partition("\t")
        metrics = QtGui.QFontMetrics(font)
        if separator:
            numberWidth = metrics.horizontalAdvance("0" * max(4, len(frameNumber)))
            numberRect = QtCore.QRect(textRect.left(), textRect.top(), numberWidth, textRect.height())
            filenameRect = textRect.adjusted(numberWidth + 22, 0, 0, 0)
            painter.drawText(numberRect, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter, frameNumber)
            painter.drawText(filenameRect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, filename)
        else:
            painter.drawText(textRect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, text)

        if isPendingRemove:
            iconToPaint = self.visibleIcon if isManuallyEnabled else self.hiddenIcon
            painter.drawPixmap(iconRect, self.TintedIconPixmap(iconToPaint, ThemeQColor("ERROR"), iconSize))
        elif isManuallyEnabled and isSelected and not isActive:
            painter.drawPixmap(iconRect, self.TintedIconPixmap(self.visibleIcon, ThemeQColor("TEXT_MUTED"), iconSize))
        elif isManuallyEnabled:
            self.visibleIcon.paint(painter, iconRect)
        else:
            painter.drawPixmap(iconRect, self.TintedIconPixmap(self.hiddenIcon, ThemeQColor("TEXT_DISABLED"), iconSize))
        if hasWarning:
            painter.drawPixmap(warningIconRect, self.TintedIconPixmap(self.warningIcon, ThemeQColor("WARNING"), iconSize))
        if isMissing:
            painter.drawPixmap(errorIconRect, self.TintedIconPixmap(self.errorIcon, ThemeQColor("ERROR"), iconSize))
        painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(1, 28)

    def IconRect(self, option):
        iconSize = 18
        iconMargin = 8
        return QtCore.QRect(
            option.rect.right() - iconMargin - iconSize,
            option.rect.top() + ((option.rect.height() - iconSize) // 2),
            iconSize,
            iconSize,
        )

    def SideIconRect(self, option, slot):
        iconSize = 18
        iconMargin = 8
        return QtCore.QRect(
            option.rect.right() - (iconMargin * (slot + 2)) - (iconSize * (slot + 2)),
            option.rect.top() + ((option.rect.height() - iconSize) // 2),
            iconSize,
            iconSize,
        )

    def editorEvent(self, event, model, option, index):
        if (
            event.type() == QtCore.QEvent.Type.MouseButtonRelease
            and event.button() == QtCore.Qt.MouseButton.LeftButton
            and self.IconRect(option).contains(event.position().toPoint())
        ):
            self.toggleRequested.emit(index.row())
            return True

        return super().editorEvent(event, model, option, index)
