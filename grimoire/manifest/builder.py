#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Manifest 文件构建器

用于创建 Manifest 模式的索引清单文件。
"""

import os
from typing import Optional, List, Callable

from ..core.binary_io import BinaryWriter
from ..core.schema import FileHeader, IndexHeader, ManifestEntry, MODE_MANIFEST, FLAG_INDEX_ENCRYPTED
from ..core.string_table import PathDictionary
from ..hooks.base import ChecksumHook, IndexCryptoHook
from ..utils import normalize_path, split_path, default_path_hash
from ..exceptions import HashCollisionError


class ManifestBuilder:
    """
    Manifest 文件构建器
    
    用于创建清单文件，记录文件路径、大小和校验信息。
    """
    
    def __init__(
        self,
        output_path: str,
        magic: bytes = b'GRIM',
        checksum_hook: Optional[ChecksumHook] = None,
        index_crypto: Optional[IndexCryptoHook] = None,
        path_hash_func: Optional[Callable[[str], int]] = None
    ):
        """
        初始化构建器
        
        Args:
            output_path: 输出文件路径
            magic: 自定义魔法数 (4 bytes)
            checksum_hook: 校验算法钩子 (可选)
            index_crypto: 索引加密钩子 (可选)
            path_hash_func: 自定义路径 Hash 函数 (可选)
        """
        self._output_path = output_path
        self._magic = magic
        self._checksum_hook = checksum_hook
        self._index_crypto = index_crypto
        self._path_hash_func = path_hash_func or default_path_hash
        
        # 内部状态
        self._path_dict = PathDictionary()
        self._entries: List[ManifestEntry] = []
        self._hash_to_path: dict[int, str] = {}  # 用于冲突检测
    
    def add_file(self, local_path: str, vfs_path: Optional[str] = None) -> None:
        """
        添加单个文件到清单
        
        Args:
            local_path: 本地文件路径
            vfs_path: 虚拟路径 (默认使用文件名)
            
        Raises:
            FileNotFoundError: 本地文件不存在
            HashCollisionError: 路径 Hash 冲突
        """
        # 1. 检查文件存在
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"文件不存在: {local_path}")
        
        # 2. 确定虚拟路径
        if vfs_path is None:
            vfs_path = "/" + os.path.basename(local_path)
        
        # 3. 规范化并拆分路径
        normalized = normalize_path(vfs_path)
        dir_part, name, ext = split_path(normalized)
        
        # 4. 计算 path_hash 并检查冲突
        path_hash = self._path_hash_func(normalized)
        if path_hash in self._hash_to_path:
            existing = self._hash_to_path[path_hash]
            if existing != normalized:  # 真正的冲突
                raise HashCollisionError(existing, normalized, path_hash)
            else:  # 重复添加同一路径，跳过
                return
        self._hash_to_path[path_hash] = normalized
        
        # 5. 添加到字典
        dir_id, name_id, ext_id = self._path_dict.add_path(dir_part, name, ext)
        
        # 6. 读取文件并计算校验值
        with open(local_path, 'rb') as f:
            data = f.read()
        raw_size = len(data)
        
        checksum = b''
        if self._checksum_hook:
            checksum = self._checksum_hook.compute(data)
        
        # 7. 创建 Entry
        entry = ManifestEntry(
            path_hash=path_hash,
            dir_id=dir_id,
            name_id=name_id,
            ext_id=ext_id,
            raw_size=raw_size,
            checksum=checksum
        )
        self._entries.append(entry)
    
    def add_dir(
        self, 
        local_dir: str, 
        mount_point: str = "/",
        recursive: bool = True
    ) -> int:
        """
        添加目录到清单
        
        Args:
            local_dir: 本地目录路径
            mount_point: 虚拟挂载点
            recursive: 是否递归扫描子目录
            
        Returns:
            添加的文件数量
            
        Raises:
            NotADirectoryError: 路径不是目录
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
                    self.add_file(local_path, vfs_path)
                    count += 1
        else:
            for filename in os.listdir(local_dir):
                local_path = os.path.join(local_dir, filename)
                if os.path.isfile(local_path):
                    vfs_path = mount_point + "/" + filename
                    self.add_file(local_path, vfs_path)
                    count += 1
        
        return count
    
    def build(self) -> None:
        """
        构建并写入 Manifest 文件
        
        执行流程:
        1. 预留 FileHeader 空间
        2. 写入 IndexHeader
        3. 写入 String Tables (可选加密)
        4. 写入 Entry Table
        5. 回写 FileHeader 和 IndexHeader
        """
        with open(self._output_path, 'w+b') as f:
            writer = BinaryWriter(f)
            
            # ========== 1. 预留 FileHeader 空间 ==========
            writer.reserve(FileHeader.SIZE)
            
            # ========== 2. 预留 IndexHeader 空间 ==========
            index_start = writer.position
            writer.reserve(IndexHeader.SIZE)
            
            # ========== 3. 写入 String Tables ==========
            string_start = writer.position
            self._path_dict.pack(writer)
            string_size = writer.position - string_start
            
            # 如果需要加密/压缩
            if self._index_crypto:
                # 读回 String Tables 数据
                f.seek(string_start)
                string_data = f.read(string_size)
                
                # 加密/压缩
                encrypted = self._index_crypto.encrypt(string_data)
                
                # 重写
                f.seek(string_start)
                f.write(encrypted)
                
                # 更新 string_size 为压缩后的大小！
                string_size = len(encrypted)
                
                # 更新位置
                writer.seek(string_start + string_size)
            
            # ========== 4. 写入 Entry Table ==========
            checksum_size = self._checksum_hook.digest_size if self._checksum_hook else 0
            
            for entry in self._entries:
                writer.write_bytes(entry.pack())
            
            index_size = writer.position - index_start
            
            # ========== 5. 回写 IndexHeader ==========
            index_header = IndexHeader(
                dir_count=len(self._path_dict.dirs),
                name_count=len(self._path_dict.names),
                ext_count=len(self._path_dict.exts),
                string_table_size=string_size,  # 这里现在是正确的压缩后大小
                checksum_size=checksum_size
            )
            writer.seek(index_start)
            writer.write_bytes(index_header.pack())
            
            # ========== 6. 回写 FileHeader ==========
            flags = FLAG_INDEX_ENCRYPTED if self._index_crypto else 0
            
            file_header = FileHeader(
                magic=self._magic,
                version=3,
                mode=MODE_MANIFEST,
                flags=flags,
                checksum_algo=self._checksum_hook.algo_id if self._checksum_hook else 0,
                index_offset=FileHeader.SIZE,
                index_size=index_size,
                data_offset=0,  # Manifest 模式无数据区
                entry_count=len(self._entries)
            )
            writer.seek(0)
            writer.write_bytes(file_header.pack())
    
    @property
    def entry_count(self) -> int:
        """已添加的文件数量"""
        return len(self._entries)
    
    @property
    def path_stats(self) -> dict:
        """路径字典统计信息"""
        return self._path_dict.stats
    
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
            estimate_total_bytes
        )
        
        # 转换为列表以获取总数
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
                self.add_file(item.local_path, item.vfs_path)
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
            recursive: 是否递归扫描
            exclude_patterns: 排除的文件模式
            on_error: 错误处理策略
            progress_callback: 进度回调函数
            
        Returns:
            BatchResult 批量操作结果
        """
        from ..core.batch import scan_directory, FileItem
        
        # 为 Manifest 模式创建 FileItem (algo_id 无用，设为 0)
        items = list(scan_directory(
            local_dir, mount_point, recursive, algo_id=0, exclude_patterns=exclude_patterns
        ))
        
        return self.add_files_batch(items, on_error, progress_callback)

