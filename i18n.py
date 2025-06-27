# I18N Manager for Interactive Feedback MCP
# 交互式反馈 MCP 国际化管理器
# Developed by Claude Sonnet 4 - Created for seamless Chinese-English UI support

import os
import sys
import json
import locale
from typing import Dict, Any, Optional
from PySide6.QtCore import QSettings


class I18NManager:
    """
    国际化管理器
    Internationalization Manager for handling Chinese and English UI texts
    """
    
    def __init__(self, default_language: str = "auto"):
        """
        初始化国际化管理器
        Initialize the internationalization manager
        
        Args:
            default_language: "zh", "en", or "auto" for system detection
        """
        self.current_language = "en"  # Default fallback
        self.settings = QSettings("InteractiveFeedbackMCP", "I18NManager")
        
        # Load saved language preference or detect system language
        if default_language == "auto":
            saved_lang = self.settings.value("language", "auto", type=str)
            if saved_lang == "auto":
                self.current_language = self._detect_system_language()
            else:
                self.current_language = saved_lang
        else:
            self.current_language = default_language
        
        # Initialize text dictionaries
        self._init_texts()
    
    def _detect_system_language(self) -> str:
        """
        检测系统语言
        Detect system language
        
        Returns:
            "zh" for Chinese, "en" for English
        """
        try:
            # Get system locale
            system_locale = locale.getdefaultlocale()[0]
            if system_locale:
                if system_locale.startswith(('zh_', 'zh-')):
                    return "zh"
            
            # Alternative detection methods
            if sys.platform == "darwin":  # macOS
                try:
                    import subprocess
                    result = subprocess.run(
                        ["defaults", "read", "-g", "AppleLanguages"],
                        capture_output=True, text=True, timeout=2
                    )
                    if "zh" in result.stdout.lower():
                        return "zh"
                except:
                    pass
            
            elif sys.platform == "win32":  # Windows
                try:
                    import ctypes
                    windll = ctypes.windll.kernel32
                    language_id = windll.GetUserDefaultUILanguage()
                    # Chinese language IDs: 0x0404 (Traditional), 0x0804 (Simplified)
                    if language_id in [0x0404, 0x0804]:
                        return "zh"
                except:
                    pass
            
        except Exception:
            pass
        
        # Default to English if detection fails
        return "en"
    
    def _init_texts(self):
        """
        初始化所有文本字典
        Initialize all text dictionaries
        """
        self.texts = {}
        if not os.path.exists("i18n.json"):
            raise FileNotFoundError("i18n.json not found")
        with open("i18n.json", "r", encoding="utf-8") as f:
            self.texts = json.load(f)
    
    def get_text(self, category: str, key: str, **kwargs) -> str:
        """
        获取指定类别和键的文本
        Get text for specified category and key
        
        Args:
            category: Text category (e.g., 'buttons', 'labels')
            key: Text key within the category
            **kwargs: Format parameters for the text
            
        Returns:
            Localized text string
        """
        try:
            text = self.texts[category][self.current_language][key]
            if kwargs:
                return text.format(**kwargs)
            return text
        except KeyError:
            # Fallback to English if current language text not found
            try:
                text = self.texts[category]["en"][key]
                if kwargs:
                    return text.format(**kwargs)
                return text
            except KeyError:
                # Last resort: return the key itself
                return f"[{category}.{key}]"
    
    def get_quick_replies(self) -> list:
        """
        获取快速回复选项
        Get quick reply options
        
        Returns:
            List of quick reply strings in current language
        """
        try:
            return self.texts["quick_replies"][self.current_language]
        except KeyError:
            return self.texts["quick_replies"]["en"]
    

    
    def set_language(self, language: str) -> None:
        """
        设置当前语言
        Set current language
        
        Args:
            language: "zh" for Chinese, "en" for English
        """
        if language in ["zh", "en"]:
            self.current_language = language
            # Save language preference
            self.settings.setValue("language", language)
    
    def get_current_language(self) -> str:
        """
        获取当前语言
        Get current language
        
        Returns:
            Current language code ("zh" or "en")
        """
        return self.current_language
    
    def toggle_language(self) -> str:
        """
        切换语言
        Toggle between Chinese and English
        
        Returns:
            New current language code
        """
        new_lang = "en" if self.current_language == "zh" else "zh"
        self.set_language(new_lang)
        return new_lang
    
    def get_available_languages(self) -> Dict[str, str]:
        """
        获取可用语言列表
        Get available languages
        
        Returns:
            Dictionary mapping language codes to display names
        """
        return {
            "zh": "中文",
            "en": "English"
        }
    
    def export_texts(self, filepath: str) -> bool:
        """
        导出文本到JSON文件
        Export texts to JSON file
        
        Args:
            filepath: Path to save the JSON file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.texts, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error exporting texts: {e}")
            return False
    
    def import_texts(self, filepath: str) -> bool:
        """
        从JSON文件导入文本
        Import texts from JSON file
        
        Args:
            filepath: Path to the JSON file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.texts = json.load(f)
            return True
        except Exception as e:
            print(f"Error importing texts: {e}")
            return False


# Convenience functions for easy access
# 便捷函数，方便访问

# Global instance - will be initialized when first imported
_text_manager: Optional[I18NManager] = None

def get_text_manager() -> I18NManager:
    """
    获取全局国际化管理器实例
    Get global internationalization manager instance
    """
    global _text_manager
    if _text_manager is None:
        _text_manager = I18NManager()
    return _text_manager

def get_text(category: str, key: str, **kwargs) -> str:
    """
    便捷函数：获取文本
    Convenience function: get text
    """
    return get_text_manager().get_text(category, key, **kwargs)

def set_language(language: str) -> None:
    """
    便捷函数：设置语言
    Convenience function: set language
    """
    get_text_manager().set_language(language)

def toggle_language() -> str:
    """
    便捷函数：切换语言
    Convenience function: toggle language
    """
    return get_text_manager().toggle_language()

def get_current_language() -> str:
    """
    便捷函数：获取当前语言
    Convenience function: get current language
    """
    return get_text_manager().get_current_language()


# Example usage and testing
if __name__ == "__main__":
    print("=== I18N Manager Test ===")
    print("=== 国际化管理器测试 ===\n")
    
    # Test basic functionality
    tm = I18NManager("auto")
    print(f"Detected language: {tm.get_current_language()}")
    print(f"检测到的语言: {tm.get_current_language()}\n")
    
    # Test text retrieval in both languages
    for lang in ["en", "zh"]:
        print(f"--- Testing {lang} ---")
        tm.set_language(lang)
        
        print(f"Window title: {tm.get_text('window_titles', 'main_title')}")
        print(f"Run button: {tm.get_text('buttons', 'run')}")
        print(f"Working dir: {tm.get_text('labels', 'working_directory', path='/test/path')}")
        print(f"Quick replies: {tm.get_quick_replies()}")
        print()
    
    # Test language toggle
    print("--- Language Toggle Test ---")
    current = tm.get_current_language()
    print(f"Current: {current}")
    new_lang = tm.toggle_language()
    print(f"After toggle: {new_lang}")
    print(f"Button text: {tm.get_text('buttons', 'run')}")
    
    print("\n=== Test completed ===")
    print("=== 测试完成 ===") 