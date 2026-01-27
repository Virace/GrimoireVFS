#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
内置校验 Hook 实现

提供常用的校验算法实现 (基于标准库)。
"""

import hashlib
import zlib
from .base import ChecksumHook


class NoneChecksumHook(ChecksumHook):
    """
    无校验
    
    不进行任何校验操作。
    """
    
    @property
    def algo_id(self) -> int:
        return 0
    
    @property
    def display_name(self) -> str:
        return "none"
    
    @property
    def digest_size(self) -> int:
        return 0
    
    def compute(self, data: bytes) -> bytes:
        return b''
    
    def verify(self, data: bytes, expected: bytes) -> bool:
        return True


class CRC32Hook(ChecksumHook):
    """
    CRC32 校验
    
    快速但较弱的校验算法，4 字节输出。
    """
    
    @property
    def algo_id(self) -> int:
        return 1
    
    @property
    def display_name(self) -> str:
        return "crc32"
    
    @property
    def digest_size(self) -> int:
        return 4
    
    def compute(self, data: bytes) -> bytes:
        crc = zlib.crc32(data) & 0xFFFFFFFF
        return crc.to_bytes(4, 'little')


class MD5Hook(ChecksumHook):
    """
    MD5 校验
    
    通用的校验算法，16 字节输出。
    注意：MD5 不应用于安全目的，但适合文件完整性校验。
    """
    
    @property
    def algo_id(self) -> int:
        return 2
    
    @property
    def display_name(self) -> str:
        return "md5"
    
    @property
    def digest_size(self) -> int:
        return 16
    
    def compute(self, data: bytes) -> bytes:
        return hashlib.md5(data).digest()


class SHA1Hook(ChecksumHook):
    """
    SHA1 校验
    
    Git 使用的校验算法，20 字节输出。
    """
    
    @property
    def algo_id(self) -> int:
        return 3
    
    @property
    def display_name(self) -> str:
        return "sha1"
    
    @property
    def digest_size(self) -> int:
        return 20
    
    def compute(self, data: bytes) -> bytes:
        return hashlib.sha1(data).digest()


class SHA256Hook(ChecksumHook):
    """
    SHA256 校验
    
    强校验算法，32 字节输出。
    """
    
    @property
    def algo_id(self) -> int:
        return 4
    
    @property
    def display_name(self) -> str:
        return "sha256"
    
    @property
    def digest_size(self) -> int:
        return 32
    
    def compute(self, data: bytes) -> bytes:
        return hashlib.sha256(data).digest()
