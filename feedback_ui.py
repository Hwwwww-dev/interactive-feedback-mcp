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
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit, QGroupBox
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
        line-height: 1.5;
    }
    
    QLabel[class="section-title"] {
        color: rgb(161, 161, 170);
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
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
            self.resize(800, 600)
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - 800) // 2
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

        self._create_ui()  # self.config is used here to set initial values

        # Set command section visibility AFTER _create_ui has created relevant widgets
        self.command_group.setVisible(command_section_visible)
        if command_section_visible:
            self.toggle_command_button.setText("Hide Command Section")
        else:
            self.toggle_command_button.setText("Show Command Section")

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
        
        # Toggle Command Section Button (80% width)
        self.toggle_command_button = QPushButton("Show Command Section")
        self.toggle_command_button.setProperty("class", "secondary")
        self.toggle_command_button.clicked.connect(self._toggle_command_section)
        
        # Restore Default Size Button (20% width)
        self.restore_size_button = QPushButton("Reset Size")
        self.restore_size_button.setProperty("class", "secondary")
        self.restore_size_button.clicked.connect(self.restore_default_window_size)
        
        # Add buttons to layout with 8:2 ratio
        buttons_layout.addWidget(self.toggle_command_button, 9)
        buttons_layout.addWidget(self.restore_size_button, 1)
        
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
        self.description_label.setContentsMargins(0, 0, 0, 10)  # Add bottom margin
        feedback_layout.addWidget(self.description_label)

        self.feedback_text = FeedbackTextEdit()
        font_metrics = self.feedback_text.fontMetrics()
        row_height = font_metrics.height()
        # Calculate height for 3 lines + some padding for margins
        padding = self.feedback_text.contentsMargins().top() + self.feedback_text.contentsMargins().bottom() + 5  # 5 is extra vertical padding
        self.feedback_text.setMinimumHeight(3 * row_height + padding)

        self.feedback_text.setPlaceholderText("Enter your feedback here (Cmd+Enter to submit)")
        submit_button = QPushButton("&Send Feedback (Cmd+Enter)")
        submit_button.clicked.connect(self._submit_feedback)

        feedback_layout.addWidget(self.feedback_text)
        feedback_layout.addWidget(submit_button)

        # Set minimum height for feedback_group to accommodate its contents
        # This will be based on the section title, description label and the 3-line feedback_text
        self.feedback_group.setMinimumHeight(
            section_title.sizeHint().height() + self.description_label.sizeHint().height() + self.feedback_text.minimumHeight() + submit_button.sizeHint().height() + feedback_layout.spacing() * 3 + feedback_layout.contentsMargins().top() + feedback_layout.contentsMargins().bottom() + 10)  # 10 for extra padding

        # Add widgets in a specific order
        layout.addWidget(self.feedback_group)

    def _toggle_command_section(self):
        is_visible = self.command_group.isVisible()
        self.command_group.setVisible(not is_visible)
        if not is_visible:
            self.toggle_command_button.setText("Hide Command Section")
            # When command section becomes visible, call restore_default_window_size method
            self.restore_default_window_size()
        else:
            self.toggle_command_button.setText("Show Command Section")
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
            # Default size when command section is visible: 800x600
            default_width, default_height = 500, 900
        else:
            # Default size when command section is not visible: 500x500
            default_width, default_height = 500, 500
            
        # Calculate center position
        x = (screen.width() - default_width) // 2
        y = (screen.height() - default_height) // 2
        
        # Resize and move window
        self.resize(default_width, default_height)
        self.move(x, y)

    def _update_config(self):
        self.config["run_command"] = self.command_entry.text()
        self.config["execute_automatically"] = self.auto_check.isChecked()

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


def get_project_settings_group(project_dir: str) -> str:
    # Create a safe, unique group name from the project directory path
    # Using only the last component + hash of full path to keep it somewhat readable but unique
    basename = os.path.basename(os.path.normpath(project_dir))
    full_hash = hashlib.md5(project_dir.encode('utf-8')).hexdigest()[:8]
    return f"{basename}_{full_hash}"


def feedback_ui(project_directory: str, prompt: str, output_file: Optional[str] = None) -> Optional[FeedbackResult]:
    app = QApplication.instance() or QApplication()
    app.setPalette(get_dark_mode_palette(app))
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
