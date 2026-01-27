#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Archive 文件读取器

用于读取 Archive 模式的完整归档文件。
支持 mmap 和传统文件读取模式。
"""

import io
import mmap
import os
from typing import Optional, List, Dict, Callable, BinaryIO

from ..core.binary_io import BinaryReader
from ..core.schema import (
    FileHeader, IndexHeader, DataHeader, ArchiveEntry,
    MODE_ARCHIVE
)
from ..core.string_table import PathDictionary
from ..hooks.base import CompressionHook, ChecksumHook, IndexCryptoHook
from ..utils import normalize_path, default_path_hash
from ..exceptions import (
    InvalidFormatError,
    IndexNotDecryptedError,
    CorruptedDataError,
    UnknownAlgorithmError
)


class ArchiveReader:
    """
    Archive 文件读取器
    
    支持两种读取模式:
    - mmap 模式 (默认): 内存映射，线程安全，高性能
    - 传统模式: 标准文件 I/O
    """
    
    def __init__(
        self,
        file_path: str,
        compression_hooks: Optional[List[CompressionHook]] = None,
        checksum_hook: Optional[ChecksumHook] = None,
        index_crypto: Optional[IndexCryptoHook] = None,
        path_hash_func: Optional[Callable[[str], int]] = None,
        use_mmap: bool = True
    ):
        """
        初始化读取器
        
        Args:
            file_path: Archive 文件路径
            compression_hooks: 解压算法钩子列表
            checksum_hook: 校验算法钩子
            index_crypto: 索引解密钩子
            path_hash_func: 自定义路径 Hash 函数
            use_mmap: 是否使用 mmap 模式
        """
        self._file_path = file_path
        self._checksum_hook = checksum_hook
        self._index_crypto = index_crypto
        self._path_hash_func = path_hash_func or default_path_hash
        self._use_mmap = use_mmap
        
        # 注册解压钩子
        self._compression_hooks: Dict[int, CompressionHook] = {}
        if compression_hooks:
            for hook in compression_hooks:
                self._compression_hooks[hook.algo_id] = hook
        
        # 内部状态
        self._file: Optional[BinaryIO] = None
        self._mmap: Optional[mmap.mmap] = None
        self._file_header: Optional[FileHeader] = None
        self._index_header: Optional[IndexHeader] = None
        self._data_header: Optional[DataHeader] = None
        self._path_dict: Optional[PathDictionary] = None
        self._entries: Dict[int, ArchiveEntry] = {}  # path_hash -> Entry
        self._index_decrypted: bool = False
        
        # 加载文件
        self._load()
    
    def _load(self) -> None:
        """加载文件内容"""
        self._file = open(self._file_path, 'rb')
        
        # 使用 mmap
        if self._use_mmap:
            try:
                self._mmap = mmap.mmap(
                    self._file.fileno(),
                    0,  # 整个文件
                    access=mmap.ACCESS_READ
                )
            except Exception:
                # mmap 失败，回退到传统模式
                self._use_mmap = False
                self._mmap = None
        
        reader = BinaryReader(self._file)
        
        # ========== 1. 读取 FileHeader ==========
        header_data = reader.read_bytes(FileHeader.SIZE)
        self._file_header = FileHeader.unpack(header_data)
        
        # 验证
        if self._file_header.mode != MODE_ARCHIVE:
            raise InvalidFormatError(
                "非 Archive 模式",
                expected="MODE_ARCHIVE (0x02)",
                actual=f"0x{self._file_header.mode:02x}"
            )
        
        # ========== 2. 读取 IndexHeader ==========
        index_header_data = reader.read_bytes(IndexHeader.SIZE)
        self._index_header = IndexHeader.unpack(index_header_data)
        
        # ========== 3. 读取 String Tables ==========
        string_data = reader.read_bytes(self._index_header.string_table_size)
        
        # flags 非零表示索引区需要处理 (压缩/加密)
        needs_processing = self._file_header.flags != 0
        
        if needs_processing:
            if self._index_crypto:
                string_data = self._index_crypto.decrypt(string_data)
                self._index_decrypted = True
            else:
                self._index_decrypted = False
        else:
            self._index_decrypted = True
        
        # 解析字典 (如果已解密)
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
        entry_size = ArchiveEntry.entry_size(checksum_size)
        
        for _ in range(self._file_header.entry_count):
            entry_data = reader.read_bytes(entry_size)
            entry = ArchiveEntry.unpack(entry_data, checksum_size)
            self._entries[entry.path_hash] = entry
        
        # ========== 5. 读取 DataHeader ==========
        data_header_data = reader.read_bytes(DataHeader.SIZE)
        self._data_header = DataHeader.unpack(data_header_data)
        
        if self._data_header.magic != b'DATA':
            raise InvalidFormatError(
                "无效的数据头魔法数",
                expected="DATA",
                actual=str(self._data_header.magic)
            )
    
    def _read_data(self, offset: int, size: int) -> bytes:
        """
        读取指定位置的数据
        
        mmap 模式下直接切片，传统模式下 seek+read。
        """
        if self._mmap:
            return self._mmap[offset:offset + size]
        else:
            self._file.seek(offset)
            return self._file.read(size)
    
    def exists(self, vfs_path: str) -> bool:
        """检查虚拟路径是否存在"""
        path_hash = self._path_hash_func(normalize_path(vfs_path))
        return path_hash in self._entries
    
    def read(self, vfs_path: str, verify: bool = True) -> bytes:
        """
        读取文件内容
        
        Args:
            vfs_path: 虚拟路径
            verify: 是否校验数据完整性
            
        Returns:
            文件原始内容
            
        Raises:
            FileNotFoundError: 路径不存在
            CorruptedDataError: 校验失败
            UnknownAlgorithmError: 未知的解压算法
        """
        path_hash = self._path_hash_func(normalize_path(vfs_path))
        if path_hash not in self._entries:
            raise FileNotFoundError(f"路径不存在: {vfs_path}")
        
        entry = self._entries[path_hash]
        
        # 1. 读取压缩后的数据
        packed_data = self._read_data(entry.offset, entry.packed_size)
        
        # 2. 解压 (如果需要)
        if entry.algo_id != 0:
            if entry.algo_id not in self._compression_hooks:
                raise UnknownAlgorithmError(entry.algo_id, "compression")
            hook = self._compression_hooks[entry.algo_id]
            raw_data = hook.decompress(packed_data, entry.raw_size)
        else:
            raw_data = packed_data
        
        # 3. 校验 (如果需要)
        if verify and self._checksum_hook and entry.checksum:
            if not self._checksum_hook.verify(raw_data, entry.checksum):
                raise CorruptedDataError(
                    vfs_path,
                    entry.checksum,
                    self._checksum_hook.compute(raw_data)
                )
        
        return raw_data
    
    def open(self, vfs_path: str, verify: bool = True) -> io.BytesIO:
        """
        以文件对象方式打开
        
        Args:
            vfs_path: 虚拟路径
            verify: 是否校验数据完整性
            
        Returns:
            BytesIO 对象
        """
        data = self.read(vfs_path, verify)
        return io.BytesIO(data)
    
    def get_entry(self, vfs_path: str) -> ArchiveEntry:
        """获取指定路径的条目信息"""
        path_hash = self._path_hash_func(normalize_path(vfs_path))
        if path_hash not in self._entries:
            raise FileNotFoundError(f"路径不存在: {vfs_path}")
        return self._entries[path_hash]
    
    def list_all(self) -> List[str]:
        """
        列出所有文件路径
        
        Raises:
            IndexNotDecryptedError: 索引未解密
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
        
        返回每个条目的路径、大小、压缩信息等，不包含二进制数据。
        如需读取数据，请使用 read() 方法。
        
        Returns:
            条目信息列表，每个元素包含:
            - path: 虚拟路径
            - raw_size: 原始大小
            - packed_size: 压缩后大小
            - algo_id: 压缩算法 ID (0=未压缩)
            - checksum: 校验值 (bytes)
            - checksum_hex: 校验值 (hex字符串)
            
        Raises:
            IndexNotDecryptedError: 索引未解密时无法遍历
            
        Example:
            >>> for entry in reader.get_all_entries():
            ...     print(f"{entry['path']}: {entry['raw_size']} bytes")
            ...     if entry['raw_size'] > 0:
            ...         data = reader.read(entry['path'])  # 按需读取
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
                'raw_size': entry.raw_size,
                'packed_size': entry.packed_size,
                'algo_id': entry.algo_id,
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
        """列出所有路径 Hash"""
        return list(self._entries.keys())
    
    @property
    def file_header(self) -> FileHeader:
        return self._file_header
    
    @property
    def index_header(self) -> IndexHeader:
        return self._index_header
    
    @property
    def data_header(self) -> DataHeader:
        return self._data_header
    
    @property
    def entry_count(self) -> int:
        return len(self._entries)
    
    @property
    def is_decrypted(self) -> bool:
        return self._index_decrypted
    
    @property
    def is_mmap(self) -> bool:
        return self._mmap is not None
    
    def close(self) -> None:
        """关闭文件"""
        if self._mmap:
            self._mmap.close()
            self._mmap = None
        if self._file:
            self._file.close()
            self._file = None
    
    def __enter__(self) -> 'ArchiveReader':
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
    
    # ==================== 批量操作 API ====================
    
    def read_batch(
        self,
        vfs_paths: List[str],
        verify: bool = True,
        on_error: str = 'raise'
    ) -> Dict[str, bytes]:
        """
        批量读取多个文件
        
        mmap 模式下可实现真正的并行读取。
        
        Args:
            vfs_paths: 虚拟路径列表
            verify: 是否校验数据完整性
            on_error: 错误处理策略 ('raise', 'skip')
            
        Returns:
            {vfs_path: data} 字典
        """
        result = {}
        
        for path in vfs_paths:
            try:
                data = self.read(path, verify)
                result[path] = data
            except Exception as e:
                if on_error == 'raise':
                    raise
                elif on_error == 'skip':
                    continue  # 跳过失败的文件
        
        return result
    
    def extract_all(
        self,
        output_dir: str,
        verify: bool = True,
        on_error: str = 'raise',
        progress_callback: Optional[Callable] = None
    ) -> 'BatchResult':
        """
        解包所有文件到指定目录
        
        Args:
            output_dir: 输出目录路径
            verify: 是否校验数据完整性
            on_error: 错误处理策略
            progress_callback: 进度回调函数
            
        Returns:
            BatchResult 批量操作结果
        """
        from ..core.batch import BatchResult, ProgressTracker, ProgressInfo
        
        if not self._index_decrypted:
            raise IndexNotDecryptedError("需要解密索引才能解包所有文件")
        
        all_paths = self.list_all()
        total_files = len(all_paths)
        total_bytes = sum(self._entries[self._path_hash_func(normalize_path(p))].raw_size 
                         for p in all_paths)
        
        tracker = ProgressTracker(
            total_files=total_files,
            total_bytes=total_bytes,
            callback=progress_callback
        )
        
        result = BatchResult()
        
        # 预创建目录结构
        dirs_to_create = set()
        for vfs_path in all_paths:
            local_path = os.path.join(output_dir, vfs_path.lstrip('/'))
            dirs_to_create.add(os.path.dirname(local_path))
        
        for dir_path in dirs_to_create:
            os.makedirs(dir_path, exist_ok=True)
        
        # 解包文件
        for vfs_path in all_paths:
            try:
                data = self.read(vfs_path, verify)
                local_path = os.path.join(output_dir, vfs_path.lstrip('/'))
                
                with open(local_path, 'wb') as f:
                    f.write(data)
                
                result.success_count += 1
                result.total_bytes += len(data)
                tracker.update(vfs_path, len(data))
                
            except Exception as e:
                if on_error == 'raise':
                    raise
                elif on_error == 'skip':
                    result.failed_count += 1
                    result.failed_files.append((vfs_path, e))
                    tracker.update(vfs_path, 0)
                elif on_error == 'abort':
                    result.failed_count += 1
                    result.failed_files.append((vfs_path, e))
                    break
        
        result.elapsed_time = tracker.finish()
        return result

