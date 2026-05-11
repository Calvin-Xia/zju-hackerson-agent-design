import asyncio
import logging
from pathlib import Path
from typing import Dict, Type

from src.models.textbook import Textbook
from src.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# 解析器注册表
_PARSERS: Dict[str, Type[BaseParser]] = {}


def register_parser(extension: str, parser_class: Type[BaseParser]):
    """注册解析器"""
    _PARSERS[extension.lower()] = parser_class


def get_parser(extension: str) -> BaseParser:
    """获取解析器实例"""
    ext = extension.lower().lstrip('.')
    if ext not in _PARSERS:
        raise ValueError(f"Unsupported file format: {ext}")
    return _PARSERS[ext]()


async def parse_file(file_path: Path) -> Textbook:
    """异步解析文件"""
    extension = file_path.suffix.lstrip('.')
    parser = get_parser(extension)
    
    result = await asyncio.to_thread(parser.parse, file_path)
    
    return result
