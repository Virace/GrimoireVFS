#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
内置索引压缩/加密 Hook 实现
"""

import zlib
from .base import IndexCryptoHook


class ZlibCompressHook(IndexCryptoHook):
    """
    使用 zlib 压缩索引区
    
    这不是加密，只是压缩，可以减少索引区体积。
    """
    
    def __init__(self, level: int = 6):
        """
        Args:
            level: 压缩级别 (0-9), 默认 6
        """
        self._level = level
    
    def encrypt(self, data: bytes) -> bytes:
        """压缩数据"""
        return zlib.compress(data, self._level)
    
    def decrypt(self, data: bytes) -> bytes:
        """解压数据"""
        return zlib.decompress(data)


class XorObfuscateHook(IndexCryptoHook):
    """
    简单 XOR 混淆
    
    使用固定 key 进行 XOR 混淆，提供基本的索引保护。
    注意：这不是安全的加密，仅用于防止直接查看。
    """
    
    def __init__(self, key: bytes = b'GrimoireVFS'):
        """
        Args:
            key: XOR 密钥
        """
        self._key = key
    
    def _xor(self, data: bytes) -> bytes:
        key_len = len(self._key)
        return bytes(b ^ self._key[i % key_len] for i, b in enumerate(data))
    
    def encrypt(self, data: bytes) -> bytes:
        return self._xor(data)
    
    def decrypt(self, data: bytes) -> bytes:
        return self._xor(data)


class ZlibXorHook(IndexCryptoHook):
    """
    先压缩后 XOR 混淆
    
    结合压缩和混淆，既减少体积又提供基本保护。
    """
    
    def __init__(self, key: bytes = b'GrimoireVFS', level: int = 6):
        self._zlib = ZlibCompressHook(level)
        self._xor = XorObfuscateHook(key)
    
    def encrypt(self, data: bytes) -> bytes:
        compressed = self._zlib.encrypt(data)
        return self._xor.encrypt(compressed)
    
    def decrypt(self, data: bytes) -> bytes:
        deobfuscated = self._xor.decrypt(data)
        return self._zlib.decrypt(deobfuscated)
