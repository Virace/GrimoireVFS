#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
二进制 I/O 封装

提供 BinaryWriter 和 BinaryReader 类，封装所有底层文件操作，
使上层模块不需要直接操作文件指针。
"""

import struct
from typing import BinaryIO, Tuple, Any


class BinaryWriter:
    """
    二进制写入器
    
    封装所有底层写操作，提供类型化的写入方法。
    上层模块只需调用 write_u32() 等方法，无需关心 struct.pack 细节。
    """
    
    def __init__(self, file: BinaryIO):
        """
        初始化写入器
        
        Args:
            file: 以 'wb' 模式打开的文件对象
        """
        self._file = file
        self._position = 0
    
    @property
    def position(self) -> int:
        """当前写入位置"""
        return self._position
    
    # ==================== 原始写入 ====================
    
    def write_bytes(self, data: bytes) -> int:
        """
        写入原始字节
        
        Args:
            data: 要写入的字节
            
        Returns:
            写入的字节数
        """
        written = self._file.write(data)
        self._position += written
        return written
    
    def write_struct(self, fmt: str, *values: Any) -> int:
        """
        按 struct 格式写入
        
        Args:
            fmt: struct 格式字符串
            *values: 要写入的值
            
        Returns:
            写入的字节数
        """
        data = struct.pack(fmt, *values)
        return self.write_bytes(data)
    
    # ==================== 类型化写入 ====================
    
    def write_u8(self, value: int) -> int:
        """写入无符号 8 位整数"""
        return self.write_struct('<B', value)
    
    def write_u16(self, value: int) -> int:
        """写入无符号 16 位整数 (Little-Endian)"""
        return self.write_struct('<H', value)
    
    def write_u32(self, value: int) -> int:
        """写入无符号 32 位整数 (Little-Endian)"""
        return self.write_struct('<I', value)
    
    def write_u64(self, value: int) -> int:
        """写入无符号 64 位整数 (Little-Endian)"""
        return self.write_struct('<Q', value)
    
    def write_i8(self, value: int) -> int:
        """写入有符号 8 位整数"""
        return self.write_struct('<b', value)
    
    def write_i16(self, value: int) -> int:
        """写入有符号 16 位整数 (Little-Endian)"""
        return self.write_struct('<h', value)
    
    def write_i32(self, value: int) -> int:
        """写入有符号 32 位整数 (Little-Endian)"""
        return self.write_struct('<i', value)
    
    def write_i64(self, value: int) -> int:
        """写入有符号 64 位整数 (Little-Endian)"""
        return self.write_struct('<q', value)
    
    # ==================== 字符串写入 ====================
    
    def write_string(self, s: str) -> int:
        """
        写入长度前缀字符串
        
        格式: [长度: u16][UTF-8 字节]
        
        Args:
            s: 要写入的字符串
            
        Returns:
            写入的总字节数 (2 + 字符串字节数)
        """
        encoded = s.encode('utf-8')
        length = len(encoded)
        self.write_u16(length)
        return 2 + self.write_bytes(encoded)
    
    # ==================== 位置控制 ====================
    
    def reserve(self, size: int) -> int:
        """
        预留空间 (写入零字节)
        
        用于预留 Header 等固定大小区域，稍后回写。
        
        Args:
            size: 预留字节数
            
        Returns:
            预留区域的起始位置
        """
        start = self._position
        self.write_bytes(b'\x00' * size)
        return start
    
    def seek(self, position: int):
        """
        移动到指定位置
        
        Args:
            position: 目标位置
        """
        self._file.seek(position)
        self._position = position
    
    def patch_bytes(self, position: int, data: bytes):
        """
        在指定位置回写数据
        
        写入后恢复到原位置。
        
        Args:
            position: 回写位置
            data: 要写入的数据
        """
        current = self._position
        self.seek(position)
        self.write_bytes(data)
        self.seek(current)
    
    def patch_u32(self, position: int, value: int):
        """在指定位置回写 u32 值"""
        self.patch_bytes(position, struct.pack('<I', value))
    
    def patch_u64(self, position: int, value: int):
        """在指定位置回写 u64 值"""
        self.patch_bytes(position, struct.pack('<Q', value))


class BinaryReader:
    """
    二进制读取器
    
    封装所有底层读操作，提供类型化的读取方法。
    支持普通文件和 mmap 对象。
    """
    
    def __init__(self, file: BinaryIO):
        """
        初始化读取器
        
        Args:
            file: 以 'rb' 模式打开的文件对象
        """
        self._file = file
        self._position = 0
    
    @property
    def position(self) -> int:
        """当前读取位置"""
        return self._position
    
    # ==================== 原始读取 ====================
    
    def read_bytes(self, size: int) -> bytes:
        """
        读取指定字节数
        
        Args:
            size: 要读取的字节数
            
        Returns:
            读取的字节
            
        Raises:
            EOFError: 文件不足请求的字节数
        """
        data = self._file.read(size)
        if len(data) < size:
            raise EOFError(
                f"文件结束: 期望读取 {size} 字节，实际只有 {len(data)} 字节"
            )
        self._position += size
        return data
    
    def read_struct(self, fmt: str) -> Tuple[Any, ...]:
        """
        按 struct 格式读取
        
        Args:
            fmt: struct 格式字符串
            
        Returns:
            解包后的值元组
        """
        size = struct.calcsize(fmt)
        data = self.read_bytes(size)
        return struct.unpack(fmt, data)
    
    # ==================== 类型化读取 ====================
    
    def read_u8(self) -> int:
        """读取无符号 8 位整数"""
        return self.read_struct('<B')[0]
    
    def read_u16(self) -> int:
        """读取无符号 16 位整数 (Little-Endian)"""
        return self.read_struct('<H')[0]
    
    def read_u32(self) -> int:
        """读取无符号 32 位整数 (Little-Endian)"""
        return self.read_struct('<I')[0]
    
    def read_u64(self) -> int:
        """读取无符号 64 位整数 (Little-Endian)"""
        return self.read_struct('<Q')[0]
    
    def read_i8(self) -> int:
        """读取有符号 8 位整数"""
        return self.read_struct('<b')[0]
    
    def read_i16(self) -> int:
        """读取有符号 16 位整数 (Little-Endian)"""
        return self.read_struct('<h')[0]
    
    def read_i32(self) -> int:
        """读取有符号 32 位整数 (Little-Endian)"""
        return self.read_struct('<i')[0]
    
    def read_i64(self) -> int:
        """读取有符号 64 位整数 (Little-Endian)"""
        return self.read_struct('<q')[0]
    
    # ==================== 字符串读取 ====================
    
    def read_string(self) -> str:
        """
        读取长度前缀字符串
        
        格式: [长度: u16][UTF-8 字节]
        
        Returns:
            解码后的字符串
        """
        length = self.read_u16()
        data = self.read_bytes(length)
        return data.decode('utf-8')
    
    # ==================== 位置控制 ====================
    
    def seek(self, position: int):
        """
        移动到指定位置
        
        Args:
            position: 目标位置
        """
        self._file.seek(position)
        self._position = position
    
    def skip(self, size: int):
        """
        跳过指定字节
        
        Args:
            size: 要跳过的字节数
        """
        self.seek(self._position + size)
    
    def peek_bytes(self, size: int) -> bytes:
        """
        预览指定字节 (不移动位置)
        
        Args:
            size: 要预览的字节数
            
        Returns:
            预览的字节
        """
        data = self.read_bytes(size)
        self.seek(self._position - size)
        return data
