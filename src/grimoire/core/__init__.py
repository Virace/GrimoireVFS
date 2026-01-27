#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS 核心模块

提供二进制 I/O 封装、数据结构定义和字符串字典管理。
"""

from .binary_io import BinaryReader, BinaryWriter
from .schema import FileHeader, IndexHeader, ManifestEntry, ArchiveEntry
from .string_table import StringTable, PathDictionary
from .batch import (
    FileItem, ProgressInfo, BatchResult, ProgressTracker,
    ErrorPolicy, scan_directory, estimate_total_bytes
)

__all__ = [
    "BinaryReader",
    "BinaryWriter",
    "FileHeader",
    "IndexHeader",
    "ManifestEntry",
    "ArchiveEntry",
    "StringTable",
    "PathDictionary",
    # 批量操作
    "FileItem",
    "ProgressInfo",
    "BatchResult",
    "ProgressTracker",
    "ErrorPolicy",
    "scan_directory",
    "estimate_total_bytes",
]

