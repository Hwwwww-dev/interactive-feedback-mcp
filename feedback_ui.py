# Interactive Feedback MCP UI
# Developed by Fábio Ferreira (https://x.com/fabiomlferreira)
# Inspired by/related to dotcursorrules.com (https://dotcursorrules.com/)
import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
from typing import Optional, TypedDict
from io import BytesIO

import psutil
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QSettings, QMimeData, QUrl
from PySide6.QtGui import QTextCursor, QIcon, QKeyEvent, QFont, QFontDatabase, QPalette, QColor, QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit, QGroupBox, QGridLayout, QFileDialog, QMessageBox, QScrollArea, QFrame, QSizePolicy
)

# Import bilingual text manager
from i18n import get_text_manager


class FeedbackResult(TypedDict):
    command_logs: str
    interactive_feedback: str
    images: list[dict]  # List of {"filename": str, "data": str (base64)}
    text_files: list[dict]  # List of {"filename": str, "content": str, "path": str, "size": int, "encoding": str}


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


class FilePreviewWidget(QWidget):
    """Base widget for file preview with elegant design inspired by Cursor."""
    
    def __init__(self, file_data: dict, file_type: str, parent=None):
        super().__init__(parent)
        self.file_data = file_data
        self.file_type = file_type  # "image" or "text"
        self.parent_ui = parent
        self._setup_ui()
    
    def _setup_ui(self):
        # Use a fixed size for the entire widget to ensure consistent layout
        self.setFixedSize(140, 32)  # Optimal tab size
        
        # Main container
        container = QWidget(self)
        container.setGeometry(0, 0, 140, 32)
        container.setProperty("class", f"{self.file_type}-tab")
        
        # Create layout for container
        layout = QHBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)  # Equal margins
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignVCenter)  # Ensure all items are vertically centered
        
        # Small icon/thumbnail (16x16 like in Cursor)
        self.file_icon = QLabel()
        self.file_icon.setFixedSize(16, 16)
        self.file_icon.setScaledContents(True)
        self.file_icon.setProperty("class", f"{self.file_type}-tab-icon")
        
        # Load appropriate icon
        self._load_tab_icon()
        
        # Filename label (truncated to fit tab)
        self.filename_label = QLabel(self._get_tab_filename())
        self.filename_label.setProperty("class", f"{self.file_type}-tab-filename")
        self.filename_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # Add widgets to layout
        layout.addWidget(self.file_icon)
        layout.addWidget(self.filename_label)
        layout.addStretch()  # Push content to left
        
        # Set cursor to indicate clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        container.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filename_label.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def _get_tab_filename(self):
        """Get a tab-friendly filename with smart truncation for fixed-width tabs."""
        filename = self.file_data['filename']
        # For 140px tab width with icon and close button, we have about 70px for text (roughly 9-10 chars)
        if len(filename) > 10:
            name, ext = os.path.splitext(filename)
            if len(name) > 7:
                return f"{name[:7]}...{ext}"
        return filename
    
    def _load_tab_icon(self):
        """Load and display appropriate icon for the file type."""
        if self.file_type == "image":
            self._load_image_icon()
        else:  # text file
            self._load_text_file_icon()
    
    def _load_image_icon(self):
        """Load and display a small 16x16 icon for image files."""
        try:
            # Extract base64 data
            data_url = self.file_data['data']
            if data_url.startswith('data:image/'):
                # Split data URL: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...
                header, base64_data = data_url.split(',', 1)
                image_bytes = base64.b64decode(base64_data)
                
                # Create QPixmap from bytes
                pixmap = QPixmap()
                pixmap.loadFromData(image_bytes)
                
                if not pixmap.isNull():
                    # Scale to small 16x16 icon
                    icon_pixmap = pixmap.scaled(
                        16, 16, 
                        Qt.KeepAspectRatio, 
                        Qt.SmoothTransformation
                    )
                    self.file_icon.setPixmap(icon_pixmap)
                else:
                    # Use a generic image icon
                    self.file_icon.setText("🖼")
                    self.file_icon.setAlignment(Qt.AlignCenter)
            else:
                self.file_icon.setText("🖼")
                self.file_icon.setAlignment(Qt.AlignCenter)
        except Exception as e:
            print(f"Error loading image icon: {e}")
            self.file_icon.setText("🖼")
            self.file_icon.setAlignment(Qt.AlignCenter)
    
    def _load_text_file_icon(self):
        """Load and display appropriate icon for text files based on extension."""
        filename = self.file_data['filename']
        file_ext = os.path.splitext(filename.lower())[1]
        
        # Icon mapping for different file types
        icon_map = {
            '.py': '🐍', '.pyw': '🐍', '.pyi': '🐍',
            '.js': '🟨', '.jsx': '🟨', '.ts': '🔷', '.tsx': '🔷',
            '.java': '☕', '.c': '🔧', '.cpp': '🔧', '.h': '🔧',
            '.cs': '🔷', '.go': '🐹', '.rs': '🦀', '.swift': '🍎',
            '.php': '🐘', '.rb': '💎', '.kt': '🎯', '.scala': '🔺',
            '.html': '🌐', '.css': '🎨', '.xml': '📄', '.json': '📋',
            '.md': '📝', '.txt': '📄', '.sql': '🗃️', '.sh': '⚡',
            '.yaml': '⚙️', '.yml': '⚙️', '.toml': '⚙️', '.ini': '⚙️'
        }
        
        icon = icon_map.get(file_ext, '📄')  # Default to document icon
        self.file_icon.setText(icon)
        self.file_icon.setAlignment(Qt.AlignCenter)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click to remove file."""
        if event.button() == Qt.LeftButton:
            self._remove_file()
        super().mouseDoubleClickEvent(event)
    
    def _remove_file(self):
        """Remove this file from the parent widget."""
        if self.parent_ui and hasattr(self.parent_ui, 'feedback_text'):
            if self.file_type == "image":
                self.parent_ui.feedback_text._remove_image(self.file_data)
            else:  # text file
                self.parent_ui.feedback_text._remove_text_file(self.file_data)


class ImagePreviewWidget(FilePreviewWidget):
    """Modern widget to display image preview with elegant design inspired by Cursor."""
    
    def __init__(self, image_data: dict, parent=None):
        super().__init__(image_data, "image", parent)


class TextFilePreviewWidget(FilePreviewWidget):
    """Modern widget to display text file preview with elegant design inspired by Cursor."""
    
    def __init__(self, text_file_data: dict, parent=None):
        super().__init__(text_file_data, "text", parent)




class FeedbackTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.images = []  # Store image data as list of dicts
        self.text_files = []  # Store text file data as list of dicts

    def keyPressEvent(self, event: QKeyEvent):
        if (event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier):
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
        Override to handle both text and image pasting.
        """
        if source.hasImage():
            # Handle image from clipboard
            image = source.imageData()
            if image and not image.isNull():
                self._handle_image_paste(image)
        elif source.hasText():
            self.insertPlainText(source.text())
        # If not text or image, do nothing

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events for files."""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are supported files (image or text)
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if self._is_image_file(file_path) or self._is_text_file(file_path):
                        event.acceptProposedAction()
                        return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        """Handle drop events for supported files."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if self._is_image_file(file_path):
                        self._handle_image_file(file_path)
                        event.acceptProposedAction()
                        return
                    elif self._is_text_file(file_path):
                        self._handle_text_file(file_path)
                        event.acceptProposedAction()
                        return
        super().dropEvent(event)

    def _is_image_file(self, file_path: str) -> bool:
        """Check if file is a supported image format."""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type and mime_type.startswith('image/')
    
    def _is_text_file(self, file_path: str) -> bool:
        """Check if file is a supported text/code format."""
        # Define supported text file extensions
        text_extensions = {
            # Programming languages
            '.py', '.pyw', '.pyi',  # Python
            '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',  # JavaScript/TypeScript
            '.java',  # Java
            '.c', '.cpp', '.cxx', '.cc', '.h', '.hpp', '.hxx',  # C/C++
            '.cs', '.csx',  # C#
            '.go',  # Go
            '.rs',  # Rust
            '.swift',  # Swift
            '.kt', '.kts',  # Kotlin
            '.scala', '.sc',  # Scala
            '.rb', '.rbw',  # Ruby
            '.php', '.phtml',  # PHP
            '.pl', '.pm',  # Perl
            '.r', '.R',  # R
            '.m',  # MATLAB/Objective-C
            '.lua',  # Lua
            '.dart',  # Dart
            '.mm',  # Objective-C++
            
            # Web development
            '.html', '.htm', '.xhtml',  # HTML
            '.css', '.scss', '.sass', '.less', '.styl',  # CSS
            '.xml', '.xsl', '.xsd',  # XML
            '.json', '.jsonc',  # JSON
            '.yaml', '.yml',  # YAML
            '.toml',  # TOML
            
            # Scripts and config
            '.sh', '.bash', '.zsh', '.fish',  # Shell scripts
            '.ps1',  # PowerShell
            '.bat', '.cmd',  # Windows batch
            '.sql',  # SQL
            '.graphql', '.gql',  # GraphQL
            
            # Documents
            '.md', '.markdown', '.mdown', '.mdx',  # Markdown
            '.rst',  # reStructuredText
            '.tex', '.cls', '.sty',  # LaTeX
            '.txt', '.text',  # Plain text
            '.log',  # Log files
            
            # Config files
            '.ini', '.cfg', '.conf',  # INI/Config
            '.properties',  # Properties
            '.env', '.environment',  # Environment
        }
        
        file_ext = os.path.splitext(file_path.lower())[1]
        return file_ext in text_extensions or os.path.basename(file_path.lower()) in ['makefile', 'dockerfile']
    
    def _detect_encoding(self, file_path: str) -> str:
        """Detect file encoding."""
        try:
            import chardet
            with open(file_path, 'rb') as f:
                raw_data = f.read(10240)  # Read first 10KB for detection
                result = chardet.detect(raw_data)
                return result['encoding'] or 'utf-8'
        except ImportError:
            # Fallback without chardet
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin1']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        f.read(1024)  # Try to read first 1KB
                        return encoding
                except (UnicodeDecodeError, UnicodeError):
                    continue
            return 'utf-8'  # Final fallback
        except Exception:
            return 'utf-8'
    
    def _compress_image(self, image_data: bytes, max_size: int = 1024, quality: int = 75) -> tuple[bytes, str]:
        """
        Compress image to reduce file size while maintaining reasonable quality.
        
        Args:
            image_data: Original image bytes
            max_size: Maximum width/height in pixels
            quality: JPEG quality (1-100, lower = smaller file)
            
        Returns:
            Tuple of (compressed_bytes, format)
        """
        try:
            from PySide6.QtGui import QPixmap
            from PySide6.QtCore import QBuffer, QIODevice
            
            # Load image from bytes
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            
            if pixmap.isNull():
                return image_data, "PNG"  # Return original if can't process
            
            # Calculate new size while maintaining aspect ratio
            original_width = pixmap.width()
            original_height = pixmap.height()
            
            if original_width <= max_size and original_height <= max_size:
                # Image is already small enough, but still compress for quality
                new_pixmap = pixmap
            else:
                # Scale down image
                if original_width > original_height:
                    new_width = max_size
                    new_height = int(original_height * max_size / original_width)
                else:
                    new_height = max_size
                    new_width = int(original_width * max_size / original_height)
                
                new_pixmap = pixmap.scaled(
                    new_width, new_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            
            # Save as JPEG for better compression (unless it's a PNG with transparency)
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            
            # Determine output format
            if self._has_transparency(image_data):
                # Keep PNG for images with transparency
                new_pixmap.save(buffer, "PNG")
                return buffer.data().data(), "PNG"
            else:
                # Use JPEG for better compression
                new_pixmap.save(buffer, "JPEG", quality)
                return buffer.data().data(), "JPEG"
                
        except Exception as e:
            print(f"Error compressing image: {e}")
            return image_data, "PNG"  # Return original if compression fails
    
    def _has_transparency(self, image_data: bytes) -> bool:
        """Check if image has transparency (alpha channel)."""
        try:
            # Check PNG signature and look for transparency
            if image_data.startswith(b'\x89PNG\r\n\x1a\n'):
                # Simple check for PNG transparency - look for tRNS chunk or RGBA color type
                return b'tRNS' in image_data[:1000] or b'RGBA' in image_data[:100]
            return False
        except:
            return False

    def _handle_image_paste(self, image: QPixmap):
        """Handle image pasted from clipboard."""
        try:
            # Check image limit (maximum 5 images)
            if len(self.images) >= 5:
                parent = self.parent()
                while parent and not isinstance(parent, FeedbackUI):
                    parent = parent.parent()
                if parent:
                    parent._show_error_message("max_images_reached")
                return
            
            # Convert QPixmap to bytes first
            from PySide6.QtCore import QBuffer, QIODevice
            from PySide6.QtGui import QPixmap
            
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            image.save(buffer, "PNG")
            original_data = buffer.data().data()
            
            # Compress the image
            compressed_data, image_format = self._compress_image(original_data)
            base64_data = base64.b64encode(compressed_data).decode('utf-8')
            
            # Determine file extension based on format
            file_ext = "jpg" if image_format == "JPEG" else "png"
            
            # Create image entry
            image_entry = {
                "filename": f"clipboard_image_{len(self.images) + 1}.{file_ext}",
                "data": f"data:image/{image_format.lower()};base64,{base64_data}"
            }
            
            self.images.append(image_entry)
            
            # Insert placeholder text with proper formatting
            placeholder = f"[图片: {image_entry['filename']}]"
            cursor = self.textCursor()
            # If not at the beginning of a line, add a newline before
            if cursor.positionInBlock() > 0:
                self.insertPlainText("\n")
            self.insertPlainText(placeholder)
            # Add a newline after the placeholder
            self.insertPlainText("\n")
            
            # Get parent FeedbackUI to show notification and update previews
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                # Calculate compression ratio
                original_size = len(original_data)
                compressed_size = len(compressed_data)
                compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                
                parent._show_image_notification(image_entry['filename'], compression_ratio)
                parent._update_file_previews()
                
        except Exception as e:
            print(f"Error handling image paste: {e}")

    def _handle_image_file(self, file_path: str):
        """Handle image file dropped or selected."""
        try:
            # Check image limit (maximum 5 images)
            if len(self.images) >= 5:
                parent = self.parent()
                while parent and not isinstance(parent, FeedbackUI):
                    parent = parent.parent()
                if parent:
                    parent._show_error_message("max_images_reached")
                return
            
            # Check file size (10MB limit)
            file_size = os.path.getsize(file_path)
            if file_size > 10 * 1024 * 1024:  # 10MB
                parent = self.parent()
                while parent and not isinstance(parent, FeedbackUI):
                    parent = parent.parent()
                if parent:
                    parent._show_error_message("image_too_large")
                return
            
            # Read and compress image
            with open(file_path, 'rb') as f:
                original_data = f.read()
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type or not mime_type.startswith('image/'):
                parent = self.parent()
                while parent and not isinstance(parent, FeedbackUI):
                    parent = parent.parent()
                if parent:
                    parent._show_error_message("invalid_image_format")
                return
            
            # Compress the image
            compressed_data, image_format = self._compress_image(original_data)
            base64_data = base64.b64encode(compressed_data).decode('utf-8')
            
            # Update filename extension if format changed
            original_filename = os.path.basename(file_path)
            name_without_ext = os.path.splitext(original_filename)[0]
            file_ext = "jpg" if image_format == "JPEG" else "png"
            final_filename = f"{name_without_ext}.{file_ext}"
            
            # Create image entry
            image_entry = {
                "filename": final_filename,
                "data": f"data:image/{image_format.lower()};base64,{base64_data}"
            }
            
            self.images.append(image_entry)
            
            # Insert placeholder text with proper formatting
            placeholder = f"[图片: {final_filename}]"
            cursor = self.textCursor()
            # If not at the beginning of a line, add a newline before
            if cursor.positionInBlock() > 0:
                self.insertPlainText("\n")
            self.insertPlainText(placeholder)
            # Add a newline after the placeholder
            self.insertPlainText("\n")
            
            # Get parent FeedbackUI to show notification and update previews
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                # Calculate compression ratio
                original_size = len(original_data)
                compressed_size = len(compressed_data)
                compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                
                parent._show_image_notification(final_filename, compression_ratio)
                parent._update_file_previews()
                
        except Exception as e:
            print(f"Error handling image file: {e}")

    def _handle_text_file(self, file_path: str):
        """Handle text file dropped or selected."""
        try:
            # Check text file limit (maximum 5 text files)
            if len(self.text_files) >= 5:
                parent = self.parent()
                while parent and not isinstance(parent, FeedbackUI):
                    parent = parent.parent()
                if parent:
                    parent._show_error_message("max_text_files_reached")
                return
            
            # Check file size (5MB limit for text files)
            file_size = os.path.getsize(file_path)
            if file_size > 5 * 1024 * 1024:  # 5MB
                parent = self.parent()
                while parent and not isinstance(parent, FeedbackUI):
                    parent = parent.parent()
                if parent:
                    parent._show_error_message("text_file_too_large")
                return
            
            # Detect encoding and read file content
            encoding = self._detect_encoding(file_path)
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Fallback to utf-8 with error handling
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                encoding = 'utf-8'
            
            # Create text file entry
            filename = os.path.basename(file_path)
            text_file_entry = {
                "filename": filename,
                "content": content,
                "path": os.path.abspath(file_path),
                "size": file_size,
                "encoding": encoding
            }
            
            self.text_files.append(text_file_entry)
            
            # Insert placeholder text with proper formatting
            placeholder = f"[代码文件: {filename}]"
            cursor = self.textCursor()
            # If not at the beginning of a line, add a newline before
            if cursor.positionInBlock() > 0:
                self.insertPlainText("\n")
            self.insertPlainText(placeholder)
            # Add a newline after the placeholder
            self.insertPlainText("\n")
            
            # Get parent FeedbackUI to show notification and update previews
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                parent._show_text_file_notification(filename, file_size)
                parent._update_file_previews()
                
        except Exception as e:
            print(f"Error handling text file: {e}")

    def get_images(self) -> list[dict]:
        """Get all images as list of dicts."""
        return self.images.copy()

    def get_text_files(self) -> list[dict]:
        """Get all text files as list of dicts."""
        return self.text_files.copy()

    def clear_images(self):
        """Clear all images."""
        self.images.clear()
    
    def clear_text_files(self):
        """Clear all text files."""
        self.text_files.clear()
    
    def _remove_image(self, image_data: dict):
        """Remove a specific image from the list."""
        if image_data in self.images:
            self.images.remove(image_data)
            
            # Remove placeholder text from the text edit
            text = self.toPlainText()
            placeholder = f"[图片: {image_data['filename']}]"
            # Remove the placeholder and clean up extra whitespace
            updated_text = text.replace(placeholder, "")
            # Clean up multiple consecutive newlines
            updated_text = re.sub(r'\n\s*\n\s*\n', '\n\n', updated_text)
            updated_text = updated_text.strip()
            self.setPlainText(updated_text)
            
            # Notify parent to update preview
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                parent._update_file_previews()
    
    def _remove_text_file(self, text_file_data: dict):
        """Remove a specific text file from the list."""
        if text_file_data in self.text_files:
            self.text_files.remove(text_file_data)
            
            # Remove placeholder text from the text edit
            text = self.toPlainText()
            placeholder = f"[代码文件: {text_file_data['filename']}]"
            # Remove the placeholder and clean up extra whitespace
            updated_text = text.replace(placeholder, "")
            # Clean up multiple consecutive newlines
            updated_text = re.sub(r'\n\s*\n\s*\n', '\n\n', updated_text)
            updated_text = updated_text.strip()
            self.setPlainText(updated_text)
            
            # Notify parent to update preview
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                parent._update_file_previews()


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
        
        # 设置窗口图标，添加存在性检查和调试信息
        print(f"Debug: Looking for icon at: {icon_path}")
        if os.path.exists(icon_path):
            print(f"Debug: Icon file exists")
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.setWindowIcon(icon)
                # 在macOS上设置应用程序图标到Dock
                app = QApplication.instance()
                if app:
                    app.setWindowIcon(icon)
                    if sys.platform == "darwin":
                        # macOS上设置应用程序图标
                        app.setApplicationDisplayName("Interactive Feedback")
                print(f"Debug: Icon loaded successfully and set for application")
            else:
                print(f"Warning: Icon file exists but failed to load: {icon_path}")
        else:
            print(f"Warning: Icon file not found: {icon_path}")
            # 列出当前目录内容以便调试
            script_dir = os.path.dirname(os.path.abspath(__file__))
            images_dir = os.path.join(script_dir, "images")
            if os.path.exists(images_dir):
                print(f"Debug: Images directory contents: {os.listdir(images_dir)}")
            else:
                print(f"Debug: Images directory not found: {images_dir}")
        # 设置窗口标志：根据保存的置顶状态设置
        # 在macOS上，需要使用不同的方法
        if sys.platform == "darwin":  # macOS
            # macOS上使用不同的窗口标志组合
            # 不使用WindowStaysOnTopHint，而是在显示后设置置顶
            flags = Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
            self.setWindowFlags(flags)
            print(f"Debug: macOS window flags set without StaysOnTop")
        else:
            # Windows和Linux上根据保存的置顶状态设置标志
            flags = Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
            if self.stay_on_top:
                flags |= Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            # Window flags set based on stay_on_top preference
        
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
        
        # Stay on top management
        self.stay_on_top = self.settings.value("stay_on_top", False, type=bool)
        
        # Project path display management
        self.show_full_path = False  # Default to show project name only
        
        # File management
        self.images = []
        self.text_files = []
        self.file_preview_widgets = []

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
        
        # Apply initial stay on top setting
        if self.stay_on_top:
            self._apply_stay_on_top()

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
    
    def _get_project_name(self) -> str:
        """Extract project name from project directory path."""
        return os.path.basename(os.path.normpath(self.project_directory))
    
    def _update_project_path_display(self):
        """Update the bottom project path label based on current display mode."""
        if self.show_full_path:
            # Show full path
            formatted_path = self._format_windows_path(self.project_directory)
            text = self.text_manager.get_text('labels', 'project_path', path=formatted_path)
        else:
            # Show project name only
            project_name = self._get_project_name()
            text = self.text_manager.get_text('labels', 'project_name', name=project_name)
        
        if hasattr(self, 'bottom_path_label'):
            self.bottom_path_label.setText(text)
    
    def _toggle_project_path_display(self):
        """Toggle between project name and full path display."""
        self.show_full_path = not self.show_full_path
        self._update_project_path_display()

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

        
        # Stay on Top Toggle Button (10% width)
        stay_on_top_icon = self.text_manager.get_text('buttons', 'stay_on_top_on' if self.stay_on_top else 'stay_on_top_off')
        self.stay_on_top_button = QPushButton(stay_on_top_icon)
        self.stay_on_top_button.setProperty("class", "secondary")
        self.stay_on_top_button.clicked.connect(self.toggle_stay_on_top)
        self.stay_on_top_button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Add buttons to layout with 6:1:1:1:1 ratio
        buttons_layout.addWidget(self.toggle_command_button, 6)
        buttons_layout.addWidget(self.restore_size_button, 1)
        buttons_layout.addWidget(self.theme_toggle_button, 1)
        buttons_layout.addWidget(self.language_toggle_button, 1)
        buttons_layout.addWidget(self.stay_on_top_button, 1)
        
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
        # Enable text selection for copy functionality
        self.description_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
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
        
        # Image and submit button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Add file button (images and text files)
        self.add_file_button = QPushButton(self.text_manager.get_text('buttons', 'add_file'))
        self.add_file_button.setProperty("class", "secondary")
        self.add_file_button.clicked.connect(self._add_file)
        self.add_file_button.setCursor(Qt.CursorShape.PointingHandCursor)

        
        self.submit_button = QPushButton(self.text_manager.get_text('buttons', 'send_feedback'))
        self.submit_button.clicked.connect(self._submit_feedback)
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        button_layout.addWidget(self.add_file_button)
        button_layout.addStretch()
        button_layout.addWidget(self.submit_button)

        feedback_layout.addWidget(self.feedback_text)
        feedback_layout.addLayout(quick_reply_container)
        
        # File preview area (horizontal flex layout, no scroll)
        self.file_preview_container = QWidget()
        self.file_preview_container.setVisible(False)  # Initially hidden
        self.file_preview_container.setProperty("class", "file-preview-container")
        
        self.file_layout = QHBoxLayout(self.file_preview_container)
        self.file_layout.setContentsMargins(12, 8, 12, 8)
        self.file_layout.setSpacing(12)
        self.file_layout.setAlignment(Qt.AlignLeft)
        
        feedback_layout.addWidget(self.file_preview_container)
        
        feedback_layout.addLayout(button_layout)

        # Set minimum height for feedback_group to accommodate its contents
        # This will be based on the section title, description label and the 3-line feedback_text
        self.feedback_group.setMinimumHeight(
            self.section_title.sizeHint().height() + self.description_label.sizeHint().height() + self.feedback_text.minimumHeight() + self.submit_button.sizeHint().height() + feedback_layout.spacing() * 3 + feedback_layout.contentsMargins().top() + feedback_layout.contentsMargins().bottom() + 10)  # 10 for extra padding

        # Add widgets in a specific order
        layout.addWidget(self.feedback_group)

        # Bottom project path display
        # Initialize with project name (default display mode)
        project_name = self._get_project_name()
        self.bottom_path_label = QLabel(self.text_manager.get_text('labels', 'project_name', name=project_name))
        self.bottom_path_label.setProperty("class", "muted")
        self.bottom_path_label.setAlignment(Qt.AlignCenter)
        self.bottom_path_label.setWordWrap(True)
        self.bottom_path_label.setContentsMargins(8, 4, 8, 4)
        # Enable click functionality
        self.bottom_path_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bottom_path_label.mousePressEvent = lambda event: self._toggle_project_path_display()
        layout.addWidget(self.bottom_path_label)
        
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
        
        # Update language button text
        self.update_language_button()
        
        # Update bottom project path label
        if hasattr(self, 'bottom_path_label'):
            self._update_project_path_display()
        

        

        
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
        """Update language button text."""
        current_lang = self.text_manager.get_current_language()
        language_text = self.text_manager.get_text('buttons', f'language_{current_lang}')
        self.language_toggle_button.setText(language_text)
    
    def toggle_stay_on_top(self):
        """Toggle window stay on top state."""
        self.stay_on_top = not self.stay_on_top
        self._apply_stay_on_top()
        
        # Update button icon
        stay_on_top_icon = self.text_manager.get_text('buttons', 'stay_on_top_on' if self.stay_on_top else 'stay_on_top_off')
        self.stay_on_top_button.setText(stay_on_top_icon)
        
        # Save preference
        self.settings.setValue("stay_on_top", self.stay_on_top)
    

    
    def _apply_stay_on_top(self):
        """Apply stay on top setting to the window."""
        # Get current window state
        was_visible = self.isVisible()
        current_pos = self.pos()
        current_size = self.size()
        
        # Update window flags
        flags = self.windowFlags()
        if self.stay_on_top:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        
        # Apply new flags with minimal flicker
        if was_visible:
            # Temporarily hide to avoid flicker
            self.hide()
        
        self.setWindowFlags(flags)
        
        # Restore position and size
        self.move(current_pos)
        self.resize(current_size)
        
        if was_visible:
            self.show()
            if self.stay_on_top and sys.platform == "darwin":
                # Additional raise for macOS
                self.raise_()
                self.activateWindow()
    
    def _add_file(self):
        """Open file dialog to select a file (image or text)."""
        # Check file limits before opening dialog
        images_count = len(self.feedback_text.get_images())
        text_files_count = len(self.feedback_text.get_text_files())
        
        if images_count >= 5 and text_files_count >= 5:
            self._show_error_message("max_files_reached")
            return
        
        file_dialog = QFileDialog(self)
        file_dialog.setWindowTitle(self.text_manager.get_text('messages', 'select_file'))
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        
        # Comprehensive file filter
        file_filter = (
            "All Supported Files ("
            "*.png *.jpg *.jpeg *.gif *.bmp *.webp "  # Images
            "*.py *.pyw *.pyi *.js *.jsx *.ts *.tsx *.mjs *.cjs "  # Python, JavaScript/TypeScript
            "*.java *.c *.cpp *.cxx *.cc *.h *.hpp *.hxx *.cs *.csx "  # Java, C/C++, C#
            "*.go *.rs *.swift *.kt *.kts *.scala *.sc *.rb *.rbw "  # Go, Rust, Swift, Kotlin, Scala, Ruby
            "*.php *.phtml *.pl *.pm *.r *.R *.m *.lua *.dart *.mm "  # PHP, Perl, R, MATLAB, Lua, Dart, Objective-C++
            "*.html *.htm *.xhtml *.css *.scss *.sass *.less *.styl "  # Web files
            "*.xml *.xsl *.xsd *.json *.jsonc *.yaml *.yml *.toml "  # Data files
            "*.sh *.bash *.zsh *.fish *.ps1 *.bat *.cmd *.sql *.graphql *.gql "  # Scripts
            "*.md *.markdown *.mdown *.mdx *.rst *.tex *.cls *.sty *.txt *.text *.log "  # Documents
            "*.ini *.cfg *.conf *.properties *.env *.environment "  # Config files
            ");;"
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;"
            "Source Code ("
            "*.py *.pyw *.pyi *.js *.jsx *.ts *.tsx *.mjs *.cjs *.java *.c *.cpp *.cxx *.cc *.h *.hpp *.hxx "
            "*.cs *.csx *.go *.rs *.swift *.kt *.kts *.scala *.sc *.rb *.rbw *.php *.phtml *.pl *.pm "
            "*.r *.R *.m *.lua *.dart *.mm"
            ");;"
            "Web Files (*.html *.htm *.xhtml *.css *.scss *.sass *.less *.styl *.xml *.xsl *.xsd *.json *.jsonc *.yaml *.yml *.toml);;"
            "Scripts (*.sh *.bash *.zsh *.fish *.ps1 *.bat *.cmd *.sql *.graphql *.gql);;"
            "Documents (*.md *.markdown *.mdown *.mdx *.rst *.tex *.cls *.sty *.txt *.text *.log);;"
            "Config Files (*.ini *.cfg *.conf *.properties *.env *.environment)"
        )
        
        file_dialog.setNameFilter(file_filter)
        
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                file_path = selected_files[0]
                # Automatically detect file type and handle accordingly
                if self.feedback_text._is_image_file(file_path):
                    if images_count >= 5:
                        self._show_error_message("max_images_reached")
                        return
                    self.feedback_text._handle_image_file(file_path)
                elif self.feedback_text._is_text_file(file_path):
                    if text_files_count >= 5:
                        self._show_error_message("max_text_files_reached")
                        return
                    self.feedback_text._handle_text_file(file_path)
                else:
                    self._show_error_message("unsupported_file_type")
    
    def _show_image_notification(self, filename: str, compression_ratio: float = 0):
        """Show notification that image was added with compression info."""
        if compression_ratio > 10:  # Only show compression info if significant
            if self.text_manager.get_current_language() == 'zh':
                message = f"图片已添加: {filename} (压缩了 {compression_ratio:.0f}%)"
            else:
                message = f"Image added: {filename} (compressed {compression_ratio:.0f}%)"
        else:
            message = self.text_manager.get_text('messages', 'image_added', filename=filename)
        self.show_notification_banner(message)
    
    def _show_text_file_notification(self, filename: str, file_size: int):
        """Show notification that text file was added."""
        # Format file size
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        
        if self.text_manager.get_current_language() == 'zh':
            message = f"代码文件已添加: {filename} ({size_str})"
        else:
            message = f"Text file added: {filename} ({size_str})"
        self.show_notification_banner(message)
    
    def _show_error_message(self, error_key: str):
        """Show error message dialog."""
        error_message = self.text_manager.get_text('messages', error_key)
        QMessageBox.warning(self, "Error", error_message)
    
    def _update_file_previews(self):
        """Update the file preview area with horizontal flex-like layout."""
        # Clear existing preview widgets
        for widget in self.file_preview_widgets:
            self.file_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self.file_preview_widgets.clear()
        
        # Clear all items from layout
        while self.file_layout.count():
            item = self.file_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.spacerItem():
                # Remove spacer items
                pass
        
        # Get current files from feedback_text
        images = self.feedback_text.get_images()
        text_files = self.feedback_text.get_text_files()
        
        if images or text_files:
            # Show preview container
            self.file_preview_container.setVisible(True)
            
            # Add image preview widgets in horizontal layout
            for image_data in images:
                preview_widget = ImagePreviewWidget(image_data, self)
                self.file_layout.addWidget(preview_widget)
                self.file_preview_widgets.append(preview_widget)
            
            # Add text file preview widgets in horizontal layout
            for text_file_data in text_files:
                preview_widget = TextFilePreviewWidget(text_file_data, self)
                self.file_layout.addWidget(preview_widget)
                self.file_preview_widgets.append(preview_widget)
            
            # Add stretch to push items to the left (flex-start behavior)
            self.file_layout.addStretch()
        else:
            # Hide preview container if no files
            self.file_preview_container.setVisible(False)



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
            images=self.feedback_text.get_images(),
            text_files=self.feedback_text.get_text_files()
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
        
        # 在macOS上，窗口显示后设置置顶
        if sys.platform == "darwin":
            self.raise_()
            self.activateWindow()
            print(f"Debug: macOS window raised and activated")
        
        QApplication.instance().exec()

        if self.process:
            kill_tree(self.process)

        if not self.feedback_result:
            return FeedbackResult(logs="".join(self.log_buffer), interactive_feedback="", images=[], text_files=[])

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
