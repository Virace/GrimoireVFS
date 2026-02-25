#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
格式转换工具

提供 Manifest/Archive/JSON 之间的互转功能。
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable, Any, Tuple

from .manifest import ManifestBuilder, ManifestReader
from .archive import ArchiveBuilder, ArchiveReader
from .hooks.base import ChecksumHook, IndexCryptoHook, CompressionHook
from .hooks.registry import (
    get_checksum_hook_by_id,
    get_index_crypto_by_flags,
    get_hook_name,
)
from .utils import normalize_path
from .exceptions import (
    ManifestMergeError,
    ManifestVersionMismatchError,
    ManifestAlgorithmMismatchError,
    PathConflictError,
)


# ==================== 合并结果数据类 ====================


@dataclass
class MergeResult:
    """清单合并操作结果"""
    total_entries: int = 0      # 合并后的总条目数
    source_count: int = 0       # 源清单数量
    duplicate_count: int = 0    # 重复条目数 (被去重/覆盖)
    elapsed_time: float = 0.0   # 耗时 (秒)


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

    @staticmethod
    def json_to_manifest_trusted(
        json_path: str,
        output_path: str,
        checksum_hook_override: Optional[ChecksumHook] = None,
        index_crypto_override: Optional[IndexCryptoHook] = None,
    ) -> None:
        """
        将 JSON 直接还原为二进制 Manifest（完全信任 JSON 内数据）

        与 json_to_manifest 的关键区别：
        - 本方法 **不读取任何本地文件**，也 **不重新计算 checksum**。
        - 直接将 JSON 中的 ``size`` 和 ``checksum`` 原样写入二进制结构。
        - 因此 **无需** 提供 local_base_path。

        .. warning:: 风险说明

            1. **数据完整性无法保证**：若 JSON 中的 checksum/size 已损坏或
               被篡改，生成的 Manifest 将携带错误的校验值，运行时校验
               将通过但文件实际上已损坏。
            2. **checksum 格式依赖**：JSON 中的 checksum 必须是十六进制字符串，
               且与目标算法的输出长度严格匹配；否则写入的字节序列将无意义。
            3. **不适合生产构建**：仅推荐用于以下场景：
               - 快速恢复/迁移已知可信的清单备份
               - 跨环境同步（源文件不可访问，但 JSON 来自可信来源）
               - 单元测试 / CI 中的 Manifest 快速生成

        Args:
            json_path: JSON 文件路径
            output_path: 输出 Manifest 文件路径
            checksum_hook_override: 覆盖 JSON 中的校验 Hook（决定文件头写入的算法 ID）
            index_crypto_override: 覆盖 JSON 中的索引加密 Hook

        Raises:
            ValueError: JSON 中的 checksum 无法解析为字节序列
            KeyError: JSON 条目缺少必要字段 (``path`` / ``size`` / ``checksum``)
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 确定 Hook（支持 override）
        if checksum_hook_override:
            checksum_hook = checksum_hook_override
        else:
            algo_id = data.get('checksum_algo', 0)
            checksum_hook = get_checksum_hook_by_id(algo_id)

        if index_crypto_override:
            index_crypto = index_crypto_override
        else:
            flags = data.get('index_flags', 0)
            index_crypto = get_index_crypto_by_flags(flags)

        magic = data.get('magic', 'GRIM').encode('ascii')[:4].ljust(4, b'\x00')

        builder = ManifestBuilder(
            output_path,
            magic=magic,
            checksum_hook=checksum_hook,
            index_crypto=index_crypto,
        )

        from .utils import split_path, default_path_hash
        from .core.schema import ManifestEntry

        for entry in data.get('entries', []):
            vfs_path = entry['path']
            raw_size = int(entry['size'])

            # 信任 JSON 中的 checksum，直接转换为 bytes
            checksum_hex = entry.get('checksum') or ''
            try:
                checksum_bytes = bytes.fromhex(checksum_hex) if checksum_hex else b''
            except ValueError as exc:
                raise ValueError(
                    f"条目 '{vfs_path}' 的 checksum 无法解析为十六进制字节: {checksum_hex!r}"
                ) from exc

            normalized = normalize_path(vfs_path)
            dir_part, name, ext = split_path(normalized)
            path_hash = default_path_hash(normalized)
            dir_id, name_id, ext_id = builder._path_dict.add_path(dir_part, name, ext)

            manifest_entry = ManifestEntry(
                path_hash=path_hash,
                dir_id=dir_id,
                name_id=name_id,
                ext_id=ext_id,
                raw_size=raw_size,
                checksum=checksum_bytes,
            )
            builder._entries.append(manifest_entry)
            builder._hash_to_path[path_hash] = normalized

        builder.build()


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


# ==================== 清单合并功能 ====================


def _load_manifest_as_dict(source_path: str) -> dict:
    """
    加载清单文件为标准字典格式
    
    自动检测文件格式 (JSON 或 二进制)。
    
    Args:
        source_path: 清单文件路径
        
    Returns:
        标准化的 JSON 字典
    """
    ext = os.path.splitext(source_path)[1].lower()
    
    if ext == '.json':
        # 直接读取 JSON
        with open(source_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        # 二进制格式，先读取文件头
        from .core.schema import FileHeader
        
        with open(source_path, 'rb') as f:
            header = FileHeader.unpack(f.read(FileHeader.SIZE))
        
        algo_id = header.checksum_algo
        flags = header.flags
        
        checksum_hook = get_checksum_hook_by_id(algo_id)
        index_crypto = get_index_crypto_by_flags(flags)
        
        with ManifestReader(
            source_path,
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
            
            return {
                'version': 2,
                'magic': reader.file_header.magic.decode('ascii', errors='ignore').rstrip('\x00'),
                'checksum_algo': algo_id,
                'checksum_algo_name': get_hook_name(checksum_hook),
                'index_flags': flags,
                'index_flags_name': get_hook_name(index_crypto),
                'entry_count': len(entries),
                'entries': entries
            }


def merge_manifests(
    sources: List[str],
    output_path: str,
    local_base_path: Optional[str] = None,
    path_mappings: Optional[Dict[str, str]] = None,
    on_conflict: str = "error",
    output_format: str = "auto",
) -> MergeResult:
    """
    合并多个清单文件
    
    支持 JSON 和二进制清单的混合输入。
    约束: 所有输入必须具有相同的 version、checksum_algo 和 index_flags。
    
    Args:
        sources: 清单文件路径列表 (支持 .json 和 .grim 混合)
        output_path: 输出文件路径
        local_base_path: 本地文件基础路径 (输出为二进制时必需)
        path_mappings: 虚拟路径映射 {虚拟前缀: 本地前缀}
        on_conflict: 路径冲突处理策略:
            - "error": 抛出 PathConflictError (默认)
            - "keep_first": 保留第一个出现的条目
            - "keep_last": 保留最后一个出现的条目
        output_format: 输出格式:
            - "auto": 根据扩展名自动判断
            - "json": 输出 JSON 格式
            - "binary": 输出二进制格式
        
    Returns:
        MergeResult 合并结果
        
    Raises:
        ManifestVersionMismatchError: 版本不匹配
        ManifestAlgorithmMismatchError: 校验算法不匹配
        PathConflictError: 路径冲突 (on_conflict='error' 时)
    """
    if not sources:
        return MergeResult()
    
    start_time = time.time()
    
    # 1. 加载所有源清单
    manifests = [_load_manifest_as_dict(src) for src in sources]
    
    # 2. 验证兼容性
    versions = [m.get('version', 2) for m in manifests]
    if len(set(versions)) > 1:
        raise ManifestVersionMismatchError(versions)
    
    algos = [m.get('checksum_algo', 0) for m in manifests]
    if len(set(algos)) > 1:
        raise ManifestAlgorithmMismatchError(algos)
    
    flags_list = [m.get('index_flags', 0) for m in manifests]
    if len(set(flags_list)) > 1:
        raise ManifestAlgorithmMismatchError(flags_list)  # 复用异常
    
    # 3. 合并 entries
    merged_entries: Dict[str, Tuple[int, dict]] = {}  # path -> (source_index, entry)
    duplicate_count = 0
    
    for src_idx, manifest in enumerate(manifests):
        for entry in manifest.get('entries', []):
            path = normalize_path(entry['path'])
            
            if path in merged_entries:
                duplicate_count += 1
                existing_idx = merged_entries[path][0]
                
                if on_conflict == "error":
                    raise PathConflictError(path, [existing_idx, src_idx])
                elif on_conflict == "keep_first":
                    continue  # 保留已有的
                elif on_conflict == "keep_last":
                    merged_entries[path] = (src_idx, entry)
            else:
                merged_entries[path] = (src_idx, entry)
    
    # 4. 构建输出数据
    base_manifest = manifests[0]
    output_entries = [
        {
            'path': path,
            'size': entry.get('size'),
            'checksum': entry.get('checksum')
        }
        for path, (_, entry) in merged_entries.items()
    ]
    
    merged_data = {
        'version': base_manifest.get('version', 2),
        'magic': base_manifest.get('magic', 'GRIM'),
        'checksum_algo': base_manifest.get('checksum_algo', 0),
        'checksum_algo_name': base_manifest.get('checksum_algo_name'),
        'index_flags': base_manifest.get('index_flags', 0),
        'index_flags_name': base_manifest.get('index_flags_name'),
        'entry_count': len(output_entries),
        'entries': output_entries
    }
    
    # 5. 确定输出格式
    if output_format == "auto":
        ext = os.path.splitext(output_path)[1].lower()
        output_format = "json" if ext == '.json' else "binary"
    
    # 6. 写入输出
    if output_format == "json":
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(merged_data, f, ensure_ascii=False, indent=2)
    else:
        # 输出二进制，需要重新构建
        if local_base_path is None:
            raise ValueError("输出二进制格式时必须提供 local_base_path")
        
        ManifestJsonConverter.json_to_manifest(
            json_path=output_path.replace('.grim', '.tmp.json') if not output_path.endswith('.json') else output_path,
            output_path=output_path if not output_path.endswith('.json') else output_path.replace('.json', '.grim'),
            local_base_path=local_base_path,
            path_mappings=path_mappings
        )
        # 临时 JSON 处理 - 直接写入再转换
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
            json.dump(merged_data, tmp, ensure_ascii=False)
            tmp_path = tmp.name
        
        try:
            ManifestJsonConverter.json_to_manifest(
                json_path=tmp_path,
                output_path=output_path,
                local_base_path=local_base_path,
                path_mappings=path_mappings
            )
        finally:
            os.unlink(tmp_path)
    
    elapsed = time.time() - start_time
    
    return MergeResult(
        total_entries=len(output_entries),
        source_count=len(sources),
        duplicate_count=duplicate_count,
        elapsed_time=elapsed
    )


def patch_manifest(
    base_path: str,
    patch_path: str,
    output_path: str,
    local_base_path: Optional[str] = None,
    path_mappings: Optional[Dict[str, str]] = None,
    output_format: str = "auto",
) -> MergeResult:
    """
    用 patch 清单覆盖 base 清单 (热更新场景)
    
    这是 merge_manifests 的便捷封装，使用 on_conflict="keep_last" 策略。
    适用于版本更新场景：用新版本的部分文件清单覆盖旧版本的完整清单。
    
    示例:
        # 1.0.0 完整清单 + 1.0.1 更新清单 → 1.0.1 完整清单
        result = patch_manifest(
            "v1.0.0_full.json",
            "v1.0.1_update.json",
            "v1.0.1_full.json"
        )
    
    Args:
        base_path: 基础清单文件路径 (旧版本/完整版)
        patch_path: 补丁清单文件路径 (新版本/增量)
        output_path: 输出文件路径
        local_base_path: 本地文件基础路径 (输出为二进制时必需)
        path_mappings: 虚拟路径映射
        output_format: 输出格式 ("auto"/"json"/"binary")
        
    Returns:
        MergeResult 合并结果
    """
    return merge_manifests(
        sources=[base_path, patch_path],
        output_path=output_path,
        local_base_path=local_base_path,
        path_mappings=path_mappings,
        on_conflict="keep_last",
        output_format=output_format,
    )


# ==================== 版本迁移预留框架 ====================


class ManifestVersionMigrator:
    """
    清单版本迁移器 (预留框架)
    
    当库版本升级导致 Schema 变化时，使用此类进行版本迁移。
    
    工作流程:
    1. 使用旧版本库将二进制转为 JSON
    2. 使用此迁移器将 JSON 升级到新版本
    3. 使用新版本库将 JSON 转回二进制
    
    TODO: 当 Schema 版本升级时，在此实现具体迁移逻辑。
    """
    
    # 当前支持的 Schema 版本
    CURRENT_VERSION = 2
    SUPPORTED_VERSIONS = [2]
    
    @classmethod
    def migrate_json(
        cls,
        source_path: str,
        target_version: int = 2
    ) -> dict:
        """
        将旧版本 JSON 迁移到目标版本
        
        TODO: 实现具体版本迁移逻辑。
        目前仅支持版本 2，直接返回原数据。
        
        Args:
            source_path: 源 JSON 文件路径
            target_version: 目标版本号
            
        Returns:
            迁移后的 JSON 字典
            
        Raises:
            ValueError: 不支持的目标版本
        """
        if target_version not in cls.SUPPORTED_VERSIONS:
            raise ValueError(f"不支持的目标版本: {target_version}")
        
        with open(source_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        source_version = data.get('version', 1)
        
        # TODO: 实现版本迁移链
        # 例如: v1 -> v2 -> v3
        # if source_version == 1 and target_version >= 2:
        #     data = cls._migrate_v1_to_v2(data)
        # if source_version <= 2 and target_version >= 3:
        #     data = cls._migrate_v2_to_v3(data)
        
        if source_version == target_version:
            return data
        
        # 当前仅支持版本 2，无需迁移
        data['version'] = target_version
        return data
    
    @classmethod
    def get_supported_versions(cls) -> List[int]:
        """获取支持的版本列表"""
        return cls.SUPPORTED_VERSIONS.copy()
    
    @classmethod
    def can_migrate(cls, source_version: int, target_version: int) -> bool:
        """
        检查是否支持指定的版本迁移
        
        TODO: 随着版本增加，更新此逻辑。
        """
        return (
            source_version in cls.SUPPORTED_VERSIONS and
            target_version in cls.SUPPORTED_VERSIONS
        )
    
    # ==================== 版本迁移实现 (预留) ====================
    
    # @classmethod
    # def _migrate_v1_to_v2(cls, data: dict) -> dict:
    #     """
    #     v1 -> v2 迁移
    #     
    #     TODO: 实现具体迁移逻辑
    #     示例变更:
    #     - 添加 checksum_algo_name 字段
    #     - 重命名某些字段
    #     """
    #     # data['checksum_algo_name'] = ...
    #     # data['version'] = 2
    #     return data
