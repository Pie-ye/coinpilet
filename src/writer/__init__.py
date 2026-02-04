"""
寫作模組 (Brain) - 使用 GitHub Copilot SDK 生成市場分析文章
"""

from .writer import Writer, MockWriter, get_writer

__all__ = ["Writer", "MockWriter", "get_writer"]
