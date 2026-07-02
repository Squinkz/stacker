import os

from PySide6 import QtCore, QtGui


CURRENT_THEME = "dark_fire"
_ASSET_ICON_CACHE = {}
_DARK_ASSET_ICON_CACHE = {}
_SPLIT_ASSET_ICON_CACHE = {}
_STATUS_ASSET_ICON_CACHE = {}

STATUS_ASSET_FILENAMES = {
    "warning": "titlebar_warning_F5A623.svg",
    "error": "titlebar_error_E53935.svg",
    "info": "titlebar_info_2F80ED.svg",
}

THEME_DISPLAY_NAMES = {
    "dark_fire": "Dark Fire",
    "dark_ice": "Dark Ice",
    "light_fire": "Light Fire",
    "light_ice": "Light Ice",
}

THEME_ALIASES = {
    "dark": "dark_fire",
    "dark fire": "dark_fire",
    "dark_fire": "dark_fire",
    "dark ice": "dark_ice",
    "dark_ice": "dark_ice",
    "light": "light_fire",
    "light fire": "light_fire",
    "light_fire": "light_fire",
    "light ice": "light_ice",
    "light_ice": "light_ice",
}

THEME_ASSET_SUFFIXES = {
    "dark": "E3E3E3",
    "light": "202020",
}


STYLE_TEMPLATE = """
QWidget {
    background: __APP_BG__;
    color: __TEXT__;
    font-size: 10pt;
}
QLabel#warningLabel {
    color: __WARNING__;
}
QLabel#errorLabel {
    color: __ERROR__;
}
QLabel#mutedLabel {
    color: __TEXT_MUTED__;
}
QLabel#dialogHeading {
    color: __OVERLAY_TITLE__;
    font-size: 13pt;
    font-weight: 700;
}
QFrame#sectionHeadingLine {
    color: __SECTION_LINE__;
    background: __SECTION_LINE__;
    max-height: 1px;
}
QGroupBox {
    border: 1px solid __PANEL_BORDER__;
    border-radius: 6px;
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QSplitter::handle {
    background: __APP_BG__;
}
QSplitter::handle:hover {
    background: __PANEL_BORDER_HOVER__;
}
QWidget#collapsibleSection {
    border: 1px solid __PANEL_BORDER_HOVER__;
    border-radius: 6px;
}
QToolButton#collapsibleHeader {
    background: __FIELD_BG__;
    border: 1px solid __FIELD_BG__;
    border-radius: 4px;
    padding: 5px 8px;
    font-weight: 700;
    text-align: left;
}
QToolButton#collapsibleHeader:hover {
    background: __FIELD_HOVER__;
    border: 1px solid __FIELD_HOVER__;
}
QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QPlainTextEdit {
    background: __FIELD_BG__;
    border: 1px solid __FIELD_BG__;
    border-radius: 4px;
    padding: 4px;
    selection-background-color: __SELECTION__;
}
QListWidget,
QListView {
    background: __DISABLED_BG__;
    border: 1px solid __DISABLED_BG__;
    border-radius: 4px;
    padding: 4px;
    outline: 0;
}
QListWidget::item,
QListView::item {
    min-height: 22px;
    padding: 3px 6px;
    border-radius: 3px;
}
QListWidget::item:hover,
QListView::item:hover {
    background: __FIELD_HOVER__;
}
QListWidget::item:selected,
QListWidget::item:selected:!active,
QListView::item:selected,
QListView::item:selected:!active {
    background: __SELECTION__;
    color: __SELECTION_TEXT__;
}
QListWidget:disabled,
QListView:disabled {
    color: __TEXT_DISABLED__;
    background: __DISABLED_BG__;
    border-color: __DISABLED_BG__;
}
QScrollBar:vertical {
    background: __DISABLED_BG__;
    border: none;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: __PANEL_BORDER_HOVER__;
    border-radius: 4px;
    min-height: 28px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: __TEXT_MUTED__;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: __DISABLED_BG__;
    border: none;
}
QScrollBar:horizontal {
    background: __DISABLED_BG__;
    border: none;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: __PANEL_BORDER_HOVER__;
    border-radius: 4px;
    min-width: 28px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: __TEXT_MUTED__;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: __DISABLED_BG__;
    border: none;
}
QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QPushButton,
QToolButton {
    min-height: 22px;
    max-height: 22px;
}
QComboBox {
    background: __FIELD_BG__;
    border: 1px solid __FIELD_BG__;
    border-radius: 5px;
    padding: 4px 36px 4px 10px;
}
QComboBox:hover {
    background: __FIELD_HOVER__;
}
QComboBox:pressed {
    background: __FIELD_PRESSED__;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid __FIELD_BG__;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    background: __FIELD_BG__;
}
QComboBox::drop-down:hover {
    background: __FIELD_HOVER__;
}
QComboBox::down-arrow {
    image: url("__DROPDOWN_DOWN__");
    width: 16px;
    height: 16px;
}
QComboBox QAbstractItemView {
    background: __FIELD_BG__;
    border: 1px solid __PANEL_BORDER_HOVER__;
    selection-background-color: __SELECTION__;
    selection-color: __SELECTION_TEXT__;
    outline: 0;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 5px 14px;
    border-radius: 4px;
}
QComboBox QAbstractItemView::item:selected {
    background: __SELECTION__;
    color: __SELECTION_TEXT__;
}
QMenu {
    background: __FIELD_BG__;
    border: 1px solid __PANEL_BORDER_HOVER__;
    padding: 4px;
}
QMenu::item {
    background: transparent;
    color: __TEXT__;
    padding: 7px 30px 7px 18px;
    border-radius: 4px;
}
QMenu#viewportContextMenu::item {
    padding: 7px 32px 7px 32px;
}
QMenu#fileListContextMenu::item {
    padding: 7px 34px 7px 38px;
}
QMenu::item:selected {
    background: __SELECTION__;
    color: __SELECTION_TEXT__;
}
QMenu::item:disabled {
    background: transparent;
    color: __TEXT_DISABLED__;
}
QMenu::item:disabled:selected {
    background: transparent;
    color: __TEXT_DISABLED__;
}
QMenu::item:checked {
    background: __CHECKED_ROW__;
    color: __SELECTION_TEXT__;
}
QMenu::item:checked:selected {
    background: __SELECTION__;
    color: __SELECTION_TEXT__;
}
QMenu::item:pressed {
    background: __SELECTION_PRESSED__;
}
QMenu::indicator {
    width: 0;
    height: 0;
}
QMenu#viewportContextMenu::indicator {
    width: 16px;
    height: 16px;
    left: 12px;
}
QMenu#viewportContextMenu::indicator:checked {
    image: url("__MENU_CHECK__");
}
QMenu#fileListContextMenu::icon {
    left: 12px;
    width: 16px;
    height: 16px;
}
QMenu::separator {
    height: 1px;
    background: __PANEL_BORDER_HOVER__;
    margin: 4px 6px;
}
QPushButton#viewportMenuItem {
    background: transparent;
    border: 1px solid transparent;
    color: __TEXT__;
    border-radius: 4px;
    padding: 7px 28px 7px 14px;
    min-height: 24px;
    text-align: left;
}
QPushButton#viewportMenuItem:hover,
QPushButton#viewportMenuItem:checked {
    background: __SELECTION__;
    border-color: __SELECTION__;
    color: __SELECTION_TEXT__;
}
QPushButton#viewportMenuItem QLabel {
    background: transparent;
    color: __TEXT__;
}
QPushButton#viewportMenuItem:hover QLabel,
QPushButton#viewportMenuItem:checked QLabel {
    color: __SELECTION_TEXT__;
}
QPushButton#headerMenuItem {
    background: transparent;
    border: 1px solid transparent;
    color: __TEXT__;
    border-radius: 4px;
    padding: 7px 0;
    min-height: 24px;
    text-align: left;
}
QPushButton#headerMenuItem:hover,
QPushButton#headerMenuItem:checked {
    background: __SELECTION__;
    border-color: __SELECTION__;
    color: __SELECTION_TEXT__;
}
QPushButton#headerMenuItem[softDisabled="true"] {
    background: transparent;
    border-color: transparent;
    color: __TEXT_DISABLED__;
}
QPushButton#headerMenuItem QLabel {
    background: transparent;
    color: __TEXT__;
}
QPushButton#headerMenuItem:hover QLabel,
QPushButton#headerMenuItem:checked QLabel {
    color: __SELECTION_TEXT__;
}
QPushButton#headerMenuItem[softDisabled="true"] QLabel {
    color: __TEXT_DISABLED__;
}
QLabel#menuTextLabel[softDisabled="true"],
QLabel#menuShortcutLabel[softDisabled="true"] {
    color: __TEXT_DISABLED__;
}
QPushButton#headerMenuItem QLabel#menuShortcutLabel {
    color: __TEXT_MUTED__;
    font-size: 8pt;
}
QPushButton#viewportMenuItem QLabel#menuShortcutLabel {
    color: __TEXT_MUTED__;
    font-size: 8pt;
}
QPushButton#headerMenuItem[softDisabled="true"] QLabel#menuShortcutLabel {
    color: __TEXT_DISABLED__;
}
QPushButton#headerMenuItem:hover QLabel#menuShortcutLabel,
QPushButton#headerMenuItem:checked QLabel#menuShortcutLabel,
QPushButton#viewportMenuItem:hover QLabel#menuShortcutLabel,
QPushButton#viewportMenuItem:checked QLabel#menuShortcutLabel {
    color: __SELECTION_TEXT__;
}
QPushButton#viewportMenuItem[forceIdle="true"],
QPushButton#headerMenuItem[forceIdle="true"] {
    background: transparent;
    border-color: transparent;
    color: __TEXT__;
}
QPushButton#viewportMenuItem[forceIdle="true"] QLabel,
QPushButton#headerMenuItem[forceIdle="true"] QLabel {
    color: __TEXT__;
}
QPushButton#viewportMenuItem[forceIdle="true"] QLabel#menuShortcutLabel,
QPushButton#headerMenuItem[forceIdle="true"] QLabel#menuShortcutLabel {
    color: __TEXT_MUTED__;
}
QMenu#footerActionMenu {
    padding: 4px;
}
QPushButton#footerMenuItem {
    background: transparent;
    border: 1px solid transparent;
    color: __TEXT__;
    border-radius: 4px;
    padding: 7px 16px;
    min-height: 24px;
    max-height: 24px;
}
QPushButton#footerMenuItem:hover {
    background: __SELECTION__;
    border-color: __SELECTION__;
    color: __SELECTION_TEXT__;
}
QPushButton#footerMenuItem:checked {
    background: __CHECKED_ROW__;
    border-color: __CHECKED_ROW__;
    color: __SELECTION_TEXT__;
}
QPushButton#footerMenuItem:checked:hover {
    background: __SELECTION__;
    border-color: __SELECTION__;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox:disabled {
    color: __TEXT_DISABLED__;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QCheckBox::indicator:unchecked {
    image: url("__CHECK_OFF__");
}
QCheckBox::indicator:checked {
    image: url("__CHECK_ON__");
}
QCheckBox::indicator:unchecked:disabled {
    image: url("__CHECK_OFF_DISABLED__");
}
QCheckBox::indicator:checked:disabled {
    image: url("__CHECK_ON_DISABLED__");
}
QSpinBox,
QDoubleSpinBox {
    padding-right: 22px;
}
QSpinBox::up-button,
QDoubleSpinBox::up-button,
QSpinBox::down-button,
QDoubleSpinBox::down-button {
    background: __FIELD_BG__;
    border-left: 1px solid __FIELD_BG__;
    width: 20px;
}
QSpinBox::up-button,
QDoubleSpinBox::up-button {
    border-top-right-radius: 4px;
    border-bottom: 1px solid __FIELD_BG__;
}
QSpinBox::down-button,
QDoubleSpinBox::down-button {
    border-bottom-right-radius: 4px;
}
QSpinBox::up-button:hover,
QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover {
    background: __FIELD_HOVER__;
}
QSpinBox::up-arrow,
QDoubleSpinBox::up-arrow {
    image: url("__SPIN_UP__");
    width: 16px;
    height: 16px;
}
QSpinBox::down-arrow,
QDoubleSpinBox::down-arrow {
    image: url("__SPIN_DOWN__");
    width: 16px;
    height: 16px;
}
QLineEdit:disabled,
QComboBox:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled,
QPlainTextEdit:disabled {
    color: __TEXT_DISABLED__;
    background: __DISABLED_BG__;
    border-color: __DISABLED_BG__;
}
QComboBox::drop-down:disabled,
QSpinBox::up-button:disabled,
QDoubleSpinBox::up-button:disabled,
QSpinBox::down-button:disabled,
QDoubleSpinBox::down-button:disabled {
    background: __DISABLED_BG__;
    border-color: __DISABLED_BG__;
}
QPushButton,
QToolButton {
    background: __FIELD_BG__;
    border: 1px solid __FIELD_BG__;
    border-radius: 5px;
    padding: 4px 12px;
}
QToolButton#exportButton {
    background: __EXPORT_BG__;
    border-color: __EXPORT_BG__;
    min-height: 34px;
    max-height: 34px;
}
QToolButton#exportButton:hover {
    background: __EXPORT_HOVER__;
    border-color: __EXPORT_HOVER__;
}
QToolButton#exportButton:pressed {
    background: __EXPORT_PRESSED__;
    border-color: __EXPORT_PRESSED__;
}
QToolButton#exportButton:disabled {
    color: __TEXT_DISABLED__;
    background: __EXPORT_DISABLED__;
    border-color: __EXPORT_DISABLED__;
}
QPushButton#previewButton,
QToolButton#previewButton {
    background: __PREVIEW_BG__;
    border-color: __PREVIEW_BG__;
    min-height: 34px;
    max-height: 34px;
}
QPushButton#previewButton:hover,
QToolButton#previewButton:hover {
    background: __PREVIEW_HOVER__;
    border-color: __PREVIEW_HOVER__;
}
QPushButton#previewButton:pressed,
QToolButton#previewButton:pressed {
    background: __PREVIEW_PRESSED__;
    border-color: __PREVIEW_PRESSED__;
}
QPushButton#cancelButton {
    background: __CANCEL_BG__;
    border-color: __CANCEL_BG__;
    min-height: 34px;
    max-height: 34px;
}
QPushButton#cancelButton:hover {
    background: __CANCEL_HOVER__;
    border-color: __CANCEL_HOVER__;
}
QPushButton#cancelButton:pressed {
    background: __CANCEL_PRESSED__;
    border-color: __CANCEL_PRESSED__;
}
QPushButton#transportButton {
    background: __OVERLAY_BUTTON__;
    border-color: __OVERLAY_BUTTON__;
    min-width: 54px;
    max-width: 54px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
}
QPushButton#transportButton[wideTransportButton="false"] {
    min-width: 36px;
    max-width: 36px;
}
QPushButton#transportButton:hover {
    background: __OVERLAY_BUTTON_HOVER__;
    border-color: __OVERLAY_BUTTON_HOVER__;
}
QPushButton#transportButton:pressed {
    background: __OVERLAY_BUTTON_PRESSED__;
    border-color: __OVERLAY_BUTTON_PRESSED__;
}
QPushButton#transportButton:disabled {
    background: __OVERLAY_BUTTON_DISABLED__;
    border-color: __OVERLAY_BUTTON_DISABLED__;
}
QPushButton#fullscreenButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    padding: 0;
}
QPushButton#fullscreenButton:hover {
    background: __FULLSCREEN_HOVER__;
    border-color: __FULLSCREEN_HOVER__;
}
QPushButton#fullscreenButton:pressed {
    background: __FULLSCREEN_PRESSED__;
    border-color: __FULLSCREEN_PRESSED__;
}
QPushButton#settingsButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    padding: 0;
}
QPushButton#settingsButton:hover {
    background: __FULLSCREEN_HOVER__;
    border-color: __FULLSCREEN_HOVER__;
}
QPushButton#settingsButton:pressed {
    background: __FULLSCREEN_PRESSED__;
    border-color: __FULLSCREEN_PRESSED__;
}
QPushButton#settingsButton:checked {
    background: __SELECTION__;
    border-color: __SELECTION__;
}
QPushButton#stackerTextLogoButton,
QPushButton#stackerTextLogoButton:hover,
QPushButton#stackerTextLogoButton:pressed,
QPushButton#stackerTextLogoButton:checked {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 0;
    min-width: 128px;
    max-width: 128px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
}
QToolButton#inputToolButton[showCheckedState="true"]:checked {
    background: __SELECTION__;
    border-color: __SELECTION__;
}
QToolButton#inputToolButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 30px;
    max-height: 30px;
    padding: 0;
}
QPushButton:hover,
QToolButton:hover {
    background: __FIELD_HOVER__;
    border-color: __FIELD_HOVER__;
}
QPushButton:pressed,
QToolButton:pressed {
    background: __FIELD_PRESSED__;
    border-color: __FIELD_PRESSED__;
}
QPushButton:disabled,
QToolButton:disabled {
    color: __TEXT_DISABLED__;
    background: __DISABLED_BG__;
    border-color: __DISABLED_BG__;
}
QPushButton#renderPathButton:checked {
    background: __SELECTION__;
    border-color: __SELECTION__;
    color: __SELECTION_TEXT__;
}
QPushButton#renderPathButton:checked:hover {
    background: __SELECTION_PRESSED__;
    border-color: __SELECTION_PRESSED__;
}
QPushButton#renderPathButton {
    padding-left: 12px;
    padding-right: 12px;
}
QPushButton#savePresetButton {
    padding-left: 14px;
    padding-right: 14px;
}
QFrame#blendSeparator {
    color: __PANEL_BORDER_HOVER__;
    background: __PANEL_BORDER_HOVER__;
    max-height: 1px;
}
QToolButton::menu-button {
    width: 28px;
}
QToolButton::menu-arrow {
    image: url("__DROPDOWN_DOWN__");
    width: 16px;
    height: 16px;
}
QToolButton[hideMenuArrow="true"]::menu-button {
    width: 0;
    border: none;
}
QToolButton[hideMenuArrow="true"]::menu-arrow {
    image: none;
    width: 0;
    height: 0;
}
QToolButton#previewButton::menu-arrow,
QToolButton#exportButton::menu-arrow {
    image: url("__DROPDOWN_UP__");
    width: 16px;
    height: 16px;
}
QTabWidget::pane {
    border: 1px solid __FIELD_BG__;
    border-radius: 5px;
    top: -1px;
}
QTabWidget#viewportTabs[viewportOnly="true"]::pane {
    border: 0;
    border-radius: 0;
    top: 0;
}
QTabBar::tab {
    background: __TAB_BG__;
    border: 1px solid __TAB_BG__;
    padding: 5px 14px;
    margin-right: 2px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}
QTabBar::tab:selected {
    background: __TAB_SELECTED__;
    border-color: __TAB_SELECTED__;
}
QTabBar::tab:!selected {
    color: __TAB_TEXT__;
}
QProgressBar {
    background: __FIELD_BG__;
    border: 1px solid __FIELD_BG__;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background: __FIELD_BG__;
    border-radius: 3px;
}
QProgressBar#runningProgress::chunk {
    background: #61d66f;
}
QSlider::groove:horizontal {
    height: 6px;
    background: __SLIDER_GROOVE__;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: __SLIDER_FILL__;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
    background: __SLIDER_HANDLE__;
}
QSlider::groove:horizontal:disabled {
    background: __FIELD_HOVER__;
}
QSlider::sub-page:horizontal:disabled {
    background: __SLIDER_DISABLED__;
}
QSlider::handle:horizontal:disabled {
    background: __SLIDER_DISABLED__;
}
QStatusBar {
    background: __DISABLED_BG__;
    color: __TEXT__;
}
QToolButton#exportButton {
    background: __EXPORT_BG__;
    border-color: __EXPORT_BG__;
}
QToolButton#exportButton:hover {
    background: __EXPORT_HOVER__;
    border-color: __EXPORT_HOVER__;
}
QToolButton#exportButton:pressed {
    background: __EXPORT_PRESSED__;
    border-color: __EXPORT_PRESSED__;
}
QToolButton#exportButton:disabled {
    color: __TEXT_DISABLED__;
    background: __EXPORT_DISABLED__;
    border-color: __EXPORT_DISABLED__;
}
QToolButton#previewButton {
    background: __PREVIEW_BG__;
    border-color: __PREVIEW_BG__;
}
QToolButton#previewButton:hover {
    background: __PREVIEW_HOVER__;
    border-color: __PREVIEW_HOVER__;
}
QToolButton#previewButton:pressed {
    background: __PREVIEW_PRESSED__;
    border-color: __PREVIEW_PRESSED__;
}
QToolButton#previewButton:disabled {
    color: __TEXT_DISABLED__;
    background: __DISABLED_BG__;
    border-color: __DISABLED_BG__;
}
QPushButton#cancelButton {
    background: __CANCEL_BG__;
    border-color: __CANCEL_BG__;
}
QPushButton#cancelButton:hover {
    background: __CANCEL_HOVER__;
    border-color: __CANCEL_HOVER__;
}
QPushButton#cancelButton:pressed {
    background: __CANCEL_PRESSED__;
    border-color: __CANCEL_PRESSED__;
}
QPushButton#cancelButton:disabled {
    color: __TEXT_DISABLED__;
    background: __DISABLED_BG__;
    border-color: __DISABLED_BG__;
}
"""

BASE_DARK_THEME = {
        "APP_BG": "#191919",
        "TEXT": "#e7e9ee",
        "TEXT_MUTED": "#b8b8b8",
        "TEXT_DISABLED": "#9a9a9a",
        "ICON_DISABLED": "#565656",
        "FIELD_BG": "#282828",
        "FIELD_HOVER": "#303030",
        "FIELD_PRESSED": "#222222",
        "TAB_BG": "#282828",
        "TAB_SELECTED": "#303030",
        "TAB_TEXT": "#b8b8b8",
        "DISABLED_BG": "#151515",
        "PANEL_BORDER": "#343434",
        "PANEL_BORDER_HOVER": "#3d3d3d",
        "SECTION_LINE": "#343434",
        "SELECTION": "#5f5f5f",
        "SELECTION_TEXT": "#ffffff",
        "SELECTION_PRESSED": "#4f4f4f",
        "CHECKED_ROW": "#3a3a3a",
        "SLIDER_GROOVE": "#303030",
        "SLIDER_FILL": "#a8a8a8",
        "SLIDER_HANDLE": "#d0d0d0",
        "SLIDER_DISABLED": "#777777",
        "CONSOLE_BG": "#0e0e0e",
        "OVERLAY_BUTTON": "rgba(40, 40, 40, 180)",
        "OVERLAY_BUTTON_HOVER": "rgba(48, 48, 48, 220)",
        "OVERLAY_BUTTON_PRESSED": "rgba(34, 34, 34, 230)",
        "OVERLAY_BUTTON_DISABLED": "rgba(21, 21, 21, 130)",
        "FULLSCREEN_HOVER": "rgba(48, 48, 48, 140)",
        "FULLSCREEN_PRESSED": "rgba(34, 34, 34, 180)",
        "EXPORT_BG": "#245f36",
        "EXPORT_HOVER": "#2f7a46",
        "EXPORT_PRESSED": "#1d4a2b",
        "EXPORT_DISABLED": "#183321",
        "PREVIEW_BG": "#245c61",
        "PREVIEW_HOVER": "#307980",
        "PREVIEW_PRESSED": "#1d484c",
        "CANCEL_BG": "#6d2c2c",
        "CANCEL_HOVER": "#8a3939",
        "CANCEL_PRESSED": "#562323",
        "VIEWPORT_BG": "#0e0e0e",
        "OVERLAY_BG": (20, 20, 20, 210),
        "OVERLAY_TEXT": "#e7e9ee",
        "OVERLAY_MUTED": "#b8b8b8",
        "PLACEHOLDER_TEXT": "#b8b8b8",
        "OVERLAY_TITLE": "#ffa100",
        "WARNING": "#d5a24a",
        "ERROR": "#ff5c5c",
        "INFO": "#4aa3ff",
        "SCRUBBER_BG": "#151515",
        "SCRUBBER_LINE": "#343434",
        "SCRUBBER_TICK": "#5d5d5d",
        "SCRUBBER_MAJOR_TICK": "#8a8a8a",
        "SCRUBBER_HANDLE": "#72b8ff",
        "SCRUBBER_HANDLE_BORDER": "#b9dcff",
}

BASE_LIGHT_THEME = {
        "APP_BG": "#f0f0f0",
        "TEXT": "#202020",
        "TEXT_MUTED": "#666666",
        "TEXT_DISABLED": "#8a8a8a",
        "ICON_DISABLED": "#9a9a9a",
        "FIELD_BG": "#ffffff",
        "FIELD_HOVER": "#e9e9e9",
        "FIELD_PRESSED": "#dddddd",
        "TAB_BG": "#e2e2e2",
        "TAB_SELECTED": "#ffffff",
        "TAB_TEXT": "#555555",
        "DISABLED_BG": "#e2e2e2",
        "PANEL_BORDER": "#cfcfcf",
        "PANEL_BORDER_HOVER": "#bdbdbd",
        "SECTION_LINE": "#b8b8b8",
        "SELECTION": "#d8d8d8",
        "SELECTION_TEXT": "#111111",
        "SELECTION_PRESSED": "#cfcfcf",
        "CHECKED_ROW": "#e4e4e4",
        "SLIDER_GROOVE": "#b8b8b8",
        "SLIDER_FILL": "#4a4a4a",
        "SLIDER_HANDLE": "#4a4a4a",
        "SLIDER_DISABLED": "#c8c8c8",
        "CONSOLE_BG": "#a0a0a0",
        "OVERLAY_BUTTON": "rgba(245, 245, 245, 180)",
        "OVERLAY_BUTTON_HOVER": "rgba(230, 230, 230, 220)",
        "OVERLAY_BUTTON_PRESSED": "rgba(210, 210, 210, 230)",
        "OVERLAY_BUTTON_DISABLED": "rgba(210, 210, 210, 130)",
        "FULLSCREEN_HOVER": "rgba(230, 230, 230, 150)",
        "FULLSCREEN_PRESSED": "rgba(210, 210, 210, 190)",
        "EXPORT_BG": "#8fd0a4",
        "EXPORT_HOVER": "#78c491",
        "EXPORT_PRESSED": "#64b37d",
        "EXPORT_DISABLED": "#bad3c3",
        "PREVIEW_BG": "#8ecbd0",
        "PREVIEW_HOVER": "#76bdc4",
        "PREVIEW_PRESSED": "#61abb2",
        "CANCEL_BG": "#e0a0a0",
        "CANCEL_HOVER": "#d58787",
        "CANCEL_PRESSED": "#c77171",
        "VIEWPORT_BG": "#a0a0a0",
        "OVERLAY_BG": (255, 255, 255, 225),
        "OVERLAY_TEXT": "#1f1f1f",
        "OVERLAY_MUTED": "#666666",
        "PLACEHOLDER_TEXT": "#444444",
        "OVERLAY_TITLE": "#9c2a0f",
        "WARNING": "#a86700",
        "ERROR": "#b00020",
        "INFO": "#1f6fb8",
        "SCRUBBER_BG": "#efefef",
        "SCRUBBER_LINE": "#c7c7c7",
        "SCRUBBER_TICK": "#8f8f8f",
        "SCRUBBER_MAJOR_TICK": "#626262",
        "SCRUBBER_HANDLE": "#2c79c8",
        "SCRUBBER_HANDLE_BORDER": "#1d4f83",
}

THEMES = {
    "dark_fire": BASE_DARK_THEME,
    "dark_ice": {
        **BASE_DARK_THEME,
        "OVERLAY_TITLE": "#55d8d6",
    },
    "light_fire": BASE_LIGHT_THEME,
    "light_ice": {
        **BASE_LIGHT_THEME,
        "OVERLAY_TITLE": "#155a9f",
    },
}


def NormalizeThemeName(themeName):
    themeName = str(themeName or "dark_fire").strip().lower()
    return THEME_ALIASES.get(themeName, "dark_fire")


def ThemeDisplayName(themeName = None):
    return THEME_DISPLAY_NAMES.get(NormalizeThemeName(themeName or CURRENT_THEME), "Dark Fire")


def ThemeDisplayNames():
    return [THEME_DISPLAY_NAMES[key] for key in ("dark_fire", "dark_ice", "light_fire", "light_ice")]


def ThemeBaseName(themeName = None):
    return "light" if NormalizeThemeName(themeName or CURRENT_THEME).startswith("light") else "dark"


def ThemeAppIconPath(themeName = None):
    flavor = "ice" if NormalizeThemeName(themeName or CURRENT_THEME).endswith("_ice") else "fire"
    return os.path.join(AppRoot(), f"stacker_{flavor}.ico")


def ThemeAboutLogoPath(themeName = None):
    return os.path.join(AppRoot(), "assets", f"stacker_{NormalizeThemeName(themeName or CURRENT_THEME)}.svg")


def SetTheme(themeName):
    global CURRENT_THEME
    CURRENT_THEME = NormalizeThemeName(themeName)


def ThemeName():
    return CURRENT_THEME


def ThemeColor(key, themeName = None):
    theme = THEMES[NormalizeThemeName(themeName or CURRENT_THEME)]
    color = theme.get(key, THEMES["dark_fire"].get(key, "#000000"))
    if isinstance(color, tuple):
        return "rgba({}, {}, {}, {})".format(*color)
    return color


def ThemeQColor(key, themeName = None):
    color = THEMES[NormalizeThemeName(themeName or CURRENT_THEME)].get(key, THEMES["dark_fire"].get(key, "#000000"))
    if isinstance(color, tuple):
        return QtGui.QColor(*color)
    return QtGui.QColor(color)


def AppRoot():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ThemeAssetDir(themeName = None):
    assetRoot = os.path.join(AppRoot(), "assets")
    themeDir = os.path.join(assetRoot, ThemeBaseName(themeName or CURRENT_THEME))
    return themeDir if os.path.isdir(themeDir) else assetRoot


def ThemeAssetFilename(filename, themeName = None):
    suffix = THEME_ASSET_SUFFIXES.get(ThemeBaseName(themeName or CURRENT_THEME), "E3E3E3")
    return str(filename).replace("E3E3E3", suffix)


def ThemeAssetPath(filename, themeName = None):
    themeName = NormalizeThemeName(themeName or CURRENT_THEME)
    assetDir = ThemeAssetDir(themeName)
    themedFilename = ThemeAssetFilename(filename, themeName)
    path = os.path.join(assetDir, themedFilename)
    if os.path.exists(path):
        return path

    fallbackPath = os.path.join(assetDir, filename)
    if os.path.exists(fallbackPath):
        return fallbackPath

    rootPath = os.path.join(AppRoot(), "assets", filename)
    return rootPath


def BuildStyle(themeName = None):
    themeName = NormalizeThemeName(themeName or CURRENT_THEME)
    SetTheme(themeName)
    style = STYLE_TEMPLATE
    for key, value in THEMES[themeName].items():
        if isinstance(value, tuple):
            value = "rgba({}, {}, {}, {})".format(*value)
        style = style.replace(f"__{key}__", value)

    spinUp = ThemeAssetPath("arrow_drop_up_24dp_E3E3E3.svg", themeName).replace("\\", "/")
    spinDown = ThemeAssetPath("arrow_drop_down_24dp_E3E3E3.svg", themeName).replace("\\", "/")
    dropdownDown = ThemeAssetPath("expand_more_24dp_E3E3E3.svg", themeName).replace("\\", "/")
    checkOn = ThemeAssetPath("radio_button_checked_24dp_E3E3E3.svg", themeName).replace("\\", "/")
    checkOff = ThemeAssetPath("radio_button_unchecked_24dp_E3E3E3.svg", themeName).replace("\\", "/")
    checkOnDisabled = ThemeAssetPath("radio_button_checked_24dp_9A9A9A.svg", themeName).replace("\\", "/")
    checkOffDisabled = ThemeAssetPath("radio_button_unchecked_24dp_9A9A9A.svg", themeName).replace("\\", "/")
    menuCheck = ThemeAssetPath("check_24dp_E3E3E3.svg", themeName).replace("\\", "/")
    return (
        style
        .replace("__SPIN_UP__", spinUp)
        .replace("__SPIN_DOWN__", spinDown)
        .replace("__DROPDOWN_UP__", spinUp)
        .replace("__DROPDOWN_DOWN__", dropdownDown)
        .replace("__CHECK_ON__", checkOn)
        .replace("__CHECK_OFF__", checkOff)
        .replace("__CHECK_ON_DISABLED__", checkOnDisabled)
        .replace("__CHECK_OFF_DISABLED__", checkOffDisabled)
        .replace("__MENU_CHECK__", menuCheck)
    )


def BuildDarkStyle():
    return BuildStyle("dark")


def AssetIcon(filename):
    themeName = ThemeName()
    cacheKey = (themeName, filename)
    cachedIcon = _ASSET_ICON_CACHE.get(cacheKey)
    if cachedIcon is not None:
        return cachedIcon

    path = ThemeAssetPath(filename, themeName)

    icon = QtGui.QIcon(path)
    pixmap = icon.pixmap(24, 24)
    if not pixmap.isNull():
        disabled = QtGui.QPixmap(pixmap.size())
        disabled.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(disabled)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(disabled.rect(), ThemeQColor("ICON_DISABLED"))
        painter.end()
        icon.addPixmap(disabled, QtGui.QIcon.Mode.Disabled, QtGui.QIcon.State.Off)
        icon.addPixmap(disabled, QtGui.QIcon.Mode.Disabled, QtGui.QIcon.State.On)
    _ASSET_ICON_CACHE[cacheKey] = icon
    return icon


def DarkAssetIcon(filename):
    cachedIcon = _DARK_ASSET_ICON_CACHE.get(filename)
    if cachedIcon is not None:
        return cachedIcon

    path = os.path.join(AppRoot(), "assets", "dark", filename)
    if not os.path.exists(path):
        path = os.path.join(AppRoot(), "assets", filename)
    icon = QtGui.QIcon(path)
    _DARK_ASSET_ICON_CACHE[filename] = icon
    return icon


def StatusAssetIcon(kind):
    kind = str(kind or "info").lower()
    filename = STATUS_ASSET_FILENAMES.get(kind, STATUS_ASSET_FILENAMES["info"])
    cachedIcon = _STATUS_ASSET_ICON_CACHE.get(filename)
    if cachedIcon is not None:
        return cachedIcon

    icon = QtGui.QIcon(os.path.join(AppRoot(), "assets", filename))
    _STATUS_ASSET_ICON_CACHE[filename] = icon
    return icon


def SplitAssetIcon(filename, side):
    themeName = ThemeName()
    cacheKey = (themeName, filename, side)
    cachedIcon = _SPLIT_ASSET_ICON_CACHE.get(cacheKey)
    if cachedIcon is not None:
        return cachedIcon

    source = AssetIcon(filename).pixmap(24, 24)
    cropRect = QtCore.QRect(0 if side == "left" else 12, 0, 12, 24)
    cropped = source.copy(cropRect)
    pixmap = QtGui.QPixmap(24, 24)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    painter = QtGui.QPainter(pixmap)
    painter.drawPixmap(6, 0, cropped)
    painter.end()
    icon = QtGui.QIcon(pixmap)
    disabled = QtGui.QPixmap(pixmap.size())
    disabled.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(disabled)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(disabled.rect(), ThemeQColor("ICON_DISABLED"))
    painter.end()
    icon.addPixmap(disabled, QtGui.QIcon.Mode.Disabled, QtGui.QIcon.State.Off)
    icon.addPixmap(disabled, QtGui.QIcon.Mode.Disabled, QtGui.QIcon.State.On)
    _SPLIT_ASSET_ICON_CACHE[cacheKey] = icon
    return icon


def PlaceholderIcon():
    pixmap = QtGui.QPixmap(24, 24)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QtGui.QPen(QtGui.QColor("#e7e9ee"), 1.5))
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QtCore.QRectF(7, 7, 10, 10), 2, 2)
    painter.end()
    return QtGui.QIcon(pixmap)
