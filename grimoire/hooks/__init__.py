#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS Hook 系统

提供压缩、校验、加密算法的可插拔接口。
"""

from .base import CompressionHook, ChecksumHook, IndexCryptoHook, PathHashHook
from .checksum import (
    NoneChecksumHook, CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook,
    QuickXorHash, QuickXorHashHook
)
from .crypto import ZlibCompressHook, XorObfuscateHook, ZlibXorHook

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
    "QuickXorHash",
    "QuickXorHashHook",
    # 索引压缩/混淆
    "ZlibCompressHook",
    "XorObfuscateHook",
    "ZlibXorHook",
]


