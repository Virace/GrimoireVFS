#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hook 基类定义

定义压缩、校验、加密和路径 Hash 的抽象接口。
"""

from abc import ABC, abstractmethod


class CompressionHook(ABC):
    """
    压缩算法钩子
    
    用于实现自定义压缩算法 (如 Zstd, LZ4, LZMA)。
    """
    
    @property
    @abstractmethod
    def algo_id(self) -> int:
        """
        算法 ID
        
        必须唯一，存储在 Entry 的 algo_id 字段中。
        0 保留为"无压缩"。
        
        Returns:
            1-255 之间的整数
        """
        pass
    
    @abstractmethod
    def compress(self, data: bytes) -> bytes:
        """
        压缩数据
        
        Args:
            data: 原始数据
            
        Returns:
            压缩后的数据
        """
        pass
    
    @abstractmethod
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        """
        解压数据
        
        Args:
            data: 压缩后的数据
            raw_size: 原始大小，用于预分配缓冲区
            
        Returns:
            解压后的数据
        """
        pass


class ChecksumHook(ABC):
    """
    校验算法钩子
    
    用于实现自定义校验算法 (如 MD5, SHA1, CRC32)。
    """
    
    @property
    @abstractmethod
    def algo_id(self) -> int:
        """
        算法 ID
        
        对应 FileHeader 中的 checksum_algo 字段。
        0 = 无校验, 1 = CRC32, 2 = MD5, 3 = SHA1, 4 = SHA256
        
        Returns:
            算法 ID
        """
        pass
    
    @property
    def display_name(self) -> str:
        """
        可读名称 (用于 JSON 显示)
        
        默认返回类名，子类可覆盖提供更友好的名称。
        
        Returns:
            可读名称字符串
        """
        return type(self).__name__
    
    @property
    @abstractmethod
    def digest_size(self) -> int:
        """
        校验值字节数
        
        Returns:
            校验值长度 (bytes)
        """
        pass
    
    @abstractmethod
    def compute(self, data: bytes) -> bytes:
        """
        计算校验值
        
        Args:
            data: 要校验的数据
            
        Returns:
            校验值字节
        """
        pass
    
    def verify(self, data: bytes, expected: bytes) -> bool:
        """
        验证校验值
        
        默认实现直接比较计算结果和期望值。
        
        Args:
            data: 要校验的数据
            expected: 期望的校验值
            
        Returns:
            校验是否通过
        """
        return self.compute(data) == expected

class IndexCryptoHook(ABC):
    """
    索引加密钩子
    
    用于加密/解密 String Tables 区域。
    注意：只用于索引区，不用于数据区。
    """
    
    @property
    @abstractmethod
    def flags_id(self) -> int:
        """
        标志位 ID
        
        对应 FileHeader 中的 flags 字段。
        用于标识使用了什么类型的索引加密/压缩。
        
        Returns:
            标志位值 (e.g., 0x01, 0x02, 0x03)
        """
        pass
    
    @property
    def display_name(self) -> str:
        """
        可读名称 (用于 JSON 显示)
        
        默认返回类名，子类可覆盖提供更友好的名称。
        
        Returns:
            可读名称字符串
        """
        return type(self).__name__
    
    @abstractmethod
    def encrypt(self, data: bytes) -> bytes:
        """
        加密数据
        
        Args:
            data: 原始数据
            
        Returns:
            加密后的数据
        """
        pass
    
    @abstractmethod
    def decrypt(self, data: bytes) -> bytes:
        """
        解密数据
        
        Args:
            data: 加密后的数据
            
        Returns:
            解密后的数据
        """
        pass


class PathHashHook(ABC):
    """
    路径 Hash 钩子
    
    用于替换默认的路径 Hash 算法。
    推荐使用 xxHash64 以获得更好的性能和分布。
    """
    
    @abstractmethod
    def hash(self, path: str) -> int:
        """
        计算路径的 Hash 值
        
        Args:
            path: 规范化后的路径
            
        Returns:
            64-bit 整数 Hash 值
        """
        pass
