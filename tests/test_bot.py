"""测试 TTS Bot 基础功能"""
import unittest
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

class TestTTSBot(unittest.TestCase):
    """TTS Bot 测试"""
    
    def test_import(self):
        """测试模块导入"""
        import tts_bot
        self.assertIsNotNone(tts_bot)
    
    def test_bot_module_exists(self):
        """测试 bot 模块存在"""
        from tts_bot import bot
        self.assertTrue(hasattr(bot, 'main'))

if __name__ == '__main__':
    unittest.main()
