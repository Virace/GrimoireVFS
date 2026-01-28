#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Hook Registry 单元测试

测试 Hook 注册表的查找功能。
"""

import pytest

from grimoire.hooks.registry import (
    CHECKSUM_REGISTRY,
    ALGORITHM_REGISTRY,
    ID_TO_ALGORITHM,
    get_checksum_hook_by_id,
    get_index_crypto_by_flags,
    get_hook_name,
    get_best_checksum_hook,
    get_external_checksum_hook,
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


class TestAlgorithmRegistry:
    """测试统一算法 ID 映射表"""
    
    def test_algorithm_registry_has_required_algorithms(self):
        """应包含所有必需的算法"""
        required = ['none', 'crc32', 'md5', 'sha1', 'sha256', 'sha512',
                    'blake3', 'xxh3', 'xxh128', 'quickxor']
        for algo in required:
            assert algo in ALGORITHM_REGISTRY
    
    def test_algorithm_ids_are_unique(self):
        """所有算法 ID 应该唯一"""
        ids = [v[0] for v in ALGORITHM_REGISTRY.values()]
        assert len(ids) == len(set(ids))
    
    def test_id_to_algorithm_reverse_mapping(self):
        """反向映射应正确"""
        for algo, (algo_id, _) in ALGORITHM_REGISTRY.items():
            assert ID_TO_ALGORITHM[algo_id] == algo


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
    
    def test_unknown_id_returns_none(self):
        """未知 ID 应返回 None"""
        hook = get_checksum_hook_by_id(999)
        
        assert hook is None
    
    def test_negative_id_returns_none(self):
        """负数 ID 应返回 None"""
        hook = get_checksum_hook_by_id(-1)
        
        assert hook is None


class TestGetBestChecksumHook:
    """测试 get_best_checksum_hook 函数"""
    
    def test_builtin_algorithm(self):
        """内置算法应返回有效 Hook"""
        hook = get_best_checksum_hook('md5')
        
        assert hook is not None
        assert hook.algo_id == 2
    
    def test_unknown_algorithm_returns_none(self):
        """未知算法应返回 None"""
        hook = get_best_checksum_hook('unknown_algo')
        
        assert hook is None
    
    def test_case_insensitive(self):
        """算法名应不区分大小写"""
        hook1 = get_best_checksum_hook('MD5')
        hook2 = get_best_checksum_hook('md5')
        
        assert hook1 is not None
        assert hook2 is not None
        assert hook1.algo_id == hook2.algo_id


@pytest.mark.fhash
class TestGetExternalChecksumHookFhash:
    """测试外置工具 Hook 获取 (需要 fhash)"""
    
    def test_fhash_hook_for_quickxor(self):
        """quickxor 应返回 fhash Hook"""
        from grimoire.hooks.fhash import FhashHook
        
        hook = get_external_checksum_hook('quickxor')
        
        assert hook is not None
        assert isinstance(hook, FhashHook)
        assert hook.algo_id == 9


@pytest.mark.rclone
class TestGetExternalChecksumHookRclone:
    """测试外置工具 Hook 获取 (需要 rclone)"""
    
    def test_rclone_hook_for_sha256(self):
        """sha256 应能返回 rclone Hook"""
        from grimoire.hooks.rclone import RcloneHashHook
        
        # 如果 fhash 可用会返回 fhash，否则返回 rclone
        hook = get_external_checksum_hook('sha256')
        
        assert hook is not None
        assert hook.algo_id == 4


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
    
    @pytest.mark.fhash
    def test_fhash_hook_name(self):
        """FhashHook 应返回 fhash:algorithm 格式"""
        from grimoire.hooks.fhash import FhashHook
        
        hook = FhashHook("sha256")
        name = get_hook_name(hook)
        
        assert name == "fhash:sha256"
    
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
    
    def test_unified_algo_id_consistency(self):
        """统一 ID 应保持一致性"""
        # 内置和外置工具的 MD5 应使用相同 ID
        builtin_md5 = MD5Hook()
        
        assert builtin_md5.algo_id == 2
        assert ALGORITHM_REGISTRY['md5'][0] == 2
