#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS 数据结构定义

定义 FileHeader、IndexHeader、ManifestEntry、ArchiveEntry 等核心数据结构。
"""

import struct
from dataclasses import dataclass, field
from typing import ClassVar, Optional


# ==================== 常量定义 ====================

# 模式标识
MODE_MANIFEST = 0x01
MODE_ARCHIVE = 0x02

# 标志位
FLAG_INDEX_ENCRYPTED = 0x01
FLAG_INDEX_COMPRESSED = 0x02

# Entry 标志位
ENTRY_FLAG_COMPRESSED = 0x01
ENTRY_FLAG_EXTERNAL = 0x02


# ==================== 文件头 ====================

@dataclass
class FileHeader:
    """
    文件头 (32 bytes)
    
    位于文件开头，包含全局信息。
    """
    FORMAT: ClassVar[str] = '<4sBBBBQIQI'
    SIZE: ClassVar[int] = 32
    
    magic: bytes = b'GRIM'
    version: int = 3
    mode: int = MODE_MANIFEST
    flags: int = 0
    checksum_algo: int = 0
    index_offset: int = SIZE  # 默认紧跟 Header
    index_size: int = 0
    data_offset: int = 0  # Manifest 模式为 0
    entry_count: int = 0
    
    def pack(self) -> bytes:
        """序列化为字节"""
        return struct.pack(
            self.FORMAT,
            self.magic,
            self.version,
            self.mode,
            self.flags,
            self.checksum_algo,
            self.index_offset,
            self.index_size,
            self.data_offset,
            self.entry_count
        )
    
    @classmethod
    def unpack(cls, data: bytes) -> 'FileHeader':
        """从字节反序列化"""
        values = struct.unpack(cls.FORMAT, data)
        return cls(
            magic=values[0],
            version=values[1],
            mode=values[2],
            flags=values[3],
            checksum_algo=values[4],
            index_offset=values[5],
            index_size=values[6],
            data_offset=values[7],
            entry_count=values[8]
        )


# ==================== 索引头 ====================

@dataclass
class IndexHeader:
    """
    索引头 (16 bytes)
    
    位于 Index Block 开头，描述字典和 Entry 的元信息。
    """
    FORMAT: ClassVar[str] = '<HIHIB3s'
    SIZE: ClassVar[int] = 16
    
    dir_count: int = 0        # 目录字典条目数
    name_count: int = 0       # 文件名字典条目数
    ext_count: int = 0        # 扩展名字典条目数
    string_table_size: int = 0  # String Tables 总大小 (bytes)
    checksum_size: int = 0    # 单个校验值大小 (bytes)
    _reserved: bytes = field(default=b'\x00\x00\x00', repr=False)
    
    def pack(self) -> bytes:
        """序列化为字节"""
        return struct.pack(
            self.FORMAT,
            self.dir_count,
            self.name_count,
            self.ext_count,
            self.string_table_size,
            self.checksum_size,
            self._reserved
        )
    
    @classmethod
    def unpack(cls, data: bytes) -> 'IndexHeader':
        """从字节反序列化"""
        values = struct.unpack(cls.FORMAT, data)
        return cls(
            dir_count=values[0],
            name_count=values[1],
            ext_count=values[2],
            string_table_size=values[3],
            checksum_size=values[4],
            _reserved=values[5]
        )


# ==================== 数据头 (仅 Archive) ====================

@dataclass
class DataHeader:
    """
    数据头 (16 bytes)
    
    仅 Archive 模式使用，位于 Data Block 开头。
    """
    FORMAT: ClassVar[str] = '<4sIQ'
    SIZE: ClassVar[int] = 16
    
    magic: bytes = b'DATA'
    block_count: int = 0      # 数据块数量 (= entry_count)
    total_size: int = 0       # Data Block 总大小
    
    def pack(self) -> bytes:
        """序列化为字节"""
        return struct.pack(
            self.FORMAT,
            self.magic,
            self.block_count,
            self.total_size
        )
    
    @classmethod
    def unpack(cls, data: bytes) -> 'DataHeader':
        """从字节反序列化"""
        values = struct.unpack(cls.FORMAT, data)
        return cls(
            magic=values[0],
            block_count=values[1],
            total_size=values[2]
        )


# ==================== Manifest Entry ====================

@dataclass
class ManifestEntry:
    """
    Manifest 条目 (24 bytes + checksum)
    
    用于清单模式，不含数据定位信息。
    """
    BASE_FORMAT: ClassVar[str] = '<QHIHQ'
    BASE_SIZE: ClassVar[int] = 24
    
    path_hash: int = 0      # 完整路径的 xxHash64
    dir_id: int = 0         # 目录字典索引
    name_id: int = 0        # 文件名字典索引
    ext_id: int = 0         # 扩展名字典索引
    raw_size: int = 0       # 原始文件大小
    checksum: bytes = b''   # 校验值 (长度由 IndexHeader.checksum_size 决定)
    
    def pack(self) -> bytes:
        """序列化为字节"""
        base = struct.pack(
            self.BASE_FORMAT,
            self.path_hash,
            self.dir_id,
            self.name_id,
            self.ext_id,
            self.raw_size
        )
        return base + self.checksum
    
    @classmethod
    def unpack(cls, data: bytes, checksum_size: int = 0) -> 'ManifestEntry':
        """从字节反序列化"""
        base_values = struct.unpack(cls.BASE_FORMAT, data[:cls.BASE_SIZE])
        checksum = data[cls.BASE_SIZE:cls.BASE_SIZE + checksum_size]
        return cls(
            path_hash=base_values[0],
            dir_id=base_values[1],
            name_id=base_values[2],
            ext_id=base_values[3],
            raw_size=base_values[4],
            checksum=checksum
        )
    
    @classmethod
    def entry_size(cls, checksum_size: int) -> int:
        """计算单个 Entry 的总大小"""
        return cls.BASE_SIZE + checksum_size


# ==================== Archive Entry ====================

@dataclass
class ArchiveEntry:
    """
    Archive 条目 (42 bytes + checksum)
    
    用于归档模式，包含数据定位和压缩信息。
    """
    BASE_FORMAT: ClassVar[str] = '<QHIHQQQBB'
    BASE_SIZE: ClassVar[int] = 42
    
    path_hash: int = 0      # 完整路径的 xxHash64
    dir_id: int = 0         # 目录字典索引
    name_id: int = 0        # 文件名字典索引
    ext_id: int = 0         # 扩展名字典索引
    offset: int = 0         # 数据在 Data Block 中的偏移
    packed_size: int = 0    # 压缩后大小
    raw_size: int = 0       # 原始大小
    algo_id: int = 0        # 压缩算法 ID (0=无压缩)
    flags: int = 0          # Entry 标志位
    checksum: bytes = b''   # 校验值
    
    def pack(self) -> bytes:
        """序列化为字节"""
        base = struct.pack(
            self.BASE_FORMAT,
            self.path_hash,
            self.dir_id,
            self.name_id,
            self.ext_id,
            self.offset,
            self.packed_size,
            self.raw_size,
            self.algo_id,
            self.flags
        )
        return base + self.checksum
    
    @classmethod
    def unpack(cls, data: bytes, checksum_size: int = 0) -> 'ArchiveEntry':
        """从字节反序列化"""
        base_values = struct.unpack(cls.BASE_FORMAT, data[:cls.BASE_SIZE])
        checksum = data[cls.BASE_SIZE:cls.BASE_SIZE + checksum_size]
        return cls(
            path_hash=base_values[0],
            dir_id=base_values[1],
            name_id=base_values[2],
            ext_id=base_values[3],
            offset=base_values[4],
            packed_size=base_values[5],
            raw_size=base_values[6],
            algo_id=base_values[7],
            flags=base_values[8],
            checksum=checksum
        )
    
    @classmethod
    def entry_size(cls, checksum_size: int) -> int:
        """计算单个 Entry 的总大小"""
        return cls.BASE_SIZE + checksum_size
