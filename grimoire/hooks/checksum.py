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
    def digest_size(self) -> int:
        return 32
    
    def compute(self, data: bytes) -> bytes:
        return hashlib.sha256(data).digest()


class QuickXorHash:
    """
    QuickXorHash 算法实现
    
    这是 OneDrive 使用的快速非加密哈希算法。
    参考: https://learn.microsoft.com/zh-cn/onedrive/developer/code-snippets/quickxorhash
    
    输出: 20 字节 (160 bits)
    """
    
    BITS_IN_LAST_CELL = 32
    SHIFT = 11
    WIDTH_IN_BITS = 160
    
    def __init__(self):
        self._data = [0] * ((self.WIDTH_IN_BITS - 1) // 64 + 1)  # 3 个 64-bit 元素
        self._length_so_far = 0
        self._shift_so_far = 0
    
    def update(self, data: bytes) -> None:
        """更新哈希状态"""
        cb_size = len(data)
        current_shift = self._shift_so_far
        
        # 当前位向量索引
        vector_array_index = current_shift // 64
        # 位向量内的偏移
        vector_offset = current_shift % 64
        
        iterations = min(cb_size, self.WIDTH_IN_BITS)
        
        for i in range(iterations):
            is_last_cell = vector_array_index == len(self._data) - 1
            bits_in_vector_cell = self.BITS_IN_LAST_CELL if is_last_cell else 64
            
            if vector_offset <= bits_in_vector_cell - 8:
                # 可以直接 XOR
                j = i
                while j < cb_size:
                    self._data[vector_array_index] ^= data[j] << vector_offset
                    j += self.WIDTH_IN_BITS
            else:
                # 需要跨两个位向量
                index1 = vector_array_index
                index2 = 0 if is_last_cell else (vector_array_index + 1)
                low = bits_in_vector_cell - vector_offset
                
                xored_byte = 0
                j = i
                while j < cb_size:
                    xored_byte ^= data[j]
                    j += self.WIDTH_IN_BITS
                
                self._data[index1] ^= xored_byte << vector_offset
                self._data[index2] ^= xored_byte >> low
            
            vector_offset += self.SHIFT
            while vector_offset >= bits_in_vector_cell:
                vector_array_index = 0 if is_last_cell else vector_array_index + 1
                vector_offset -= bits_in_vector_cell
                is_last_cell = vector_array_index == len(self._data) - 1
                bits_in_vector_cell = self.BITS_IN_LAST_CELL if is_last_cell else 64
        
        # 更新循环移位位置
        self._shift_so_far = (self._shift_so_far + self.SHIFT * (cb_size % self.WIDTH_IN_BITS)) % self.WIDTH_IN_BITS
        self._length_so_far += cb_size
    
    def digest(self) -> bytes:
        """计算最终哈希值"""
        # 创建结果数组
        rgb = bytearray((self.WIDTH_IN_BITS - 1) // 8 + 1)  # 20 bytes
        
        # 复制位向量数据
        for i in range(len(self._data) - 1):
            rgb[i * 8:i * 8 + 8] = self._data[i].to_bytes(8, 'little')
        
        # 最后一个位向量 (只有 32 bits)
        last_index = len(self._data) - 1
        remaining = len(rgb) - last_index * 8
        rgb[last_index * 8:] = (self._data[last_index] & ((1 << (remaining * 8)) - 1)).to_bytes(remaining, 'little')
        
        # XOR 文件长度到最低有效位
        length_bytes = self._length_so_far.to_bytes(8, 'little')
        start_pos = self.WIDTH_IN_BITS // 8 - 8  # = 12
        for i in range(8):
            rgb[start_pos + i] ^= length_bytes[i]
        
        return bytes(rgb)
    
    def hexdigest(self) -> str:
        """返回十六进制字符串"""
        return self.digest().hex()


class QuickXorHashHook(ChecksumHook):
    """
    QuickXorHash 校验
    
    OneDrive 使用的快速非加密哈希算法，20 字节输出。
    特点: 速度快，适合大文件校验，但非加密安全。
    
    参考: https://learn.microsoft.com/zh-cn/onedrive/developer/code-snippets/quickxorhash
    """
    
    @property
    def algo_id(self) -> int:
        return 5
    
    @property
    def digest_size(self) -> int:
        return 20
    
    def compute(self, data: bytes) -> bytes:
        hasher = QuickXorHash()
        hasher.update(data)
        return hasher.digest()

