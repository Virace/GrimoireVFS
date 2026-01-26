#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS - 轻量级零依赖 Python 二进制资源管理库

支持 Manifest Mode (清单校验) 和 Archive Mode (资源打包)
"""

__version__ = "0.1.0"
__author__ = "Virace"

# 异常类
from .exceptions import (
    GrimoireError,
    HashCollisionError,
    CorruptedDataError,
    UnknownAlgorithmError,
    InvalidFormatError,
    IndexNotDecryptedError,
)

# 工具函数
from .utils import normalize_path, split_path

# Manifest Mode
from .manifest import ManifestBuilder, ManifestReader

# Archive Mode
from .archive import ArchiveBuilder, ArchiveReader

# 格式转换
from .converter import ManifestJsonConverter, ModeConverter

# Hooks
from .hooks import (
    CompressionHook,
    ChecksumHook,
    IndexCryptoHook,
    NoneChecksumHook,
    CRC32Hook,
    MD5Hook,
    SHA1Hook,
    SHA256Hook,
    ZlibCompressHook,
    XorObfuscateHook,
    ZlibXorHook,
    RcloneHashHook,
    RcloneNotFoundError,
    rclone_hash,
)

__all__ = [
    # 版本
    "__version__",
    # 异常
    "GrimoireError",
    "HashCollisionError",
    "CorruptedDataError",
    "UnknownAlgorithmError",
    "InvalidFormatError",
    "IndexNotDecryptedError",
    # 工具
    "normalize_path",
    "split_path",
    # Manifest
    "ManifestBuilder",
    "ManifestReader",
    # Archive
    "ArchiveBuilder",
    "ArchiveReader",
    # 格式转换
    "ManifestJsonConverter",
    "ModeConverter",
    # Hooks
    "CompressionHook",
    "ChecksumHook",
    "IndexCryptoHook",
    "NoneChecksumHook",
    "CRC32Hook",
    "MD5Hook",
    "SHA1Hook",
    "SHA256Hook",
    "ZlibCompressHook",
    "XorObfuscateHook",
    "ZlibXorHook",
    "RcloneHashHook",
    "RcloneNotFoundError",
    "rclone_hash",
]


