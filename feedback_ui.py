# Interactive Feedback MCP UI
# Developed by Fábio Ferreira (https://x.com/fabiomlferreira)
# Inspired by/related to dotcursorrules.com (https://dotcursorrules.com/)
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from typing import Optional, TypedDict

import psutil
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QSettings
from PySide6.QtGui import QTextCursor, QIcon, QKeyEvent, QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit, QGroupBox, QGridLayout
)


class FeedbackResult(TypedDict):
    command_logs: str
    interactive_feedback: str


class FeedbackConfig(TypedDict):
    run_command: str
    execute_automatically: bool


def set_dark_title_bar(widget: QWidget, dark_title_bar: bool) -> None:
    # Ensure we're on Windows
    if sys.platform != "win32":
        return

    from ctypes import windll, c_uint32, byref

    # Get Windows build number
    build_number = sys.getwindowsversion().build
    if build_number < 17763:  # Windows 10 1809 minimum
        return

    # Check if the widget's property already matches the setting
    dark_prop = widget.property("DarkTitleBar")
    if dark_prop is not None and dark_prop == dark_title_bar:
        return

    # Set the property (True if dark_title_bar != 0, False otherwise)
    widget.setProperty("DarkTitleBar", dark_title_bar)

    # Load dwmapi.dll and call DwmSetWindowAttribute
    dwmapi = windll.dwmapi
    hwnd = widget.winId()  # Get the window handle
    attribute = 20 if build_number >= 18985 else 19  # Use newer attribute for newer builds
    c_dark_title_bar = c_uint32(dark_title_bar)  # Convert to C-compatible uint32
    dwmapi.DwmSetWindowAttribute(hwnd, attribute, byref(c_dark_title_bar), 4)

    # HACK: Create a 1x1 pixel frameless window to force redraw
    temp_widget = QWidget(None, Qt.FramelessWindowHint)
    temp_widget.resize(1, 1)
    temp_widget.move(widget.pos())
    temp_widget.show()
    temp_widget.deleteLater()  # Safe deletion in Qt event loop


# Modern color scheme constants
PRIMARY_BG = QColor(24, 24, 27)  # Rich dark background
SECONDARY_BG = QColor(39, 39, 42)  # Card/container background
ACCENT_BG = QColor(63, 63, 70)  # Hover/active states
TEXT_PRIMARY = QColor(250, 250, 250)  # Primary text
TEXT_SECONDARY = QColor(161, 161, 170)  # Secondary text
TEXT_MUTED = QColor(113, 113, 122)  # Muted text
ACCENT_COLOR = QColor(99, 102, 241)  # Indigo accent
SUCCESS_COLOR = QColor(34, 197, 94)  # Green for success
ERROR_COLOR = QColor(239, 68, 68)  # Red for errors

# Light theme color constants
LIGHT_PRIMARY_BG = QColor(255, 255, 255)  # Pure white background
LIGHT_SECONDARY_BG = QColor(248, 250, 252)  # Light gray card background
LIGHT_ACCENT_BG = QColor(226, 232, 240)  # Light hover/active states
LIGHT_TEXT_PRIMARY = QColor(15, 23, 42)  # Dark text for contrast
LIGHT_TEXT_SECONDARY = QColor(71, 85, 105)  # Medium gray text
LIGHT_TEXT_MUTED = QColor(148, 163, 184)  # Light gray muted text
LIGHT_ACCENT_COLOR = QColor(99, 102, 241)  # Same indigo accent
LIGHT_SUCCESS_COLOR = QColor(34, 197, 94)  # Same green
LIGHT_ERROR_COLOR = QColor(239, 68, 68)  # Same red


def get_dark_mode_palette(app: QApplication):
    darkPalette = app.palette()
    darkPalette.setColor(QPalette.Window, PRIMARY_BG)
    darkPalette.setColor(QPalette.WindowText, TEXT_PRIMARY)
    darkPalette.setColor(QPalette.Disabled, QPalette.WindowText, TEXT_MUTED)
    darkPalette.setColor(QPalette.Base, SECONDARY_BG)
    darkPalette.setColor(QPalette.AlternateBase, ACCENT_BG)
    darkPalette.setColor(QPalette.ToolTipBase, PRIMARY_BG)
    darkPalette.setColor(QPalette.ToolTipText, TEXT_PRIMARY)
    darkPalette.setColor(QPalette.Text, TEXT_PRIMARY)
    darkPalette.setColor(QPalette.Disabled, QPalette.Text, TEXT_MUTED)
    darkPalette.setColor(QPalette.Dark, QColor(18, 18, 20))
    darkPalette.setColor(QPalette.Shadow, QColor(0, 0, 0))
    darkPalette.setColor(QPalette.Button, SECONDARY_BG)
    darkPalette.setColor(QPalette.ButtonText, TEXT_PRIMARY)
    darkPalette.setColor(QPalette.Disabled, QPalette.ButtonText, TEXT_MUTED)
    darkPalette.setColor(QPalette.BrightText, ERROR_COLOR)
    darkPalette.setColor(QPalette.Link, ACCENT_COLOR)
    darkPalette.setColor(QPalette.Highlight, ACCENT_COLOR)
    darkPalette.setColor(QPalette.Disabled, QPalette.Highlight, ACCENT_BG)
    darkPalette.setColor(QPalette.HighlightedText, TEXT_PRIMARY)
    darkPalette.setColor(QPalette.Disabled, QPalette.HighlightedText, TEXT_MUTED)
    darkPalette.setColor(QPalette.PlaceholderText, TEXT_MUTED)
    return darkPalette


def get_light_mode_palette(app: QApplication):
    lightPalette = app.palette()
    lightPalette.setColor(QPalette.Window, LIGHT_PRIMARY_BG)
    lightPalette.setColor(QPalette.WindowText, LIGHT_TEXT_PRIMARY)
    lightPalette.setColor(QPalette.Disabled, QPalette.WindowText, LIGHT_TEXT_MUTED)
    lightPalette.setColor(QPalette.Base, LIGHT_SECONDARY_BG)
    lightPalette.setColor(QPalette.AlternateBase, LIGHT_ACCENT_BG)
    lightPalette.setColor(QPalette.ToolTipBase, LIGHT_PRIMARY_BG)
    lightPalette.setColor(QPalette.ToolTipText, LIGHT_TEXT_PRIMARY)
    lightPalette.setColor(QPalette.Text, LIGHT_TEXT_PRIMARY)
    lightPalette.setColor(QPalette.Disabled, QPalette.Text, LIGHT_TEXT_MUTED)
    lightPalette.setColor(QPalette.Dark, QColor(200, 200, 200))
    lightPalette.setColor(QPalette.Shadow, QColor(150, 150, 150))
    lightPalette.setColor(QPalette.Button, LIGHT_SECONDARY_BG)
    lightPalette.setColor(QPalette.ButtonText, LIGHT_TEXT_PRIMARY)
    lightPalette.setColor(QPalette.Disabled, QPalette.ButtonText, LIGHT_TEXT_MUTED)
    lightPalette.setColor(QPalette.BrightText, LIGHT_ERROR_COLOR)
    lightPalette.setColor(QPalette.Link, LIGHT_ACCENT_COLOR)
    lightPalette.setColor(QPalette.Highlight, LIGHT_ACCENT_COLOR)
    lightPalette.setColor(QPalette.Disabled, QPalette.Highlight, LIGHT_ACCENT_BG)
    lightPalette.setColor(QPalette.HighlightedText, LIGHT_TEXT_PRIMARY)
    lightPalette.setColor(QPalette.Disabled, QPalette.HighlightedText, LIGHT_TEXT_MUTED)
    lightPalette.setColor(QPalette.PlaceholderText, LIGHT_TEXT_MUTED)
    return lightPalette


def get_modern_stylesheet():
    """Modern flat design stylesheet"""
    return """
    /* Main Window */
    QMainWindow {
        background-color: rgb(24, 24, 27);
        color: rgb(250, 250, 250);
    }
    
    /* Group Boxes - Card Style */
    QGroupBox {
        background-color: rgb(39, 39, 42);
        border: 1px solid rgb(63, 63, 70);
        border-radius: 12px;
        font-size: 14px;
        font-weight: 600;
        color: rgb(250, 250, 250);
        margin-top: 8px;
        padding-top: 14px;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px 0 8px;
        color: rgb(161, 161, 170);
        background-color: transparent;
    }
    
    /* Modern Buttons */
    QPushButton {
        background-color: rgb(99, 102, 241);
        color: rgb(250, 250, 250);
        border: none;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 14px;
        font-weight: 500;
        min-height: 28px;
    }
    
    QPushButton:hover {
        background-color: rgb(79, 70, 229);
    }
    
    QPushButton:pressed {
        background-color: rgb(67, 56, 202);
    }
    
    QPushButton:disabled {
        background-color: rgb(63, 63, 70);
        color: rgb(113, 113, 122);
    }
    
    /* Secondary Button Style */
    QPushButton[class="secondary"] {
        background-color: rgb(63, 63, 70);
        color: rgb(250, 250, 250);
    }
    
    QPushButton[class="secondary"]:hover {
        background-color: rgb(82, 82, 91);
    }
    
    QPushButton[class="secondary"]:pressed {
        background-color: rgb(52, 52, 59);
    }
    
    /* Quick Reply Button Style */
    QPushButton[class="quick-reply"] {
        background-color: rgb(82, 82, 91);
        color: rgb(250, 250, 250);
        border: none;
        border-radius: 12px;
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 400;
        min-height: 20px;
        max-height: 24px;
    }
    
    QPushButton[class="quick-reply"]:hover {
        background-color: rgb(99, 102, 241);
    }
    
    QPushButton[class="quick-reply"]:pressed {
        background-color: rgb(79, 70, 229);
    }
    
    /* Input Fields */
    QLineEdit {
        background-color: rgb(24, 24, 27);
        border: 1px solid rgb(63, 63, 70);
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 14px;
        color: rgb(250, 250, 250);
        selection-background-color: rgb(99, 102, 241);
    }
    
    QLineEdit:focus {
        border: 2px solid rgb(99, 102, 241);
        background-color: rgb(39, 39, 42);
    }
    
    QLineEdit:disabled {
        background-color: rgb(63, 63, 70);
        color: rgb(113, 113, 122);
    }
    
    /* Text Areas */
    QTextEdit {
        background-color: rgb(24, 24, 27);
        border: 1px solid rgb(63, 63, 70);
        border-radius: 8px;
        padding: 10px;
        font-size: 15px;
        color: rgb(250, 250, 250);
        selection-background-color: rgb(99, 102, 241);
        line-height: 1.4;
    }
    
    QTextEdit:focus {
        border: 2px solid rgb(99, 102, 241);
        background-color: rgb(39, 39, 42);
    }
    
    /* Checkboxes */
    QCheckBox {
        color: rgb(250, 250, 250);
        font-size: 14px;
        spacing: 6px;
    }
    
    QCheckBox::indicator {
        width: 14px;
        height: 14px;
        border-radius: 4px;
        border: 1px solid rgb(63, 63, 70);
        background-color: rgb(24, 24, 27);
    }
    
    QCheckBox::indicator:checked {
        background-color: rgb(99, 102, 241);
        border: 1px solid rgb(99, 102, 241);
    }
    
    QCheckBox::indicator:checked:hover {
        background-color: rgb(79, 70, 229);
        border: 1px solid rgb(79, 70, 229);
    }
    
    QCheckBox::indicator:hover {
        border: 1px solid rgb(99, 102, 241);
    }
    
    /* Small Checkbox Style */
    QCheckBox[class="small-checkbox"] {
        color: rgb(161, 161, 170);
        font-size: 11px;
        spacing: 4px;
    }
    
    QCheckBox[class="small-checkbox"]::indicator {
        width: 12px;
        height: 12px;
        border-radius: 3px;
        border: 1px solid rgb(63, 63, 70);
        background-color: rgb(24, 24, 27);
    }
    
    QCheckBox[class="small-checkbox"]::indicator:checked {
        background-color: rgb(99, 102, 241);
        border: 1px solid rgb(99, 102, 241);
    }
    
    /* Labels */
    QLabel {
        color: rgb(250, 250, 250);
        font-size: 14px;
    }
    
    QLabel[class="muted"] {
        color: rgb(161, 161, 170);
        font-size: 13px;
    }
    
    QLabel[class="description"] {
        color: rgb(250, 250, 250);
        font-size: 16px;
        line-height: 1.7;
    }
    
    QLabel[class="section-title"] {
        color: rgb(161, 161, 170);
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    QLabel[class="quick-reply-text"] {
        color: rgb(99, 102, 241);
        font-size: 12px;
        cursor: pointer;
    }
    
    QLabel[class="quick-reply-text"]:hover {
        color: rgb(129, 140, 248);
        text-decoration: underline;
    }
    
    /* Scrollbars */
    QScrollBar:vertical {
        background-color: rgb(39, 39, 42);
        width: 8px;
        border-radius: 4px;
        margin: 0;
    }
    
    QScrollBar::handle:vertical {
        background-color: rgb(63, 63, 70);
        border-radius: 4px;
        min-height: 20px;
    }
    
    QScrollBar::handle:vertical:hover {
        background-color: rgb(82, 82, 91);
    }
    
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0px;
    }
    
    /* Horizontal Layout Spacing */
    QHBoxLayout {
        spacing: 8px;
    }
    
    QVBoxLayout {
        spacing: 12px;
    }
    """


def get_light_stylesheet():
    """Modern flat design stylesheet for light theme"""
    return """
    /* Main Window */
    QMainWindow {
        background-color: rgb(255, 255, 255);
        color: rgb(15, 23, 42);
    }
    
    /* Group Boxes - Card Style */
    QGroupBox {
        background-color: rgb(248, 250, 252);
        border: 1px solid rgb(226, 232, 240);
        border-radius: 12px;
        font-size: 14px;
        font-weight: 600;
        color: rgb(15, 23, 42);
        margin-top: 8px;
        padding-top: 14px;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px 0 8px;
        color: rgb(71, 85, 105);
        background-color: transparent;
    }
    
    /* Modern Buttons */
    QPushButton {
        background-color: rgb(99, 102, 241);
        color: rgb(255, 255, 255);
        border: none;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 14px;
        font-weight: 500;
        min-height: 28px;
    }
    
    QPushButton:hover {
        background-color: rgb(79, 70, 229);
    }
    
    QPushButton:pressed {
        background-color: rgb(67, 56, 202);
    }
    
    QPushButton:disabled {
        background-color: rgb(226, 232, 240);
        color: rgb(148, 163, 184);
    }
    
    /* Secondary Button Style */
    QPushButton[class="secondary"] {
        background-color: rgb(226, 232, 240);
        color: rgb(15, 23, 42);
    }
    
    QPushButton[class="secondary"]:hover {
        background-color: rgb(203, 213, 225);
    }
    
    QPushButton[class="secondary"]:pressed {
        background-color: rgb(148, 163, 184);
    }
    
    /* Quick Reply Button Style */
    QPushButton[class="quick-reply"] {
        background-color: rgb(203, 213, 225);
        color: rgb(15, 23, 42);
        border: none;
        border-radius: 12px;
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 400;
        min-height: 20px;
        max-height: 24px;
    }
    
    QPushButton[class="quick-reply"]:hover {
        background-color: rgb(99, 102, 241);
        color: rgb(255, 255, 255);
    }
    
    QPushButton[class="quick-reply"]:pressed {
        background-color: rgb(79, 70, 229);
        color: rgb(255, 255, 255);
    }
    
    /* Input Fields */
    QLineEdit {
        background-color: rgb(255, 255, 255);
        border: 1px solid rgb(226, 232, 240);
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 14px;
        color: rgb(15, 23, 42);
        selection-background-color: rgb(99, 102, 241);
    }
    
    QLineEdit:focus {
        border: 2px solid rgb(99, 102, 241);
        background-color: rgb(248, 250, 252);
    }
    
    QLineEdit:disabled {
        background-color: rgb(248, 250, 252);
        color: rgb(148, 163, 184);
    }
    
    /* Text Areas */
    QTextEdit {
        background-color: rgb(255, 255, 255);
        border: 1px solid rgb(226, 232, 240);
        border-radius: 8px;
        padding: 10px;
        font-size: 15px;
        color: rgb(15, 23, 42);
        selection-background-color: rgb(99, 102, 241);
        line-height: 1.4;
    }
    
    QTextEdit:focus {
        border: 2px solid rgb(99, 102, 241);
        background-color: rgb(248, 250, 252);
    }
    
    /* Checkboxes */
    QCheckBox {
        color: rgb(15, 23, 42);
        font-size: 14px;
        spacing: 6px;
    }
    
    QCheckBox::indicator {
        width: 14px;
        height: 14px;
        border-radius: 4px;
        border: 1px solid rgb(226, 232, 240);
        background-color: rgb(255, 255, 255);
    }
    
    QCheckBox::indicator:checked {
        background-color: rgb(99, 102, 241);
        border: 1px solid rgb(99, 102, 241);
    }
    
    QCheckBox::indicator:checked:hover {
        background-color: rgb(79, 70, 229);
        border: 1px solid rgb(79, 70, 229);
    }
    
    QCheckBox::indicator:hover {
        border: 1px solid rgb(99, 102, 241);
    }
    
    /* Small Checkbox Style */
    QCheckBox[class="small-checkbox"] {
        color: rgb(15, 23, 42);
        font-size: 11px;
        spacing: 4px;
    }
    
    QCheckBox[class="small-checkbox"]::indicator {
        width: 12px;
        height: 12px;
        border-radius: 3px;
        border: 1px solid rgb(226, 232, 240);
        background-color: rgb(255, 255, 255);
    }
    
    QCheckBox[class="small-checkbox"]::indicator:checked {
        background-color: rgb(99, 102, 241);
        border: 1px solid rgb(99, 102, 241);
    }
    
    /* Labels */
    QLabel {
        color: rgb(15, 23, 42);
        font-size: 14px;
    }
    
    QLabel[class="muted"] {
        color: rgb(71, 85, 105);
        font-size: 13px;
    }
    
    QLabel[class="description"] {
        color: rgb(15, 23, 42);
        font-size: 16px;
        line-height: 1.7;
    }
    
    QLabel[class="section-title"] {
        color: rgb(71, 85, 105);
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    QLabel[class="quick-reply-text"] {
        color: rgb(99, 102, 241);
        font-size: 12px;
        cursor: pointer;
    }
    
    QLabel[class="quick-reply-text"]:hover {
        color: rgb(129, 140, 248);
        text-decoration: underline;
    }
    
    /* Scrollbars */
    QScrollBar:vertical {
        background-color: rgb(248, 250, 252);
        width: 8px;
        border-radius: 4px;
        margin: 0;
    }
    
    QScrollBar::handle:vertical {
        background-color: rgb(226, 232, 240);
        border-radius: 4px;
        min-height: 20px;
    }
    
    QScrollBar::handle:vertical:hover {
        background-color: rgb(203, 213, 225);
    }
    
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0px;
    }
    
    /* Horizontal Layout Spacing */
    QHBoxLayout {
        spacing: 8px;
    }
    
    QVBoxLayout {
        spacing: 12px;
    }
    """


def kill_tree(process: subprocess.Popen):
    killed: list[psutil.Process] = []
    parent = psutil.Process(process.pid)
    for proc in parent.children(recursive=True):
        try:
            proc.kill()
            killed.append(proc)
        except psutil.Error:
            pass
    try:
        parent.kill()
    except psutil.Error:
        pass
    killed.append(parent)

    # Terminate any remaining processes
    for proc in killed:
        try:
            if proc.is_running():
                proc.terminate()
        except psutil.Error:
            pass


def get_user_environment() -> dict[str, str]:
    if sys.platform != "win32":
        return os.environ.copy()

    import ctypes
    from ctypes import wintypes

    # Load required DLLs
    advapi32 = ctypes.WinDLL("advapi32")
    userenv = ctypes.WinDLL("userenv")
    kernel32 = ctypes.WinDLL("kernel32")

    # Constants
    TOKEN_QUERY = 0x0008

    # Function prototypes
    OpenProcessToken = advapi32.OpenProcessToken
    OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    OpenProcessToken.restype = wintypes.BOOL

    CreateEnvironmentBlock = userenv.CreateEnvironmentBlock
    CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.BOOL]
    CreateEnvironmentBlock.restype = wintypes.BOOL

    DestroyEnvironmentBlock = userenv.DestroyEnvironmentBlock
    DestroyEnvironmentBlock.argtypes = [wintypes.LPVOID]
    DestroyEnvironmentBlock.restype = wintypes.BOOL

    GetCurrentProcess = kernel32.GetCurrentProcess
    GetCurrentProcess.argtypes = []
    GetCurrentProcess.restype = wintypes.HANDLE

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    # Get process token
    token = wintypes.HANDLE()
    if not OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise RuntimeError("Failed to open process token")

    try:
        # Create environment block
        environment = ctypes.c_void_p()
        if not CreateEnvironmentBlock(ctypes.byref(environment), token, False):
            raise RuntimeError("Failed to create environment block")

        try:
            # Convert environment block to list of strings
            result = {}
            env_ptr = ctypes.cast(environment, ctypes.POINTER(ctypes.c_wchar))
            offset = 0

            while True:
                # Get string at current offset
                current_string = ""
                while env_ptr[offset] != "\0":
                    current_string += env_ptr[offset]
                    offset += 1

                # Skip null terminator
                offset += 1

                # Break if we hit double null terminator
                if not current_string:
                    break

                equal_index = current_string.index("=")
                if equal_index == -1:
                    continue

                key = current_string[:equal_index]
                value = current_string[equal_index + 1:]
                result[key] = value

            return result

        finally:
            DestroyEnvironmentBlock(environment)

    finally:
        CloseHandle(token)


class FeedbackTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            # Find the parent FeedbackUI instance and call submit
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                parent._submit_feedback()
        else:
            super().keyPressEvent(event)


class LogSignals(QObject):
    append_log = Signal(str)


class FeedbackUI(QMainWindow):
    # Quick reply phrases for feedback
    QUICK_REPLIES = [
        "看起来不错，按计划继续",
        "完全正确，任务完成", 
        "有小问题需要修正",
        "缺少重要功能"
    ]
    
    def __init__(self, project_directory: str, prompt: str):
        super().__init__()
        self.project_directory = project_directory
        self.prompt = prompt

        self.process: Optional[subprocess.Popen] = None
        self.log_buffer = []
        self.feedback_result = None
        self.log_signals = LogSignals()
        self.log_signals.append_log.connect(self._append_log)

        self.setWindowTitle("Interactive Feedback MCP")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "images", "feedback.png")
        self.setWindowIcon(QIcon(icon_path))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        self.settings = QSettings("InteractiveFeedbackMCP", "InteractiveFeedbackMCP")
        
        # Load general UI settings for the main window (geometry, state)
        self.settings.beginGroup("MainWindow_General")
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(500, 600)
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - 500) // 2
            y = (screen.height() - 600) // 2
            self.move(x, y)
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)
        self.settings.endGroup()  # End "MainWindow_General" group
        
        # Load project-specific settings (command, auto-execute, command section visibility)
        self.project_group_name = get_project_settings_group(self.project_directory)
        self.settings.beginGroup(self.project_group_name)
        loaded_run_command = self.settings.value("run_command", "", type=str)
        loaded_execute_auto = self.settings.value("execute_automatically", False, type=bool)
        command_section_visible = self.settings.value("commandSectionVisible", False, type=bool)
        self.settings.endGroup()  # End project-specific group
        
        self.config: FeedbackConfig = {
            "run_command": loaded_run_command,
            "execute_automatically": loaded_execute_auto
        }

        # Theme management
        self.theme_mode = self.settings.value("theme/mode", "auto", type=str)  # "auto", "dark", "light"
        self.is_dark_theme = self._get_effective_theme()

        self._create_ui()  # self.config is used here to set initial values

        # Set command section visibility AFTER _create_ui has created relevant widgets
        self.command_group.setVisible(command_section_visible)
        if command_section_visible:
            self.toggle_command_button.setText("Hide Command Section")
        else:
            self.toggle_command_button.setText("Command Section")

        # Start theme monitoring timer for auto mode
        self.theme_timer = QTimer()
        self.theme_timer.timeout.connect(self._check_system_theme_change)
        if self.theme_mode == "auto":
            self.theme_timer.start(3000)  # Check every 3 seconds only in auto mode

        set_dark_title_bar(self, True)

        if self.config.get("execute_automatically", False):
            self._run_command()

    def _format_windows_path(self, path: str) -> str:
        if sys.platform == "win32":
            # Convert forward slashes to backslashes
            path = path.replace("/", "\\")
            # Capitalize drive letter if path starts with x:\
            if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
                path = path[0].upper() + path[1:]
        return path

    def _create_ui(self):
        self.setWindowTitle("Interactive Feedback")
        self.setMinimumSize(500, 500)
        
        # Apply modern stylesheet
        self.setStyleSheet(get_modern_stylesheet())
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Toggle Command Section Button and Restore Size Button in horizontal layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        # Toggle Command Section Button (70% width)
        self.toggle_command_button = QPushButton("Command Plan'e")
        self.toggle_command_button.setProperty("class", "secondary")
        self.toggle_command_button.clicked.connect(self._toggle_command_section)
        
        # Restore Default Size Button (20% width)
        self.restore_size_button = QPushButton("🔄")
        self.restore_size_button.setProperty("class", "secondary")
        self.restore_size_button.clicked.connect(self.restore_default_window_size)
        
        # Theme Toggle Button (10% width)
        theme_icon = "💻" if self.theme_mode == "auto" else ("🌙" if self.theme_mode == "dark" else "☀️")
        self.theme_toggle_button = QPushButton(theme_icon)
        self.theme_toggle_button.setProperty("class", "secondary")
        self.theme_toggle_button.clicked.connect(self.toggle_theme)
        
        # Add buttons to layout with 7:2:1 ratio
        buttons_layout.addWidget(self.toggle_command_button, 8)
        buttons_layout.addWidget(self.restore_size_button, 1)
        buttons_layout.addWidget(self.theme_toggle_button, 1)
        
        layout.addLayout(buttons_layout)

        # Command section
        self.command_group = QGroupBox("Command")
        command_layout = QVBoxLayout(self.command_group)
        command_layout.setSpacing(14)
        command_layout.setContentsMargins(16, 18, 16, 16)

        # Working directory label
        formatted_path = self._format_windows_path(self.project_directory)
        working_dir_label = QLabel(f"Working directory: {formatted_path}")
        working_dir_label.setProperty("class", "muted")
        working_dir_label.setWordWrap(True)
        command_layout.addWidget(working_dir_label)

        # Command input row
        command_input_layout = QHBoxLayout()
        command_input_layout.setSpacing(10)
        self.command_entry = QLineEdit()
        self.command_entry.setPlaceholderText("Enter command to run (e.g., npm test, python script.py)")
        self.command_entry.setText(self.config["run_command"])
        self.command_entry.returnPressed.connect(self._run_command)
        self.command_entry.textChanged.connect(self._update_config)
        self.run_button = QPushButton("&Run")
        self.run_button.clicked.connect(self._run_command)

        command_input_layout.addWidget(self.command_entry)
        command_input_layout.addWidget(self.run_button)
        command_layout.addLayout(command_input_layout)

        # Auto-execute and save config row
        auto_layout = QHBoxLayout()
        self.auto_check = QCheckBox("Execute automatically on next run")
        self.auto_check.setChecked(self.config.get("execute_automatically", False))
        self.auto_check.stateChanged.connect(self._update_config)

        save_button = QPushButton("&Save Configuration")
        save_button.setProperty("class", "secondary")
        save_button.clicked.connect(self._save_config)

        auto_layout.addWidget(self.auto_check)
        auto_layout.addStretch()
        auto_layout.addWidget(save_button)
        command_layout.addLayout(auto_layout)

        # Console section (now part of command_group)
        console_group = QGroupBox("Console")
        console_layout_internal = QVBoxLayout(console_group)
        console_layout_internal.setSpacing(10)
        console_layout_internal.setContentsMargins(14, 14, 14, 14)
        console_group.setMinimumHeight(200)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        font.setPointSize(9)
        self.log_text.setFont(font)
        console_layout_internal.addWidget(self.log_text)

        # Clear button
        button_layout = QHBoxLayout()
        self.clear_button = QPushButton("&Clear")
        self.clear_button.setProperty("class", "secondary")
        self.clear_button.clicked.connect(self.clear_logs)
        button_layout.addStretch()
        button_layout.addWidget(self.clear_button)
        console_layout_internal.addLayout(button_layout)

        command_layout.addWidget(console_group)

        self.command_group.setVisible(False)
        layout.addWidget(self.command_group)

        # Feedback section with adjusted height
        self.feedback_group = QGroupBox("Feedback")
        feedback_layout = QVBoxLayout(self.feedback_group)
        feedback_layout.setSpacing(14)
        feedback_layout.setContentsMargins(16, 18, 16, 16)

        # Section title
        section_title = QLabel("AI Assistant Summary")
        section_title.setProperty("class", "section-title")
        feedback_layout.addWidget(section_title)

        # Short description label (from self.prompt)
        self.description_label = QLabel(self.prompt)
        self.description_label.setProperty("class", "description")
        self.description_label.setWordWrap(True)
        self.description_label.setContentsMargins(0, 0, 0, 12)  # Add bottom margin
        feedback_layout.addWidget(self.description_label)

        self.feedback_text = FeedbackTextEdit()
        font_metrics = self.feedback_text.fontMetrics()
        row_height = font_metrics.height()
        # Calculate height for 3 lines + some padding for margins
        padding = self.feedback_text.contentsMargins().top() + self.feedback_text.contentsMargins().bottom() + 5  # 5 is extra vertical padding
        self.feedback_text.setMinimumHeight(3 * row_height + padding)

        self.feedback_text.setPlaceholderText("Enter your feedback here (Cmd+Enter to submit)")
        
        # Quick reply text links
        quick_reply_container = QVBoxLayout()
        quick_reply_container.setSpacing(6)
        quick_reply_container.setContentsMargins(0, 8, 0, 4)  # Add top and bottom margin
        
        # Add quick reply label with auto-submit checkbox
        quick_header_layout = QHBoxLayout()
        quick_header_layout.setSpacing(8)
        
        quick_label = QLabel("Quick Reply:")
        quick_label.setProperty("class", "muted")
        quick_header_layout.addWidget(quick_label)
        
        self.auto_submit_check = QCheckBox("Auto Submit")
        self.auto_submit_check.setChecked(True)  # Default to auto-submit
        self.auto_submit_check.setProperty("class", "small-checkbox")
        quick_header_layout.addWidget(self.auto_submit_check)
        
        quick_header_layout.addStretch()
        quick_reply_container.addLayout(quick_header_layout)
        
        # Create quick reply text links in grid layout (2 per row)
        quick_grid = QGridLayout()
        quick_grid.setSpacing(4)
        quick_grid.setVerticalSpacing(2)
        
        for i, reply_text in enumerate(self.QUICK_REPLIES):
            quick_label = QLabel(f"• {reply_text}")
            quick_label.setProperty("class", "quick-reply-text")
            
            # Create a proper click handler to avoid closure issues
            def make_click_handler(text):
                return lambda event: self._quick_reply_clicked(text)
            
            quick_label.mousePressEvent = make_click_handler(reply_text)
            
            row = i // 2
            col = i % 2
            quick_grid.addWidget(quick_label, row, col)
        
        quick_reply_container.addLayout(quick_grid)
        
        submit_button = QPushButton("&Send Feedback (Cmd+Enter)")
        submit_button.clicked.connect(self._submit_feedback)

        feedback_layout.addWidget(self.feedback_text)
        feedback_layout.addLayout(quick_reply_container)
        feedback_layout.addWidget(submit_button)

        # Set minimum height for feedback_group to accommodate its contents
        # This will be based on the section title, description label and the 3-line feedback_text
        self.feedback_group.setMinimumHeight(
            section_title.sizeHint().height() + self.description_label.sizeHint().height() + self.feedback_text.minimumHeight() + submit_button.sizeHint().height() + feedback_layout.spacing() * 3 + feedback_layout.contentsMargins().top() + feedback_layout.contentsMargins().bottom() + 10)  # 10 for extra padding

        # Add widgets in a specific order
        layout.addWidget(self.feedback_group)

        
        # Apply the theme after all widgets are created
        self.apply_theme()

    def _toggle_command_section(self):
        is_visible = self.command_group.isVisible()
        self.command_group.setVisible(not is_visible)
        if not is_visible:
            self.toggle_command_button.setText("Hide Command Section")
            # When command section becomes visible, call restore_default_window_size method
            self.restore_default_window_size()
        else:
            self.toggle_command_button.setText("Command Section")
            # When closing command section, only adjust window size
            new_height = self.centralWidget().sizeHint().height()
            current_width = self.width()
            self.resize(current_width, new_height)

        # Immediately save the visibility state for this project
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("commandSectionVisible", self.command_group.isVisible())
        self.settings.endGroup()

    def restore_default_window_size(self):
        """Restore the window to its default size based on command section visibility."""
        screen = QApplication.primaryScreen().geometry()
        
        if self.command_group.isVisible():
            # Default size when command section is visible: 1000x500
            default_width, default_height = 500, 1000
        else:
            # Default size when command section is not visible: 600x500
            default_width, default_height = 500, 600
            
        # Calculate center position
        x = (screen.width() - default_width) // 2
        y = (screen.height() - default_height) // 2
        
        # Resize and move window
        self.resize(default_width, default_height)
        self.move(x, y)

    def apply_theme(self, is_dark=None):
        """Apply the specified theme (dark or light) to the UI."""
        if is_dark is None:
            is_dark = self.is_dark_theme
        
        app = QApplication.instance()
        if is_dark:
            app.setPalette(get_dark_mode_palette(app))
            self.setStyleSheet(get_modern_stylesheet())
        else:
            app.setPalette(get_light_mode_palette(app))
            self.setStyleSheet(get_light_stylesheet())
        
        self.is_dark_theme = is_dark
        
        # Update theme toggle button text
        if hasattr(self, 'theme_toggle_button'):
            if self.theme_mode == "auto":
                self.theme_toggle_button.setText("💻")
            elif self.theme_mode == "dark":
                self.theme_toggle_button.setText("🌙")
            else:  # light
                self.theme_toggle_button.setText("☀️")

    def toggle_theme(self):
        """Cycle through auto, dark, and light theme modes."""
        if self.theme_mode == "auto":
            self.theme_mode = "dark"
        elif self.theme_mode == "dark":
            self.theme_mode = "light"
        else:  # light
            self.theme_mode = "auto"
        
        # Update effective theme and apply
        self.is_dark_theme = self._get_effective_theme()
        self.apply_theme()
        
        # Save theme preference
        self.settings.setValue("theme/mode", self.theme_mode)
        
        # Start or stop theme monitoring based on mode
        if hasattr(self, 'theme_timer'):
            if self.theme_mode == "auto":
                if not self.theme_timer.isActive():
                    self.theme_timer.start(3000)
            else:
                self.theme_timer.stop()

    def _update_config(self):
        self.config["run_command"] = self.command_entry.text()
        self.config["execute_automatically"] = self.auto_check.isChecked()

    def _get_system_theme_is_dark(self) -> bool:
        """Detect if system is using dark theme."""
        try:
            if sys.platform == "darwin":  # macOS
                # Try multiple methods for macOS
                try:
                    # Method 1: Check AppleInterfaceStyle
                    result = subprocess.run(
                        ["defaults", "read", "-g", "AppleInterfaceStyle"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0 and "Dark" in result.stdout.strip():
                        return True
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    pass
                
                try:
                    # Method 2: Check using osascript (AppleScript)
                    result = subprocess.run([
                        "osascript", "-e", 
                        "tell application \"System Events\" to tell appearance preferences to get dark mode"
                    ], capture_output=True, text=True, timeout=2)
                    if result.returncode == 0:
                        return result.stdout.strip().lower() == "true"
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    pass
                
                # Default to light theme if detection fails
                return False
                
            elif sys.platform == "win32":  # Windows
                import winreg
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                       r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                        value = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
                        return value == 0  # 0 means dark theme
                except (FileNotFoundError, OSError):
                    return False
            else:  # Linux and others
                return False  # Default to light theme
        except Exception:
            return False  # Default to light theme if detection fails

    def _get_effective_theme(self) -> bool:
        """Get the effective theme based on current mode."""
        if self.theme_mode == "auto":
            return self._get_system_theme_is_dark()
        elif self.theme_mode == "dark":
            return True
        else:  # light
            return False

    def _append_log(self, text: str):
        self.log_buffer.append(text)
        self.log_text.append(text.rstrip())
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def _check_process_status(self):
        if self.process and self.process.poll() is not None:
            # Process has terminated
            exit_code = self.process.poll()
            self._append_log(f"\nProcess exited with code {exit_code}\n")
            self.run_button.setText("&Run")
            self.process = None
            self.activateWindow()
            self.feedback_text.setFocus()

    def _run_command(self):
        if self.process:
            kill_tree(self.process)
            self.process = None
            self.run_button.setText("&Run")
            return

        # Clear the log buffer but keep UI logs visible
        self.log_buffer = []

        command = self.command_entry.text()
        if not command:
            self._append_log("Please enter a command to run\n")
            return

        self._append_log(f"$ {command}\n")
        self.run_button.setText("Sto&p")

        try:
            self.process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.project_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=get_user_environment(),
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="ignore",
                close_fds=True,
            )

            def read_output(pipe):
                for line in iter(pipe.readline, ""):
                    self.log_signals.append_log.emit(line)

            threading.Thread(
                target=read_output,
                args=(self.process.stdout,),
                daemon=True
            ).start()

            threading.Thread(
                target=read_output,
                args=(self.process.stderr,),
                daemon=True
            ).start()

            # Start process status checking
            self.status_timer = QTimer()
            self.status_timer.timeout.connect(self._check_process_status)
            self.status_timer.start(100)  # Check every 100ms

        except Exception as e:
            self._append_log(f"Error running command: {str(e)}\n")
            self.run_button.setText("&Run")

    def _submit_feedback(self):
        self.feedback_result = FeedbackResult(
            logs="".join(self.log_buffer),
            interactive_feedback=self.feedback_text.toPlainText().strip(),
        )
        self.close()

    def _quick_reply_clicked(self, reply_text: str):
        """Handle quick reply text click - set text and optionally submit."""
        self.feedback_text.setPlainText(reply_text)
        if self.auto_submit_check.isChecked():
            self._submit_feedback()

    def clear_logs(self):
        self.log_buffer = []
        self.log_text.clear()

    def _save_config(self):
        # Save run_command and execute_automatically to QSettings under project group
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("run_command", self.config["run_command"])
        self.settings.setValue("execute_automatically", self.config["execute_automatically"])
        self.settings.endGroup()
        self._append_log("Configuration saved for this project.\n")

    def closeEvent(self, event):
        # Save general UI settings for the main window (geometry, state)
        self.settings.beginGroup("MainWindow_General")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.endGroup()

        # Save project-specific command section visibility (this is now slightly redundant due to immediate save in toggle, but harmless)
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("commandSectionVisible", self.command_group.isVisible())
        self.settings.endGroup()

        # Stop theme monitoring timer to prevent memory leaks
        if hasattr(self, 'theme_timer'):
            self.theme_timer.stop()
            self.theme_timer.deleteLater()

        if self.process:
            kill_tree(self.process)
        super().closeEvent(event)

    def run(self) -> FeedbackResult:
        self.show()
        QApplication.instance().exec()

        if self.process:
            kill_tree(self.process)

        if not self.feedback_result:
            return FeedbackResult(logs="".join(self.log_buffer), interactive_feedback="")

        return self.feedback_result

    def _check_system_theme_change(self):
        """Check if system theme has changed and update if in auto mode."""
        if self.theme_mode == "auto":
            current_system_dark = self._get_system_theme_is_dark()
            if current_system_dark != self.is_dark_theme:
                self.is_dark_theme = current_system_dark
                self.apply_theme()


def get_project_settings_group(project_dir: str) -> str:
    # Create a safe, unique group name from the project directory path
    # Using only the last component + hash of full path to keep it somewhat readable but unique
    basename = os.path.basename(os.path.normpath(project_dir))
    full_hash = hashlib.md5(project_dir.encode('utf-8')).hexdigest()[:8]
    return f"{basename}_{full_hash}"


def feedback_ui(project_directory: str, prompt: str, output_file: Optional[str] = None) -> Optional[FeedbackResult]:
    app = QApplication.instance() or QApplication()
    app.setStyle("Fusion")
    
    ui = FeedbackUI(project_directory, prompt)
    result = ui.run()

    if output_file and result:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        # Save the result to the output file
        with open(output_file, "w") as f:
            json.dump(result, f)
        return None

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the feedback UI")
    parser.add_argument("--project-directory", default=os.getcwd(), help="The project directory to run the command in")
    parser.add_argument("--prompt", default="I implemented the changes you requested.",
                        help="The prompt to show to the user")
    parser.add_argument("--output-file", help="Path to save the feedback result as JSON")
    args = parser.parse_args()

    result = feedback_ui(args.project_directory, args.prompt, args.output_file)
    if result:
        print(f"\nLogs collected: \n{result['logs']}")
        print(f"\nFeedback received:\n{result['interactive_feedback']}")
    sys.exit(0)
