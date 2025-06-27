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
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QSettings, QMimeData
from PySide6.QtGui import QTextCursor, QIcon, QKeyEvent, QFont, QFontDatabase, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit, QGroupBox, QGridLayout
)

# Import bilingual text manager
from i18n import get_text_manager


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
    # Read stylesheet from file
    stylesheet_path = os.path.join(os.path.dirname(__file__), "feedback_dark_styles.qss")
    try:
        with open(stylesheet_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: Stylesheet file not found at {stylesheet_path}")
        return ""


def get_light_stylesheet():
    """Modern flat design stylesheet for light theme"""
    # Read stylesheet from file
    stylesheet_path = os.path.join(os.path.dirname(__file__), "feedback_light_styles.qss")
    try:
        with open(stylesheet_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: Stylesheet file not found at {stylesheet_path}")
        return ""


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
        if (event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier):
            # (event.key() == Qt.Key_Return and event.modifiers() == Qt.ShiftModifier):
            # Find the parent FeedbackUI instance and call submit
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                parent._submit_feedback()
        else:
            super().keyPressEvent(event)

    def insertFromMimeData(self, source: QMimeData) -> None:
        """
        Override to ensure only plain text is pasted.
        """
        if source.hasText():
            self.insertPlainText(source.text())
        # If not plain text, do nothing (discard other formats)


class LogSignals(QObject):
    append_log = Signal(str)


class FeedbackUI(QMainWindow):
    # Default window sizes (width, height)
    DEFAULT_WINDOW_SIZES = {
        "command_visible": (500, 1000),
        "command_hidden": (500, 600)
    }
    # Minimum window size (width, height)
    MINIMUM_WINDOW_SIZE = (500, 500)

    def __init__(self, project_directory: str, prompt: str):
        super().__init__()
        self.project_directory = project_directory
        self.prompt = prompt

        self.process: Optional[subprocess.Popen] = None
        self.log_buffer = []
        self.feedback_result = None
        self.log_signals = LogSignals()
        self.log_signals.append_log.connect(self._append_log)

        # Initialize bilingual text manager
        self.text_manager = get_text_manager()

        self.setWindowTitle(self.text_manager.get_text('window_titles', 'interactive_feedback'))
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "images", "feedback.png")
        self.setWindowIcon(QIcon(icon_path))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        # Create notification banner (initially hidden)
        self.notification_banner = None
        
        self.settings = QSettings("InteractiveFeedbackMCP", "InteractiveFeedbackMCP")
        
        # Load general UI settings for the main window (geometry, state)
        self.settings.beginGroup("MainWindow_General")
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # Use default size when no saved geometry
            default_width, default_height = self.DEFAULT_WINDOW_SIZES["command_hidden"]
            self.resize(default_width, default_height)
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - default_width) // 2
            y = (screen.height() - default_height) // 2
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
            self.toggle_command_button.setText(self.text_manager.get_text('buttons', 'hide_command_section'))
        else:
            self.toggle_command_button.setText(self.text_manager.get_text('buttons', 'command_section'))

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
        self.setWindowTitle(self.text_manager.get_text('window_titles', 'interactive_feedback'))
        self.setMinimumSize(*self.MINIMUM_WINDOW_SIZE) # Use the new constant
        
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
        self.toggle_command_button = QPushButton(self.text_manager.get_text('buttons', 'command_section'))
        self.toggle_command_button.setProperty("class", "secondary")
        self.toggle_command_button.clicked.connect(self._toggle_command_section)
        self.toggle_command_button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Restore Default Size Button (20% width)
        self.restore_size_button = QPushButton(self.text_manager.get_text('buttons', 'restore_size'))
        self.restore_size_button.setProperty("class", "secondary")
        self.restore_size_button.clicked.connect(self.restore_default_window_size)
        self.restore_size_button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Theme Toggle Button (10% width)
        theme_icon = self.text_manager.get_text('buttons', 'theme_auto') if self.theme_mode == "auto" else (self.text_manager.get_text('buttons', 'theme_dark') if self.theme_mode == "dark" else self.text_manager.get_text('buttons', 'theme_light'))
        self.theme_toggle_button = QPushButton(theme_icon)
        self.theme_toggle_button.setProperty("class", "secondary")
        self.theme_toggle_button.clicked.connect(self.toggle_theme)
        self.theme_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Language Toggle Button (10% width)
        current_lang = self.text_manager.get_current_language()
        language_text = self.text_manager.get_text('buttons', f'language_{current_lang}')
        self.language_toggle_button = QPushButton(language_text)
        self.language_toggle_button.setProperty("class", "secondary")
        self.language_toggle_button.clicked.connect(self.toggle_language)
        self.language_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        # Set tooltip to show language names
        if current_lang == 'zh':
            self.language_toggle_button.setToolTip("切换到 English")
        else:
            self.language_toggle_button.setToolTip("切换到中文")
        
        # Add buttons to layout with 7:1:1:1 ratio
        buttons_layout.addWidget(self.toggle_command_button, 7)
        buttons_layout.addWidget(self.restore_size_button, 1)
        buttons_layout.addWidget(self.theme_toggle_button, 1)
        buttons_layout.addWidget(self.language_toggle_button, 1)
        
        layout.addLayout(buttons_layout)

        # Command section
        self.command_group = QGroupBox(self.text_manager.get_text('group_titles', 'command'))
        command_layout = QVBoxLayout(self.command_group)
        command_layout.setSpacing(14)
        command_layout.setContentsMargins(16, 18, 16, 16)

        # Working directory label
        formatted_path = self._format_windows_path(self.project_directory)
        self.working_dir_label = QLabel(self.text_manager.get_text('labels', 'working_directory', path=formatted_path))
        self.working_dir_label.setProperty("class", "muted")
        self.working_dir_label.setWordWrap(True)
        command_layout.addWidget(self.working_dir_label)

        # Command input row
        command_input_layout = QHBoxLayout()
        command_input_layout.setSpacing(10)
        self.command_entry = QLineEdit()
        self.command_entry.setPlaceholderText(self.text_manager.get_text('placeholders', 'command_input'))
        self.command_entry.setText(self.config["run_command"])
        self.command_entry.returnPressed.connect(self._run_command)
        self.command_entry.textChanged.connect(self._update_config)
        self.run_button = QPushButton(self.text_manager.get_text('buttons', 'run'))
        self.run_button.clicked.connect(self._run_command)
        self.run_button.setCursor(Qt.CursorShape.PointingHandCursor)

        command_input_layout.addWidget(self.command_entry)
        command_input_layout.addWidget(self.run_button)
        command_layout.addLayout(command_input_layout)

        # Auto-execute and save config row
        auto_layout = QHBoxLayout()
        self.auto_check = QCheckBox(self.text_manager.get_text('checkboxes', 'execute_automatically'))
        self.auto_check.setProperty("class", "small-checkbox")
        self.auto_check.setChecked(self.config.get("execute_automatically", False))
        self.auto_check.stateChanged.connect(self._update_config)
        self.auto_check.setCursor(Qt.CursorShape.PointingHandCursor)

        self.save_button = QPushButton(self.text_manager.get_text('buttons', 'save_configuration'))
        self.save_button.setProperty("class", "secondary")
        self.save_button.clicked.connect(self._save_config)
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)

        auto_layout.addWidget(self.auto_check)
        auto_layout.addStretch()
        auto_layout.addWidget(self.save_button)
        command_layout.addLayout(auto_layout)

        # Console section (now part of command_group)
        self.console_group = QGroupBox(self.text_manager.get_text('group_titles', 'console'))
        console_layout_internal = QVBoxLayout(self.console_group)
        console_layout_internal.setSpacing(10)
        console_layout_internal.setContentsMargins(14, 14, 14, 14)
        self.console_group.setMinimumHeight(200)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        font.setPointSize(9)
        self.log_text.setFont(font)
        console_layout_internal.addWidget(self.log_text)

        # Clear button
        button_layout = QHBoxLayout()
        self.clear_button = QPushButton(self.text_manager.get_text('buttons', 'clear'))
        self.clear_button.setProperty("class", "secondary")
        self.clear_button.clicked.connect(self.clear_logs)
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        button_layout.addStretch()
        button_layout.addWidget(self.clear_button)
        console_layout_internal.addLayout(button_layout)

        command_layout.addWidget(self.console_group)

        self.command_group.setVisible(False)
        layout.addWidget(self.command_group)

        # Feedback section with adjusted height
        self.feedback_group = QGroupBox(self.text_manager.get_text('group_titles', 'feedback'))
        feedback_layout = QVBoxLayout(self.feedback_group)
        feedback_layout.setSpacing(14)
        feedback_layout.setContentsMargins(16, 18, 16, 16)

        # Section title
        self.section_title = QLabel(self.text_manager.get_text('labels', 'ai_assistant_summary'))
        self.section_title.setProperty("class", "section-title")
        feedback_layout.addWidget(self.section_title)

        # Short description label (from self.prompt)
        self.description_label = QLabel(f"""<p style="line-height: 1.4;">{self.prompt}</p>""")
        self.description_label.setProperty("class", "description")
        self.description_label.setWordWrap(True)
        self.description_label.setTextFormat(Qt.RichText)
        self.description_label.setContentsMargins(0, 0, 0, 12)  # Add bottom margin
        feedback_layout.addWidget(self.description_label)

        self.feedback_text = FeedbackTextEdit()
        font_metrics = self.feedback_text.fontMetrics()
        row_height = font_metrics.height()
        # Calculate height for 3 lines + some padding for margins
        padding = self.feedback_text.contentsMargins().top() + self.feedback_text.contentsMargins().bottom() + 5  # 5 is extra vertical padding
        self.feedback_text.setMinimumHeight(3 * row_height + padding)
        self.feedback_text.setPlaceholderText(self.text_manager.get_text('placeholders', 'feedback_input'))
        
        # Quick reply text links
        quick_reply_container = QVBoxLayout()
        quick_reply_container.setSpacing(6)
        quick_reply_container.setContentsMargins(0, 8, 0, 4)  # Add top and bottom margin
        
        # Add quick reply label with auto-submit checkbox
        quick_header_layout = QHBoxLayout()
        quick_header_layout.setSpacing(8)
        
        self.quick_label = QLabel(self.text_manager.get_text('labels', 'quick_reply'))
        self.quick_label.setProperty("class", "muted")
        quick_header_layout.addWidget(self.quick_label)
        
        self.auto_submit_check = QCheckBox(self.text_manager.get_text('labels', 'auto_submit'))
        self.auto_submit_check.setChecked(True)  # Default to auto-submit
        self.auto_submit_check.setProperty("class", "small-checkbox")
        self.auto_submit_check.setCursor(Qt.CursorShape.PointingHandCursor)
        quick_header_layout.addWidget(self.auto_submit_check)
        
        quick_header_layout.addStretch()
        quick_reply_container.addLayout(quick_header_layout)
        
        # Create quick reply text links in grid layout (2 per row)
        quick_grid = QGridLayout()
        quick_grid.setSpacing(4)
        quick_grid.setVerticalSpacing(2)
        
        # Get quick replies from text manager
        quick_replies = self.text_manager.get_quick_replies()
        for i, reply_text in enumerate(quick_replies):
            quick_label = QLabel(f"• {reply_text}")
            quick_label.setProperty("class", "quick-reply-text")
            quick_label.setCursor(Qt.CursorShape.PointingHandCursor)
            # Create a proper click handler to avoid closure issues
            def make_click_handler(text):
                return lambda event: self._quick_reply_clicked(text)
            
            quick_label.mousePressEvent = make_click_handler(reply_text)
            
            row = i // 2
            col = i % 2
            quick_grid.addWidget(quick_label, row, col)
        
        quick_reply_container.addLayout(quick_grid)
        
        self.submit_button = QPushButton(self.text_manager.get_text('buttons', 'send_feedback'))
        self.submit_button.clicked.connect(self._submit_feedback)
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)

        feedback_layout.addWidget(self.feedback_text)
        feedback_layout.addLayout(quick_reply_container)
        feedback_layout.addWidget(self.submit_button)

        # Set minimum height for feedback_group to accommodate its contents
        # This will be based on the section title, description label and the 3-line feedback_text
        self.feedback_group.setMinimumHeight(
            self.section_title.sizeHint().height() + self.description_label.sizeHint().height() + self.feedback_text.minimumHeight() + self.submit_button.sizeHint().height() + feedback_layout.spacing() * 3 + feedback_layout.contentsMargins().top() + feedback_layout.contentsMargins().bottom() + 10)  # 10 for extra padding

        # Add widgets in a specific order
        layout.addWidget(self.feedback_group)

        
        # Apply the theme after all widgets are created
        self.apply_theme()

    def _toggle_command_section(self):
        is_visible = self.command_group.isVisible()
        self.command_group.setVisible(not is_visible)
        if not is_visible:
            self.toggle_command_button.setText(self.text_manager.get_text('buttons', 'command_section'))
            # When command section becomes visible, call restore_default_window_size method
            self.restore_default_window_size()
        else:
            self.toggle_command_button.setText(self.text_manager.get_text('buttons', 'hide_command_section'))
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
            # Default size when command section is visible
            default_width, default_height = self.DEFAULT_WINDOW_SIZES["command_visible"]
        else:
            # Default size when command section is not visible
            default_width, default_height = self.DEFAULT_WINDOW_SIZES["command_hidden"]

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
                self.theme_toggle_button.setText(self.text_manager.get_text('buttons', 'theme_auto'))
            elif self.theme_mode == "dark":
                self.theme_toggle_button.setText(self.text_manager.get_text('buttons', 'theme_dark'))
            else:  # light
                self.theme_toggle_button.setText(self.text_manager.get_text('buttons', 'theme_light'))
        
        # Update language button text
        if hasattr(self, 'language_toggle_button'):
            self.update_language_button()

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

    def toggle_language(self):
        """Toggle between Chinese and English languages."""
        # Toggle language in text manager
        new_lang = self.text_manager.toggle_language()
        
        # Update language button text and tooltip
        self.update_language_button()
        
        # Show top notification banner
        if new_lang == 'zh':
            message = "语言已切换到中文，下次启动时界面将显示中文。"
        else:
            message = "Language switched to English, interface will be in English on next startup."
        
        self.show_notification_banner(message)



    def show_notification_banner(self, message: str):
        """Show a beautiful notification banner at the top of the window."""
        # Remove existing banner if any
        if self.notification_banner:
            self.notification_banner.deleteLater()
        
        # Create notification banner
        self.notification_banner = QLabel(message)
        self.notification_banner.setParent(self)
        self.notification_banner.setAlignment(Qt.AlignCenter)
        self.notification_banner.setWordWrap(True)
        
        # Apply CSS class for styling
        self.notification_banner.setProperty("class", "notification-banner")
        
        # Position banner at top center
        self.notification_banner.adjustSize()
        banner_width = min(self.notification_banner.width() + 40, self.width() - 40)
        banner_height = self.notification_banner.height()
        
        x = (self.width() - banner_width) // 2
        y = 20  # 20px from top
        
        self.notification_banner.setGeometry(x, y, banner_width, banner_height)
        self.notification_banner.show()
        
        # Auto-hide after 4 seconds with fade effect
        QTimer.singleShot(4000, self.hide_notification_banner)
    
    def hide_notification_banner(self):
        """Hide and remove the notification banner."""
        if self.notification_banner:
            self.notification_banner.hide()
            self.notification_banner.deleteLater()
            self.notification_banner = None

    def update_language_button(self):
        """Update language button text and tooltip."""
        current_lang = self.text_manager.get_current_language()
        language_text = self.text_manager.get_text('buttons', f'language_{current_lang}')
        self.language_toggle_button.setText(language_text)
        
        # Update tooltip
        if current_lang == 'zh':
            self.language_toggle_button.setToolTip("切换到 English")
        else:
            self.language_toggle_button.setToolTip("切换到中文")



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
            self._append_log(self.text_manager.get_text('messages', 'process_exited', code=exit_code))
            self.run_button.setText(self.text_manager.get_text('buttons', 'run'))
            self.process = None
            self.activateWindow()
            self.feedback_text.setFocus()

    def _run_command(self):
        if self.process:
            kill_tree(self.process)
            self.process = None
            self.run_button.setText(self.text_manager.get_text('buttons', 'run'))
            return

        # Clear the log buffer but keep UI logs visible
        self.log_buffer = []

        command = self.command_entry.text()
        if not command:
            self._append_log(self.text_manager.get_text('messages', 'enter_command'))
            return

        self._append_log(self.text_manager.get_text('messages', 'command_running', command=command))
        self.run_button.setText(self.text_manager.get_text('buttons', 'stop'))

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
            self._append_log(self.text_manager.get_text('messages', 'command_error', error=str(e)))
            self.run_button.setText(self.text_manager.get_text('buttons', 'run'))

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
        self._append_log(self.text_manager.get_text('messages', 'config_saved'))

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
