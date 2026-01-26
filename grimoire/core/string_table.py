#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
字符串字典管理

提供 StringTable 和 PathDictionary 类，用于管理三级路径字典。
"""

from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .binary_io import BinaryWriter, BinaryReader


class StringTable:
    """
    字符串字典
    
    去重存储字符串，返回索引引用。
    用于压缩重复的目录路径、文件名和扩展名。
    """
    
    def __init__(self):
        self._strings: List[str] = []
        self._index: Dict[str, int] = {}
    
    def add(self, s: str) -> int:
        """
        添加字符串，返回索引
        
        如果字符串已存在，返回现有索引。
        
        Args:
            s: 要添加的字符串
            
        Returns:
            字符串的索引
        """
        if s in self._index:
            return self._index[s]
        
        idx = len(self._strings)
        self._strings.append(s)
        self._index[s] = idx
        return idx
    
    def get(self, index: int) -> str:
        """
        根据索引获取字符串
        
        Args:
            index: 字符串索引
            
        Returns:
            对应的字符串
            
        Raises:
            IndexError: 索引超出范围
        """
        return self._strings[index]
    
    def __len__(self) -> int:
        """返回字符串数量"""
        return len(self._strings)
    
    def __contains__(self, s: str) -> bool:
        """检查字符串是否存在"""
        return s in self._index
    
    def __iter__(self):
        """迭代所有字符串"""
        return iter(self._strings)
    
    def pack(self, writer: 'BinaryWriter') -> int:
        """
        序列化到 BinaryWriter
        
        格式: [len1: u16][utf8_1][len2: u16][utf8_2]...
        
        Args:
            writer: 二进制写入器
            
        Returns:
            写入的字节数
        """
        start = writer.position
        for s in self._strings:
            writer.write_string(s)
        return writer.position - start
    
    @classmethod
    def unpack(cls, reader: 'BinaryReader', count: int) -> 'StringTable':
        """
        从 BinaryReader 反序列化
        
        Args:
            reader: 二进制读取器
            count: 字符串数量
            
        Returns:
            StringTable 实例
        """
        table = cls()
        for _ in range(count):
            s = reader.read_string()
            table._strings.append(s)
            table._index[s] = len(table._strings) - 1
        return table
    
    @classmethod
    def from_bytes(cls, data: bytes, count: int) -> 'StringTable':
        """
        从字节数据反序列化
        
        Args:
            data: 原始字节数据
            count: 字符串数量
            
        Returns:
            StringTable 实例
        """
        import io
        from .binary_io import BinaryReader
        
        reader = BinaryReader(io.BytesIO(data))
        return cls.unpack(reader, count)


class PathDictionary:
    """
    三级路径字典
    
    管理目录、文件名、扩展名三个独立的 StringTable。
    用于高效存储和查找路径信息。
    """
    
    def __init__(self):
        self.dirs = StringTable()    # 目录字典
        self.names = StringTable()   # 文件名字典
        self.exts = StringTable()    # 扩展名字典
    
    def add_path(self, dir_path: str, name: str, ext: str) -> Tuple[int, int, int]:
        """
        添加路径组件，返回三个索引
        
        Args:
            dir_path: 目录路径
            name: 文件名 (不含扩展名)
            ext: 扩展名 (含点号)
            
        Returns:
            (dir_id, name_id, ext_id) 元组
        """
        return (
            self.dirs.add(dir_path),
            self.names.add(name),
            self.exts.add(ext)
        )
    
    def get_path(self, dir_id: int, name_id: int, ext_id: int) -> str:
        """
        根据 ID 重建完整路径
        
        Args:
            dir_id: 目录索引
            name_id: 文件名索引
            ext_id: 扩展名索引
            
        Returns:
            完整路径字符串
        """
        dir_path = self.dirs.get(dir_id)
        name = self.names.get(name_id)
        ext = self.exts.get(ext_id)
        
        # 处理根目录情况
        if dir_path == "/":
            return f"/{name}{ext}"
        return f"{dir_path}/{name}{ext}"
    
    def pack(self, writer: 'BinaryWriter') -> int:
        """
        序列化到 BinaryWriter
        
        顺序: dirs → names → exts
        
        Args:
            writer: 二进制写入器
            
        Returns:
            写入的字节数
        """
        start = writer.position
        self.dirs.pack(writer)
        self.names.pack(writer)
        self.exts.pack(writer)
        return writer.position - start
    
    @classmethod
    def unpack(cls, reader: 'BinaryReader', 
               dir_count: int, name_count: int, ext_count: int) -> 'PathDictionary':
        """
        从 BinaryReader 反序列化
        
        Args:
            reader: 二进制读取器
            dir_count: 目录数量
            name_count: 文件名数量
            ext_count: 扩展名数量
            
        Returns:
            PathDictionary 实例
        """
        path_dict = cls()
        path_dict.dirs = StringTable.unpack(reader, dir_count)
        path_dict.names = StringTable.unpack(reader, name_count)
        path_dict.exts = StringTable.unpack(reader, ext_count)
        return path_dict
    
    @property
    def stats(self) -> Dict[str, int]:
        """返回字典统计信息"""
        return {
            'dirs': len(self.dirs),
            'names': len(self.names),
            'exts': len(self.exts),
            'total': len(self.dirs) + len(self.names) + len(self.exts)
        }
