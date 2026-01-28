#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS Hook 系统

提供压缩、校验、加密算法的可插拔接口。
"""

from .base import CompressionHook, ChecksumHook, IndexCryptoHook, PathHashHook
from .checksum import (
    NoneChecksumHook, CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
)
from .crypto import ZlibCompressHook, XorObfuscateHook, ZlibXorHook
from .fhash import FhashHook, FhashNotFoundError, fhash_hash
from .rclone import RcloneHashHook, RcloneNotFoundError, rclone_hash
from .external import (
    ExternalToolLocator,
    ExternalToolManager,
    ToolInfo,
    get_tool_manager,
)
from .registry import (
    get_checksum_hook_by_id,
    get_index_crypto_by_flags,
    get_hook_name,
    get_best_checksum_hook,
    get_external_checksum_hook,
    CHECKSUM_REGISTRY,
    ALGORITHM_REGISTRY,
    ID_TO_ALGORITHM,
)

__all__ = [
    # 抽象基类
    "CompressionHook",
    "ChecksumHook",
    "IndexCryptoHook",
    "PathHashHook",
    # 内置校验实现
    "NoneChecksumHook",
    "CRC32Hook",
    "MD5Hook",
    "SHA1Hook",
    "SHA256Hook",
    # 索引压缩/混淆
    "ZlibCompressHook",
    "XorObfuscateHook",
    "ZlibXorHook",
    # fhash 外置工具
    "FhashHook",
    "FhashNotFoundError",
    "fhash_hash",
    # rclone 外置工具
    "RcloneHashHook",
    "RcloneNotFoundError",
    "rclone_hash",
    # 外置工具管理
    "ExternalToolLocator",
    "ExternalToolManager",
    "ToolInfo",
    "get_tool_manager",
    # 注册表
    "get_checksum_hook_by_id",
    "get_index_crypto_by_flags",
    "get_hook_name",
    "get_best_checksum_hook",
    "get_external_checksum_hook",
    "CHECKSUM_REGISTRY",
    "ALGORITHM_REGISTRY",
    "ID_TO_ALGORITHM",
]
