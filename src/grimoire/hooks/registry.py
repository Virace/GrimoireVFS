#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hook 注册表

提供统一的算法 ID 映射和 Hook 查找功能。
支持内置 Python 实现和外置工具 (fhash, rclone)。
"""

from typing import Dict, Type, Optional, Tuple, TYPE_CHECKING

from .base import ChecksumHook, IndexCryptoHook
from .checksum import NoneChecksumHook, CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook

if TYPE_CHECKING:
    from .fhash import FhashHook
    from .rclone import RcloneHashHook


# ==================== 统一算法 ID 映射表 ====================

# 算法名 -> (algo_id, digest_size)
# 这是全局唯一的算法定义,所有 Hook 实现必须使用相同的 ID
ALGORITHM_REGISTRY: Dict[str, Tuple[int, int]] = {
    'none':     (0, 0),
    'crc32':    (1, 4),
    'md5':      (2, 16),
    'sha1':     (3, 20),
    'sha256':   (4, 32),
    'sha512':   (5, 64),
    'blake3':   (6, 32),
    'xxh3':     (7, 8),
    'xxh128':   (8, 16),
    'quickxor': (9, 20),
}

# algo_id -> 算法名 (反向映射)
ID_TO_ALGORITHM: Dict[int, str] = {v[0]: k for k, v in ALGORITHM_REGISTRY.items()}


# ==================== Checksum Hook 注册表 ====================

# 内置 Checksum Hook 列表 (新增 Hook 时只需在此添加)
_BUILTIN_CHECKSUM_HOOKS = [
    NoneChecksumHook,
    CRC32Hook,
    MD5Hook,
    SHA1Hook,
    SHA256Hook,
]


def _build_checksum_registry() -> Dict[int, Type[ChecksumHook]]:
    """从 Hook 类自动构建 algo_id -> Hook 类映射"""
    registry = {}
    for hook_cls in _BUILTIN_CHECKSUM_HOOKS:
        instance = hook_cls()
        registry[instance.algo_id] = hook_cls
    return registry


# algo_id -> Hook 类 映射表
CHECKSUM_REGISTRY: Dict[int, Type[ChecksumHook]] = _build_checksum_registry()


def get_checksum_hook_by_id(algo_id: int) -> Optional[ChecksumHook]:
    """
    根据 algo_id 获取 ChecksumHook 实例
    
    优先使用内置 Python 实现，对于内置不支持的算法 (blake3, xxh3 等)
    会尝试使用外置工具。
    
    Args:
        algo_id: 算法 ID
        
    Returns:
        对应的 Hook 实例，未找到返回 None
    """
    # 1. 优先使用内置 Hook
    if algo_id in CHECKSUM_REGISTRY:
        return CHECKSUM_REGISTRY[algo_id]()
    
    # 2. 对于内置不支持的算法，尝试使用外置工具
    algorithm = ID_TO_ALGORITHM.get(algo_id)
    if algorithm:
        hook = get_external_checksum_hook(algorithm)
        if hook:
            return hook
    
    return None


def get_external_checksum_hook(algorithm: str) -> Optional[ChecksumHook]:
    """
    获取外置工具的 ChecksumHook
    
    优先使用 fhash，其次是 rclone。
    
    Args:
        algorithm: 算法名 (如 'sha256', 'quickxor')
        
    Returns:
        Hook 实例，工具不可用返回 None
    """
    # 尝试 fhash
    try:
        from .fhash import FhashHook
        if algorithm.lower() in FhashHook.SUPPORTED_ALGORITHMS:
            return FhashHook(algorithm, check_on_init=True)
    except Exception:
        pass
    
    # 尝试 rclone
    try:
        from .rclone import RcloneHashHook
        if algorithm.lower() in RcloneHashHook.SUPPORTED_ALGORITHMS:
            return RcloneHashHook(algorithm, check_on_init=True)
    except Exception:
        pass
    
    return None


def get_best_checksum_hook(algorithm: str) -> Optional[ChecksumHook]:
    """
    获取指定算法的最佳 Hook 实现
    
    优先顺序:
    1. fhash (如果可用)
    2. 内置 Python 实现
    3. rclone (如果可用)
    
    对于批量文件处理场景，建议使用此函数获取外置工具实现。
    
    Args:
        algorithm: 算法名
        
    Returns:
        最佳的 Hook 实例，失败返回 None
    """
    algorithm = algorithm.lower()
    
    if algorithm not in ALGORITHM_REGISTRY:
        return None
    
    algo_id = ALGORITHM_REGISTRY[algorithm][0]
    
    # 1. 尝试 fhash (批量处理性能最佳)
    try:
        from .fhash import FhashHook
        if algorithm in FhashHook.SUPPORTED_ALGORITHMS:
            return FhashHook(algorithm, check_on_init=True)
    except Exception:
        pass
    
    # 2. 内置实现
    if algo_id in CHECKSUM_REGISTRY:
        return CHECKSUM_REGISTRY[algo_id]()
    
    # 3. rclone
    try:
        from .rclone import RcloneHashHook
        if algorithm in RcloneHashHook.SUPPORTED_ALGORITHMS:
            return RcloneHashHook(algorithm, check_on_init=True)
    except Exception:
        pass
    
    return None


# ==================== IndexCrypto Hook 注册表 ====================

# 内置 IndexCrypto Hook 列表
_BUILTIN_INDEX_CRYPTO_HOOKS = None  # 延迟初始化避免循环导入


def _get_index_crypto_hooks():
    """延迟加载 IndexCrypto Hook 列表"""
    global _BUILTIN_INDEX_CRYPTO_HOOKS
    if _BUILTIN_INDEX_CRYPTO_HOOKS is None:
        from .crypto import ZlibCompressHook, XorObfuscateHook, ZlibXorHook
        _BUILTIN_INDEX_CRYPTO_HOOKS = [
            ZlibCompressHook,
            XorObfuscateHook, 
            ZlibXorHook,
        ]
    return _BUILTIN_INDEX_CRYPTO_HOOKS


def _build_index_crypto_registry() -> Dict[int, Type[IndexCryptoHook]]:
    """从 Hook 类自动构建 flags_id -> Hook 类映射"""
    registry = {}
    for hook_cls in _get_index_crypto_hooks():
        instance = hook_cls()
        registry[instance.flags_id] = hook_cls
    return registry


# 延迟构建的注册表
_INDEX_CRYPTO_REGISTRY: Optional[Dict[int, Type[IndexCryptoHook]]] = None


def get_index_crypto_by_flags(flags: int) -> Optional[IndexCryptoHook]:
    """
    根据 flags 获取 IndexCryptoHook 实例
    
    自动从已注册的 Hook 类中查找匹配的 flags_id。
    
    Args:
        flags: 标志位 (来自 FileHeader.flags)
        
    Returns:
        对应的 Hook 实例，未找到返回 None
    """
    global _INDEX_CRYPTO_REGISTRY
    if _INDEX_CRYPTO_REGISTRY is None:
        _INDEX_CRYPTO_REGISTRY = _build_index_crypto_registry()
    
    if flags in _INDEX_CRYPTO_REGISTRY:
        return _INDEX_CRYPTO_REGISTRY[flags]()
    
    return None


def get_hook_name(hook) -> Optional[str]:
    """
    获取 Hook 的可读名称 (用于 JSON 输出的可选字段)
    
    直接使用 Hook 的 display_name 属性。
    
    Args:
        hook: Hook 实例
        
    Returns:
        可读名称字符串
    """
    if hook is None:
        return None
    
    return hook.display_name
