#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hook Registry 单元测试

测试 Hook 注册表的查找功能。
"""

import pytest

from grimoire.hooks.registry import (
    CHECKSUM_REGISTRY,
    get_checksum_hook_by_id,
    get_index_crypto_by_flags,
    get_hook_name,
)
from grimoire.hooks.checksum import (
    NoneChecksumHook,
    CRC32Hook,
    MD5Hook,
    SHA1Hook,
    SHA256Hook,
)
from grimoire.hooks.crypto import (
    ZlibCompressHook,
    XorObfuscateHook,
    ZlibXorHook,
)


class TestChecksumRegistry:
    """测试 CHECKSUM_REGISTRY 常量"""
    
    def test_registry_contains_builtin_hooks(self):
        """注册表应包含所有内置 Hook"""
        assert 0 in CHECKSUM_REGISTRY  # NoneChecksumHook
        assert 1 in CHECKSUM_REGISTRY  # CRC32Hook
        assert 2 in CHECKSUM_REGISTRY  # MD5Hook
        assert 3 in CHECKSUM_REGISTRY  # SHA1Hook
        assert 4 in CHECKSUM_REGISTRY  # SHA256Hook
    
    def test_registry_maps_to_correct_classes(self):
        """注册表应映射到正确的 Hook 类"""
        assert CHECKSUM_REGISTRY[0] == NoneChecksumHook
        assert CHECKSUM_REGISTRY[1] == CRC32Hook
        assert CHECKSUM_REGISTRY[2] == MD5Hook
        assert CHECKSUM_REGISTRY[3] == SHA1Hook
        assert CHECKSUM_REGISTRY[4] == SHA256Hook


class TestGetChecksumHookById:
    """测试 get_checksum_hook_by_id 函数"""
    
    @pytest.mark.parametrize("algo_id,expected_cls", [
        (0, NoneChecksumHook),
        (1, CRC32Hook),
        (2, MD5Hook),
        (3, SHA1Hook),
        (4, SHA256Hook),
    ])
    def test_get_builtin_hook(self, algo_id, expected_cls):
        """应返回正确的内置 Hook 实例"""
        hook = get_checksum_hook_by_id(algo_id)
        
        assert hook is not None
        assert isinstance(hook, expected_cls)
        assert hook.algo_id == algo_id
    
    @pytest.mark.rclone
    @pytest.mark.parametrize("algo_id,expected_algorithm", [
        (101, "md5"),
        (102, "sha1"),
        (103, "sha256"),
        (104, "sha512"),
        (105, "crc32"),
    ])
    def test_get_rclone_hook(self, algo_id, expected_algorithm):
        """应返回正确的 RcloneHashHook 实例"""
        from grimoire.hooks.rclone import RcloneHashHook
        
        hook = get_checksum_hook_by_id(algo_id)
        
        assert hook is not None
        assert isinstance(hook, RcloneHashHook)
        assert hook.algorithm == expected_algorithm
    
    def test_unknown_id_returns_none(self):
        """未知 ID 应返回 None"""
        hook = get_checksum_hook_by_id(999)
        
        assert hook is None
    
    def test_negative_id_returns_none(self):
        """负数 ID 应返回 None"""
        hook = get_checksum_hook_by_id(-1)
        
        assert hook is None


class TestGetIndexCryptoByFlags:
    """测试 get_index_crypto_by_flags 函数"""
    
    @pytest.mark.parametrize("flags,expected_cls", [
        (0x01, XorObfuscateHook),
        (0x02, ZlibCompressHook),
        (0x03, ZlibXorHook),
    ])
    def test_get_builtin_crypto(self, flags, expected_cls):
        """应返回正确的索引加密 Hook 实例"""
        hook = get_index_crypto_by_flags(flags)
        
        assert hook is not None
        assert isinstance(hook, expected_cls)
        assert hook.flags_id == flags
    
    def test_zero_flags_returns_none(self):
        """flags=0 应返回 None (无加密)"""
        hook = get_index_crypto_by_flags(0)
        
        assert hook is None
    
    def test_unknown_flags_returns_none(self):
        """未知 flags 应返回 None"""
        hook = get_index_crypto_by_flags(0xFF)
        
        assert hook is None


class TestGetHookName:
    """测试 get_hook_name 函数"""
    
    @pytest.mark.parametrize("hook_cls,expected_name", [
        (NoneChecksumHook, "none"),
        (CRC32Hook, "crc32"),
        (MD5Hook, "md5"),
        (SHA1Hook, "sha1"),
        (SHA256Hook, "sha256"),
    ])
    def test_checksum_hook_names(self, hook_cls, expected_name):
        """应返回正确的 Checksum Hook 名称"""
        hook = hook_cls()
        name = get_hook_name(hook)
        
        assert name == expected_name
    
    @pytest.mark.parametrize("hook_cls,expected_name", [
        (ZlibCompressHook, "zlib"),
        (XorObfuscateHook, "xor"),
        (ZlibXorHook, "zlib_xor"),
    ])
    def test_crypto_hook_names(self, hook_cls, expected_name):
        """应返回正确的索引加密 Hook 名称"""
        hook = hook_cls()
        name = get_hook_name(hook)
        
        assert name == expected_name
    
    def test_none_hook_returns_none(self):
        """None 输入应返回 None"""
        name = get_hook_name(None)
        
        assert name is None
    
    @pytest.mark.rclone
    def test_rclone_hook_name(self):
        """RcloneHashHook 应返回 rclone:algorithm 格式"""
        from grimoire.hooks.rclone import RcloneHashHook
        
        hook = RcloneHashHook("sha256")
        name = get_hook_name(hook)
        
        assert name == "rclone:sha256"


class TestRegistryIntegration:
    """测试注册表与实际使用场景的集成"""
    
    def test_roundtrip_checksum_id(self):
        """通过 ID 获取的 Hook 应与原 Hook 行为一致"""
        original = MD5Hook()
        data = b"Test data"
        original_checksum = original.compute(data)
        
        # 通过 ID 获取
        retrieved = get_checksum_hook_by_id(original.algo_id)
        retrieved_checksum = retrieved.compute(data)
        
        assert original_checksum == retrieved_checksum
    
    def test_roundtrip_crypto_flags(self):
        """通过 flags 获取的 Hook 应与原 Hook 行为一致"""
        original = ZlibCompressHook()
        data = b"Test data to compress " * 100
        encrypted = original.encrypt(data)
        
        # 通过 flags 获取
        retrieved = get_index_crypto_by_flags(original.flags_id)
        decrypted = retrieved.decrypt(encrypted)
        
        assert decrypted == data
