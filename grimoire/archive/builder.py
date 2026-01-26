#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Archive 文件构建器

用于创建 Archive 模式的完整归档文件 (包含数据块)。
"""

import os
from typing import Optional, List, Dict, Callable

from ..core.binary_io import BinaryWriter
from ..core.schema import (
    FileHeader, IndexHeader, DataHeader, ArchiveEntry,
    MODE_ARCHIVE, FLAG_INDEX_ENCRYPTED, ENTRY_FLAG_COMPRESSED
)
from ..core.string_table import PathDictionary
from ..hooks.base import CompressionHook, ChecksumHook, IndexCryptoHook
from ..utils import normalize_path, split_path, default_path_hash
from ..exceptions import HashCollisionError, UnknownAlgorithmError


class ArchiveBuilder:
    """
    Archive 文件构建器
    
    用于创建归档文件，包含文件索引和二进制数据。
    """
    
    def __init__(
        self,
        output_path: str,
        magic: bytes = b'GRIM',
        compression_hooks: Optional[List[CompressionHook]] = None,
        checksum_hook: Optional[ChecksumHook] = None,
        index_crypto: Optional[IndexCryptoHook] = None,
        path_hash_func: Optional[Callable[[str], int]] = None
    ):
        """
        初始化构建器
        
        Args:
            output_path: 输出文件路径
            magic: 自定义魔法数 (4 bytes)
            compression_hooks: 压缩算法钩子列表
            checksum_hook: 校验算法钩子 (可选)
            index_crypto: 索引加密钩子 (可选)
            path_hash_func: 自定义路径 Hash 函数 (可选)
        """
        self._output_path = output_path
        self._magic = magic
        self._checksum_hook = checksum_hook
        self._index_crypto = index_crypto
        self._path_hash_func = path_hash_func or default_path_hash
        
        # 注册压缩钩子
        self._compression_hooks: Dict[int, CompressionHook] = {}
        if compression_hooks:
            for hook in compression_hooks:
                self._compression_hooks[hook.algo_id] = hook
        
        # 内部状态
        self._path_dict = PathDictionary()
        self._entries: List[ArchiveEntry] = []
        self._data_blobs: List[bytes] = []  # 压缩后的数据块
        self._hash_to_path: Dict[int, str] = {}  # 用于冲突检测
    
    def add_file(
        self,
        local_path: str,
        vfs_path: Optional[str] = None,
        algo_id: int = 0
    ) -> None:
        """
        添加单个文件到归档
        
        Args:
            local_path: 本地文件路径
            vfs_path: 虚拟路径 (默认使用文件名)
            algo_id: 压缩算法 ID (0=不压缩)
            
        Raises:
            FileNotFoundError: 本地文件不存在
            HashCollisionError: 路径 Hash 冲突
            UnknownAlgorithmError: 未注册的压缩算法
        """
        # 1. 检查文件存在
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"文件不存在: {local_path}")
        
        # 2. 检查压缩算法
        if algo_id != 0 and algo_id not in self._compression_hooks:
            raise UnknownAlgorithmError(algo_id, "compression")
        
        # 3. 确定虚拟路径
        if vfs_path is None:
            vfs_path = "/" + os.path.basename(local_path)
        
        # 4. 规范化并拆分路径
        normalized = normalize_path(vfs_path)
        dir_part, name, ext = split_path(normalized)
        
        # 5. 计算 path_hash 并检查冲突
        path_hash = self._path_hash_func(normalized)
        if path_hash in self._hash_to_path:
            existing = self._hash_to_path[path_hash]
            if existing != normalized:
                raise HashCollisionError(existing, normalized, path_hash)
            else:
                return  # 重复添加，跳过
        self._hash_to_path[path_hash] = normalized
        
        # 6. 添加到字典
        dir_id, name_id, ext_id = self._path_dict.add_path(dir_part, name, ext)
        
        # 7. 读取文件
        with open(local_path, 'rb') as f:
            raw_data = f.read()
        raw_size = len(raw_data)
        
        # 8. 计算校验值 (基于原始数据)
        checksum = b''
        if self._checksum_hook:
            checksum = self._checksum_hook.compute(raw_data)
        
        # 9. 压缩数据
        if algo_id != 0:
            hook = self._compression_hooks[algo_id]
            packed_data = hook.compress(raw_data)
            flags = ENTRY_FLAG_COMPRESSED
        else:
            packed_data = raw_data
            flags = 0
        
        packed_size = len(packed_data)
        
        # 10. 记录数据块索引 (offset 稍后计算)
        blob_index = len(self._data_blobs)
        self._data_blobs.append(packed_data)
        
        # 11. 创建 Entry (offset 暂时存储 blob_index)
        entry = ArchiveEntry(
            path_hash=path_hash,
            dir_id=dir_id,
            name_id=name_id,
            ext_id=ext_id,
            offset=blob_index,  # 临时，build() 时计算实际 offset
            packed_size=packed_size,
            raw_size=raw_size,
            algo_id=algo_id,
            flags=flags,
            checksum=checksum
        )
        self._entries.append(entry)
    
    def add_dir(
        self,
        local_dir: str,
        mount_point: str = "/",
        algo_id: int = 0,
        recursive: bool = True
    ) -> int:
        """
        添加目录到归档
        
        Args:
            local_dir: 本地目录路径
            mount_point: 虚拟挂载点
            algo_id: 压缩算法 ID
            recursive: 是否递归扫描子目录
            
        Returns:
            添加的文件数量
        """
        if not os.path.isdir(local_dir):
            raise NotADirectoryError(f"不是目录: {local_dir}")
        
        mount_point = normalize_path(mount_point)
        count = 0
        
        if recursive:
            for root, dirs, files in os.walk(local_dir):
                for filename in files:
                    local_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(local_path, local_dir)
                    vfs_path = mount_point + "/" + rel_path.replace("\\", "/")
                    self.add_file(local_path, vfs_path, algo_id)
                    count += 1
        else:
            for filename in os.listdir(local_dir):
                local_path = os.path.join(local_dir, filename)
                if os.path.isfile(local_path):
                    vfs_path = mount_point + "/" + filename
                    self.add_file(local_path, vfs_path, algo_id)
                    count += 1
        
        return count
    
    def build(self) -> None:
        """
        构建并写入 Archive 文件
        
        执行流程:
        1. 预留 FileHeader 空间
        2. 写入 IndexHeader + String Tables + Entry Table
        3. 写入 DataHeader + Data Block
        4. 回写 Headers
        """
        with open(self._output_path, 'w+b') as f:
            writer = BinaryWriter(f)
            
            # ========== 1. 预留 FileHeader 空间 ==========
            writer.reserve(FileHeader.SIZE)
            
            # ========== 2. 写入 Index Block ==========
            index_start = writer.position
            
            # 2.1 预留 IndexHeader 空间
            writer.reserve(IndexHeader.SIZE)
            
            # 2.2 写入 String Tables
            string_start = writer.position
            self._path_dict.pack(writer)
            string_size = writer.position - string_start
            
            # 2.3 如果需要加密
            if self._index_crypto:
                f.seek(string_start)
                string_data = f.read(string_size)
                encrypted = self._index_crypto.encrypt(string_data)
                f.seek(string_start)
                f.write(encrypted)
                writer.seek(string_start + len(encrypted))
            
            # ========== 3. 写入 Data Block ==========
            # 3.1 写入 DataHeader
            data_header_pos = writer.position
            writer.reserve(DataHeader.SIZE)
            
            # 3.2 计算每个 Entry 的实际 offset 并写入数据
            data_start = writer.position
            current_offset = 0
            
            for i, entry in enumerate(self._entries):
                blob_data = self._data_blobs[i]
                
                # 更新 Entry 的 offset (相对于 Data Block 开始)
                entry.offset = data_start + current_offset
                
                # 写入数据
                writer.write_bytes(blob_data)
                current_offset += len(blob_data)
            
            data_total_size = writer.position - data_start
            
            # ========== 4. 写入 Entry Table (在 String Tables 之后) ==========
            # 先记录 Entry Table 开始位置
            entry_table_pos = string_start + string_size
            if self._index_crypto:
                # 加密后可能略有变化，但通常相同
                pass
            
            # 重新定位到 Entry Table 位置
            writer.seek(data_header_pos)  # 暂时跳过，稍后处理
            
            # 实际上，我们需要重新组织写入顺序
            # 由于 Entry 的 offset 需要在写入 Data 后才能确定
            # 我们采用：先写入所有内容到内存，最后一次性写入
            
        # ===== 重新实现：两阶段写入 =====
        self._build_two_phase()
    
    def _build_two_phase(self) -> None:
        """
        两阶段构建
        
        阶段 1: 收集所有数据，计算 offset
        阶段 2: 一次性写入文件
        """
        import io
        
        # ===== 阶段 1: 计算布局 =====
        
        # 计算 String Tables 大小
        string_buffer = io.BytesIO()
        string_writer = BinaryWriter(string_buffer)
        self._path_dict.pack(string_writer)
        string_data = string_buffer.getvalue()
        
        # 加密 (如果需要)
        if self._index_crypto:
            string_data = self._index_crypto.encrypt(string_data)
        
        string_size = len(string_data)
        
        # 计算 Entry Table 大小
        checksum_size = self._checksum_hook.digest_size if self._checksum_hook else 0
        entry_size = ArchiveEntry.entry_size(checksum_size)
        entry_table_size = entry_size * len(self._entries)
        
        # 计算各区块偏移
        file_header_size = FileHeader.SIZE
        index_header_size = IndexHeader.SIZE
        data_header_size = DataHeader.SIZE
        
        index_start = file_header_size
        string_start = index_start + index_header_size
        entry_start = string_start + string_size
        data_header_start = entry_start + entry_table_size
        data_start = data_header_start + data_header_size
        
        # 计算每个 Entry 的 offset
        current_data_offset = data_start
        for i, entry in enumerate(self._entries):
            entry.offset = current_data_offset
            current_data_offset += entry.packed_size
        
        data_total_size = current_data_offset - data_start
        index_size = data_header_start - index_start
        
        # ===== 阶段 2: 写入文件 =====
        with open(self._output_path, 'wb') as f:
            writer = BinaryWriter(f)
            
            # 1. FileHeader
            file_header = FileHeader(
                magic=self._magic,
                version=3,
                mode=MODE_ARCHIVE,
                flags=FLAG_INDEX_ENCRYPTED if self._index_crypto else 0,
                checksum_algo=self._checksum_hook.algo_id if self._checksum_hook else 0,
                index_offset=index_start,
                index_size=index_size,
                data_offset=data_header_start,
                entry_count=len(self._entries)
            )
            writer.write_bytes(file_header.pack())
            
            # 2. IndexHeader
            index_header = IndexHeader(
                dir_count=len(self._path_dict.dirs),
                name_count=len(self._path_dict.names),
                ext_count=len(self._path_dict.exts),
                string_table_size=string_size,
                checksum_size=checksum_size
            )
            writer.write_bytes(index_header.pack())
            
            # 3. String Tables
            writer.write_bytes(string_data)
            
            # 4. Entry Table
            for entry in self._entries:
                writer.write_bytes(entry.pack())
            
            # 5. DataHeader
            data_header = DataHeader(
                magic=b'DATA',
                block_count=len(self._entries),
                total_size=data_total_size
            )
            writer.write_bytes(data_header.pack())
            
            # 6. Data Block
            for blob in self._data_blobs:
                writer.write_bytes(blob)
    
    @property
    def entry_count(self) -> int:
        """已添加的文件数量"""
        return len(self._entries)
    
    @property
    def path_stats(self) -> dict:
        """路径字典统计信息"""
        return self._path_dict.stats
    
    @property
    def compression_stats(self) -> dict:
        """压缩统计信息"""
        total_raw = sum(e.raw_size for e in self._entries)
        total_packed = sum(e.packed_size for e in self._entries)
        return {
            'total_raw': total_raw,
            'total_packed': total_packed,
            'ratio': total_packed / total_raw if total_raw > 0 else 1.0
        }
    
    # ==================== 批量操作 API ====================
    
    def add_files_batch(
        self,
        items: 'List[FileItem] | Iterator[FileItem]',
        on_error: str = 'raise',
        progress_callback: Optional[Callable[['ProgressInfo'], None]] = None
    ) -> 'BatchResult':
        """
        批量添加文件
        
        Args:
            items: FileItem 列表或迭代器
            on_error: 错误处理策略 ('raise', 'skip', 'abort')
            progress_callback: 进度回调函数
            
        Returns:
            BatchResult 批量操作结果
        """
        from ..core.batch import (
            FileItem, ProgressInfo, BatchResult, ProgressTracker,
            ErrorPolicy, estimate_total_bytes
        )
        
        # 转换为列表以获取总数 (如果是迭代器)
        if not isinstance(items, list):
            items = list(items)
        
        total_files = len(items)
        total_bytes = estimate_total_bytes(items)
        
        tracker = ProgressTracker(
            total_files=total_files,
            total_bytes=total_bytes,
            callback=progress_callback
        )
        
        result = BatchResult()
        
        for item in items:
            try:
                file_size = os.path.getsize(item.local_path)
                self.add_file(item.local_path, item.vfs_path, item.algo_id)
                result.success_count += 1
                result.total_bytes += file_size
                tracker.update(item.local_path, file_size)
                
            except Exception as e:
                if on_error == 'raise':
                    raise
                elif on_error == 'skip':
                    result.failed_count += 1
                    result.failed_files.append((item.local_path, e))
                    tracker.update(item.local_path, 0)
                elif on_error == 'abort':
                    result.failed_count += 1
                    result.failed_files.append((item.local_path, e))
                    break
        
        result.elapsed_time = tracker.finish()
        return result
    
    def add_dir_batch(
        self,
        local_dir: str,
        mount_point: str = "/",
        algo_id: int = 0,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None,
        on_error: str = 'raise',
        progress_callback: Optional[Callable[['ProgressInfo'], None]] = None
    ) -> 'BatchResult':
        """
        批量添加目录 (带进度回调)
        
        Args:
            local_dir: 本地目录路径
            mount_point: 虚拟挂载点
            algo_id: 压缩算法 ID
            recursive: 是否递归扫描
            exclude_patterns: 排除的文件模式
            on_error: 错误处理策略
            progress_callback: 进度回调函数
            
        Returns:
            BatchResult 批量操作结果
        """
        from ..core.batch import scan_directory
        
        items = list(scan_directory(
            local_dir, mount_point, recursive, algo_id, exclude_patterns
        ))
        
        return self.add_files_batch(items, on_error, progress_callback)

