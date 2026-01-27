#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
格式转换工具

提供 Manifest/Archive/JSON 之间的互转功能。
"""

import json
import os
from typing import Optional, Dict, List, Callable, Any

from .manifest import ManifestBuilder, ManifestReader
from .archive import ArchiveBuilder, ArchiveReader
from .hooks.base import ChecksumHook, IndexCryptoHook, CompressionHook
from .hooks.registry import (
    get_checksum_hook_by_id,
    get_index_crypto_by_flags,
    get_hook_name,
)
from .utils import normalize_path


class ManifestJsonConverter:
    """
    Manifest 和 JSON 互转
    
    JSON 格式 (v2 - 使用数字 ID):
    {
        "version": 2,
        "magic": "GRIM",
        "checksum_algo": 101,    // 算法 ID (从文件头自动读取)
        "index_flags": 2,        // 索引标志位
        "entries": [...]
    }
    """
    
    @staticmethod
    def manifest_to_json(
        manifest_path: str,
        output_path: str,
        indent: int = 2
    ) -> None:
        """
        将 Manifest 转换为 JSON 文件
        
        自动从文件头读取算法 ID 和标志位，无需手动传入 Hook。
        
        Args:
            manifest_path: Manifest 文件路径
            output_path: 输出 JSON 文件路径
            indent: JSON 缩进
        """
        # 1. 从文件头读取 algo_id 和 flags，自动创建 Hook
        # 使用 Reader 读取基本信息 (先不传 Hook 获取文件头)
        from .core.schema import FileHeader
        from .core.binary_io import BinaryReader
        
        with open(manifest_path, 'rb') as f:
            header = FileHeader.unpack(f.read(FileHeader.SIZE))
        
        algo_id = header.checksum_algo
        flags = header.flags
        
        # 2. 根据 ID 自动创建 Hook
        checksum_hook = get_checksum_hook_by_id(algo_id)
        index_crypto = get_index_crypto_by_flags(flags)
        
        # 3. 使用自动检测的 Hook 读取 Manifest
        with ManifestReader(
            manifest_path,
            checksum_hook=checksum_hook,
            index_crypto=index_crypto
        ) as reader:
            entries = []
            for path in reader.list_all():
                entry = reader.get_entry(path)
                entries.append({
                    'path': path,
                    'size': entry.raw_size,
                    'checksum': entry.checksum.hex() if entry.checksum else None
                })
            
            data = {
                'version': 2,
                'magic': reader.file_header.magic.decode('ascii', errors='ignore').rstrip('\x00'),
                'checksum_algo': algo_id,
                'checksum_algo_name': get_hook_name(checksum_hook),
                'index_flags': flags,
                'index_flags_name': get_hook_name(index_crypto),
                'entry_count': len(entries),
                'entries': entries
            }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
    
    @staticmethod
    def json_to_manifest(
        json_path: str,
        output_path: str,
        local_base_path: str,
        path_mappings: Optional[Dict[str, str]] = None,
        checksum_hook_override: Optional[ChecksumHook] = None,
        index_crypto_override: Optional[IndexCryptoHook] = None,
        progress_callback: Optional[Callable] = None
    ) -> 'BatchResult':
        """
        将 JSON 转换为 Manifest 文件
        
        自动根据 JSON 中的 checksum_algo/index_flags 创建对应 Hook。
        
        Args:
            json_path: JSON 文件路径
            output_path: 输出 Manifest 文件路径
            local_base_path: 本地文件基础路径
            path_mappings: 虚拟路径映射 {虚拟前缀: 本地前缀}
            checksum_hook_override: 覆盖 JSON 中的校验 Hook
            index_crypto_override: 覆盖 JSON 中的索引加密 Hook
            progress_callback: 进度回调
            
        Returns:
            BatchResult
        """
        from .core.batch import FileItem, BatchResult, ProgressTracker
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 根据 checksum_algo ID 自动创建 Hook (支持 override)
        if checksum_hook_override:
            checksum_hook = checksum_hook_override
        else:
            algo_id = data.get('checksum_algo', 0)
            checksum_hook = get_checksum_hook_by_id(algo_id)
        
        # 根据 index_flags 自动创建 Hook (支持 override)
        if index_crypto_override:
            index_crypto = index_crypto_override
        else:
            flags = data.get('index_flags', 0)
            index_crypto = get_index_crypto_by_flags(flags)
        
        # 创建路径解析函数
        def resolve_local_path(vfs_path: str) -> str:
            if path_mappings:
                for vfs_prefix, local_prefix in path_mappings.items():
                    if vfs_path.startswith(vfs_prefix):
                        rel = vfs_path[len(vfs_prefix):].lstrip('/')
                        return os.path.join(local_prefix, rel)
            # 默认: base_path + vfs_path
            return os.path.join(local_base_path, vfs_path.lstrip('/'))
        
        # 构建 Manifest
        magic = data.get('magic', 'GRIM').encode('ascii')[:4].ljust(4, b'\x00')
        builder = ManifestBuilder(
            output_path,
            magic=magic,
            checksum_hook=checksum_hook,
            index_crypto=index_crypto
        )
        
        entries = data.get('entries', [])
        tracker = ProgressTracker(
            total_files=len(entries),
            callback=progress_callback
        )
        
        result = BatchResult()
        
        for entry in entries:
            vfs_path = entry['path']
            local_path = resolve_local_path(vfs_path)
            
            try:
                builder.add_file(local_path, vfs_path)
                result.success_count += 1
                result.total_bytes += os.path.getsize(local_path)
                tracker.update(local_path, os.path.getsize(local_path))
            except Exception as e:
                result.failed_count += 1
                result.failed_files.append((local_path, e))
                tracker.update(local_path, 0)
        
        builder.build()
        result.elapsed_time = tracker.finish()
        return result


class ModeConverter:
    """
    Manifest 和 Archive 模式互转
    """
    
    @staticmethod
    def archive_to_manifest(
        archive_path: str,
        output_path: str,
        compression_hooks: Optional[List[CompressionHook]] = None,
        checksum_hook: Optional[ChecksumHook] = None,
        index_crypto_read: Optional[IndexCryptoHook] = None,
        # 输出配置
        output_checksum_hook: Optional[ChecksumHook] = None,
        output_index_crypto: Optional[IndexCryptoHook] = None,
        progress_callback: Optional[Callable] = None
    ) -> 'BatchResult':
        """
        将 Archive 转换为 Manifest
        
        仅保留元信息，不包含文件数据。
        
        Args:
            archive_path: Archive 文件路径
            output_path: 输出 Manifest 文件路径
            compression_hooks: Archive 解压 Hook
            checksum_hook: Archive 校验 Hook
            index_crypto_read: Archive 索引解密 Hook
            output_checksum_hook: 输出 Manifest 校验 Hook (默认继承)
            output_index_crypto: 输出 Manifest 索引加密 Hook (默认不加密)
            progress_callback: 进度回调
            
        Returns:
            BatchResult
        """
        from .core.batch import BatchResult, ProgressTracker
        
        # 使用继承的 checksum_hook
        if output_checksum_hook is None:
            output_checksum_hook = checksum_hook
        
        with ArchiveReader(
            archive_path,
            compression_hooks=compression_hooks,
            checksum_hook=checksum_hook,
            index_crypto=index_crypto_read
        ) as reader:
            all_paths = reader.list_all()
            
            builder = ManifestBuilder(
                output_path,
                magic=reader.file_header.magic,
                checksum_hook=output_checksum_hook,
                index_crypto=output_index_crypto
            )
            
            tracker = ProgressTracker(
                total_files=len(all_paths),
                callback=progress_callback
            )
            
            result = BatchResult()
            
            for vfs_path in all_paths:
                try:
                    # 从 Archive 读取数据并计算校验
                    data = reader.read(vfs_path, verify=False)
                    
                    # 手动添加条目 (绕过 add_file 的本地文件检查)
                    normalized = normalize_path(vfs_path)
                    from .utils import split_path, default_path_hash
                    dir_part, name, ext = split_path(normalized)
                    
                    path_hash = default_path_hash(normalized)
                    dir_id, name_id, ext_id = builder._path_dict.add_path(dir_part, name, ext)
                    
                    checksum = b''
                    if output_checksum_hook:
                        checksum = output_checksum_hook.compute(data)
                    
                    from .core.schema import ManifestEntry
                    entry = ManifestEntry(
                        path_hash=path_hash,
                        dir_id=dir_id,
                        name_id=name_id,
                        ext_id=ext_id,
                        raw_size=len(data),
                        checksum=checksum
                    )
                    builder._entries.append(entry)
                    builder._hash_to_path[path_hash] = normalized
                    
                    result.success_count += 1
                    result.total_bytes += len(data)
                    tracker.update(vfs_path, len(data))
                    
                except Exception as e:
                    result.failed_count += 1
                    result.failed_files.append((vfs_path, e))
                    tracker.update(vfs_path, 0)
            
            builder.build()
            result.elapsed_time = tracker.finish()
            return result
    
    @staticmethod
    def manifest_to_archive(
        manifest_path: str,
        output_path: str,
        local_base_path: str,
        path_mappings: Optional[Dict[str, str]] = None,
        checksum_hook_read: Optional[ChecksumHook] = None,
        index_crypto_read: Optional[IndexCryptoHook] = None,
        # 输出配置
        compression_hooks: Optional[List[CompressionHook]] = None,
        default_algo_id: int = 0,
        output_checksum_hook: Optional[ChecksumHook] = None,
        output_index_crypto: Optional[IndexCryptoHook] = None,
        progress_callback: Optional[Callable] = None,
        on_error: str = 'skip'
    ) -> 'BatchResult':
        """
        将 Manifest 转换为 Archive
        
        需要提供本地文件路径来读取实际数据。
        
        Args:
            manifest_path: Manifest 文件路径
            output_path: 输出 Archive 文件路径
            local_base_path: 本地文件基础路径
            path_mappings: 虚拟路径映射 {虚拟前缀: 本地前缀}
            checksum_hook_read: Manifest 校验 Hook
            index_crypto_read: Manifest 索引解密 Hook
            compression_hooks: 输出 Archive 压缩 Hook 列表
            default_algo_id: 默认压缩算法 ID
            output_checksum_hook: 输出 Archive 校验 Hook
            output_index_crypto: 输出 Archive 索引加密 Hook
            progress_callback: 进度回调
            on_error: 错误处理策略
            
        Returns:
            BatchResult
        """
        from .core.batch import FileItem
        
        # 创建路径解析函数
        def resolve_local_path(vfs_path: str) -> str:
            if path_mappings:
                for vfs_prefix, local_prefix in path_mappings.items():
                    if vfs_path.startswith(vfs_prefix):
                        rel = vfs_path[len(vfs_prefix):].lstrip('/')
                        return os.path.join(local_prefix, rel)
            return os.path.join(local_base_path, vfs_path.lstrip('/'))
        
        with ManifestReader(
            manifest_path,
            checksum_hook=checksum_hook_read,
            index_crypto=index_crypto_read
        ) as reader:
            # 构建 FileItem 列表
            items = []
            for vfs_path in reader.list_all():
                local_path = resolve_local_path(vfs_path)
                items.append(FileItem(
                    local_path=local_path,
                    vfs_path=vfs_path,
                    algo_id=default_algo_id
                ))
        
        # 创建 Archive
        builder = ArchiveBuilder(
            output_path,
            compression_hooks=compression_hooks,
            checksum_hook=output_checksum_hook,
            index_crypto=output_index_crypto
        )
        
        result = builder.add_files_batch(
            items,
            on_error=on_error,
            progress_callback=progress_callback
        )
        
        builder.build()
        return result
