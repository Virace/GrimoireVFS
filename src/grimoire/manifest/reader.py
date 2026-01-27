#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Manifest 文件读取器

用于读取 Manifest 模式的索引清单文件。
"""

import io
import os
from typing import Optional, List, Dict, Callable

from ..core.binary_io import BinaryReader
from ..core.schema import FileHeader, IndexHeader, ManifestEntry, MODE_MANIFEST
from ..core.string_table import PathDictionary
from ..hooks.base import ChecksumHook, IndexCryptoHook
from ..utils import normalize_path, default_path_hash
from ..exceptions import (
    InvalidFormatError, 
    IndexNotDecryptedError,
    CorruptedDataError
)


class ManifestReader:
    """
    Manifest 文件读取器
    
    用于读取清单文件，校验本地文件完整性。
    """
    
    def __init__(
        self,
        file_path: str,
        checksum_hook: Optional[ChecksumHook] = None,
        index_crypto: Optional[IndexCryptoHook] = None,
        path_hash_func: Optional[Callable[[str], int]] = None
    ):
        """
        初始化读取器
        
        Args:
            file_path: Manifest 文件路径
            checksum_hook: 校验算法钩子 (需与创建时一致)
            index_crypto: 索引解密钩子 (如果索引已加密)
            path_hash_func: 自定义路径 Hash 函数
        """
        self._file_path = file_path
        self._checksum_hook = checksum_hook
        self._index_crypto = index_crypto
        self._path_hash_func = path_hash_func or default_path_hash
        
        # 内部状态
        self._file = open(file_path, 'rb')
        self._reader = BinaryReader(self._file)
        
        self._file_header: Optional[FileHeader] = None
        self._index_header: Optional[IndexHeader] = None
        self._path_dict: Optional[PathDictionary] = None
        self._entries: Dict[int, ManifestEntry] = {}  # path_hash -> Entry
        self._index_decrypted: bool = False
        
        # 加载文件
        self._load()
    
    def _load(self) -> None:
        """加载文件内容"""
        # ========== 1. 读取 FileHeader ==========
        header_data = self._reader.read_bytes(FileHeader.SIZE)
        self._file_header = FileHeader.unpack(header_data)
        
        # 验证魔法数
        if len(self._file_header.magic) != 4:
            raise InvalidFormatError("无效的魔法数长度")
        
        # 验证模式
        if self._file_header.mode != MODE_MANIFEST:
            raise InvalidFormatError(
                f"非 Manifest 模式",
                expected="MODE_MANIFEST (0x01)",
                actual=f"0x{self._file_header.mode:02x}"
            )
        
        # ========== 2. 读取 IndexHeader ==========
        index_header_data = self._reader.read_bytes(IndexHeader.SIZE)
        self._index_header = IndexHeader.unpack(index_header_data)
        
        # ========== 3. 读取 String Tables ==========
        string_data = self._reader.read_bytes(self._index_header.string_table_size)
        
        # flags 非零表示索引区需要处理 (压缩/加密)
        needs_processing = self._file_header.flags != 0
        
        if needs_processing:
            if self._index_crypto:
                # 解密/解压
                string_data = self._index_crypto.decrypt(string_data)
                self._index_decrypted = True
            else:
                # 未提供解密器，保持加密状态
                self._index_decrypted = False
        else:
            self._index_decrypted = True
        
        # 如果已解密，解析字典
        if self._index_decrypted:
            string_reader = BinaryReader(io.BytesIO(string_data))
            self._path_dict = PathDictionary.unpack(
                string_reader,
                self._index_header.dir_count,
                self._index_header.name_count,
                self._index_header.ext_count
            )
        
        # ========== 4. 读取 Entry Table ==========
        checksum_size = self._index_header.checksum_size
        entry_size = ManifestEntry.entry_size(checksum_size)
        
        for _ in range(self._file_header.entry_count):
            entry_data = self._reader.read_bytes(entry_size)
            entry = ManifestEntry.unpack(entry_data, checksum_size)
            self._entries[entry.path_hash] = entry
    
    def exists(self, vfs_path: str) -> bool:
        """
        检查虚拟路径是否存在
        
        Args:
            vfs_path: 虚拟路径
            
        Returns:
            路径是否存在
        """
        path_hash = self._path_hash_func(normalize_path(vfs_path))
        return path_hash in self._entries
    
    def get_entry(self, vfs_path: str) -> ManifestEntry:
        """
        获取指定路径的条目信息
        
        Args:
            vfs_path: 虚拟路径
            
        Returns:
            ManifestEntry 对象
            
        Raises:
            FileNotFoundError: 路径不存在
        """
        path_hash = self._path_hash_func(normalize_path(vfs_path))
        if path_hash not in self._entries:
            raise FileNotFoundError(f"路径不存在: {vfs_path}")
        return self._entries[path_hash]
    
    def verify_file(self, vfs_path: str, local_path: str) -> bool:
        """
        校验本地文件与清单是否一致
        
        Args:
            vfs_path: 清单中的虚拟路径
            local_path: 本地文件路径
            
        Returns:
            校验是否通过
            
        Raises:
            FileNotFoundError: vfs_path 不存在于清单中
        """
        entry = self.get_entry(vfs_path)
        
        # 检查本地文件是否存在
        if not os.path.isfile(local_path):
            return False
        
        # 读取本地文件
        with open(local_path, 'rb') as f:
            data = f.read()
        
        # 校验大小
        if len(data) != entry.raw_size:
            return False
        
        # 校验 checksum
        if self._checksum_hook and entry.checksum:
            return self._checksum_hook.verify(data, entry.checksum)
        
        return True
    
    def list_all(self) -> List[str]:
        """
        列出所有文件路径
        
        Returns:
            所有虚拟路径列表
            
        Raises:
            IndexNotDecryptedError: 索引未解密时无法遍历
        """
        if not self._index_decrypted:
            raise IndexNotDecryptedError()
        
        result = []
        for entry in self._entries.values():
            full_path = self._path_dict.get_path(
                entry.dir_id, entry.name_id, entry.ext_id
            )
            result.append(full_path)
        return result
    
    def get_all_entries(self) -> List[Dict]:
        """
        获取所有条目的元信息
        
        返回每个条目的路径、大小、校验信息，不包含二进制数据。
        
        Returns:
            条目信息列表，每个元素包含:
            - path: 虚拟路径
            - size: 文件大小
            - checksum: 校验值 (bytes)
            - checksum_hex: 校验值 (hex字符串)
            
        Raises:
            IndexNotDecryptedError: 索引未解密时无法遍历
            
        Example:
            >>> for entry in reader.get_all_entries():
            ...     print(f"{entry['path']}: {entry['size']} bytes")
        """
        if not self._index_decrypted:
            raise IndexNotDecryptedError()
        
        result = []
        for entry in self._entries.values():
            full_path = self._path_dict.get_path(
                entry.dir_id, entry.name_id, entry.ext_id
            )
            result.append({
                'path': full_path,
                'size': entry.raw_size,
                'checksum': entry.checksum,
                'checksum_hex': entry.checksum.hex() if entry.checksum else '',
            })
        return result
    
    def iter_entries(self):
        """
        迭代所有条目 (生成器模式，内存友好)
        
        Yields:
            (path, entry) 元组
            
        Raises:
            IndexNotDecryptedError: 索引未解密时无法遍历
        """
        if not self._index_decrypted:
            raise IndexNotDecryptedError()
        
        for entry in self._entries.values():
            full_path = self._path_dict.get_path(
                entry.dir_id, entry.name_id, entry.ext_id
            )
            yield full_path, entry
    
    def list_hashes(self) -> List[int]:
        """
        列出所有路径 Hash
        
        即使索引加密也可调用此方法。
        
        Returns:
            所有 path_hash 列表
        """
        return list(self._entries.keys())
    
    def get_entry_by_hash(self, path_hash: int) -> Optional[ManifestEntry]:
        """
        根据 Hash 获取条目
        
        Args:
            path_hash: 路径 Hash 值
            
        Returns:
            ManifestEntry 或 None
        """
        return self._entries.get(path_hash)
    
    @property
    def file_header(self) -> FileHeader:
        """文件头信息"""
        return self._file_header
    
    @property
    def index_header(self) -> IndexHeader:
        """索引头信息"""
        return self._index_header
    
    @property
    def entry_count(self) -> int:
        """条目数量"""
        return len(self._entries)
    
    @property
    def is_decrypted(self) -> bool:
        """索引是否已解密"""
        return self._index_decrypted
    
    def close(self) -> None:
        """关闭文件"""
        if self._file:
            self._file.close()
            self._file = None
    
    def __enter__(self) -> 'ManifestReader':
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
