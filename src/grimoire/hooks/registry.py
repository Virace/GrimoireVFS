#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hook 注册表

自动从 Hook 类收集 algo_id，提供根据 ID 查找 Hook 的功能。
"""

from typing import Dict, Type, Optional, TYPE_CHECKING

from .base import ChecksumHook, IndexCryptoHook
from .checksum import NoneChecksumHook, CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook

if TYPE_CHECKING:
    from .rclone import RcloneHashHook


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
    
    支持:
    - 内置 Hook (algo_id 0-4)
    - Rclone Hook (algo_id 101-113)
    
    Args:
        algo_id: 算法 ID (来自 FileHeader.checksum_algo)
        
    Returns:
        对应的 Hook 实例，未找到返回 None
    """
    # 1. 先查内置 Hook
    if algo_id in CHECKSUM_REGISTRY:
        return CHECKSUM_REGISTRY[algo_id]()
    
    # 2. 检查 Rclone 范围 (101-113)
    from .rclone import RcloneHashHook
    for name, (aid, _) in RcloneHashHook.ALGORITHMS.items():
        if aid == algo_id:
            return RcloneHashHook(name, check_on_init=False)
    
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
