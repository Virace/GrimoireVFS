#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ChecksumHook 单元测试

测试所有内置校验算法 Hook 的属性和方法。
"""

import hashlib
import zlib

import pytest

from grimoire.hooks.checksum import (
    NoneChecksumHook,
    CRC32Hook,
    MD5Hook,
    SHA1Hook,
    SHA256Hook,
)


class TestChecksumHookProperties:
    """测试各校验 Hook 的属性"""
    
    @pytest.mark.parametrize("hook_cls,expected_id,expected_size,expected_name", [
        (NoneChecksumHook, 0, 0, "none"),
        (CRC32Hook, 1, 4, "crc32"),
        (MD5Hook, 2, 16, "md5"),
        (SHA1Hook, 3, 20, "sha1"),
        (SHA256Hook, 4, 32, "sha256"),
    ])
    def test_properties(self, hook_cls, expected_id, expected_size, expected_name):
        """验证 algo_id、digest_size 和 display_name 属性"""
        hook = hook_cls()
        
        assert hook.algo_id == expected_id
        assert hook.digest_size == expected_size
        assert hook.display_name == expected_name


class TestChecksumCompute:
    """测试各校验 Hook 的 compute 方法"""
    
    @pytest.fixture
    def test_data(self) -> bytes:
        return b"Hello, GrimoireVFS! Test data for checksum."
    
    def test_none_checksum_returns_empty(self, test_data):
        """NoneChecksumHook 应返回空字节"""
        hook = NoneChecksumHook()
        result = hook.compute(test_data)
        
        assert result == b''
        assert len(result) == hook.digest_size
    
    def test_crc32_matches_zlib(self, test_data):
        """CRC32Hook 应与 zlib.crc32 结果一致"""
        hook = CRC32Hook()
        result = hook.compute(test_data)
        
        expected = (zlib.crc32(test_data) & 0xFFFFFFFF).to_bytes(4, 'little')
        assert result == expected
        assert len(result) == hook.digest_size
    
    def test_md5_matches_hashlib(self, test_data):
        """MD5Hook 应与 hashlib.md5 结果一致"""
        hook = MD5Hook()
        result = hook.compute(test_data)
        
        expected = hashlib.md5(test_data).digest()
        assert result == expected
        assert len(result) == hook.digest_size
    
    def test_sha1_matches_hashlib(self, test_data):
        """SHA1Hook 应与 hashlib.sha1 结果一致"""
        hook = SHA1Hook()
        result = hook.compute(test_data)
        
        expected = hashlib.sha1(test_data).digest()
        assert result == expected
        assert len(result) == hook.digest_size
    
    def test_sha256_matches_hashlib(self, test_data):
        """SHA256Hook 应与 hashlib.sha256 结果一致"""
        hook = SHA256Hook()
        result = hook.compute(test_data)
        
        expected = hashlib.sha256(test_data).digest()
        assert result == expected
        assert len(result) == hook.digest_size


class TestChecksumVerify:
    """测试各校验 Hook 的 verify 方法"""
    
    @pytest.fixture
    def test_data(self) -> bytes:
        return b"Data to verify"
    
    def test_none_checksum_always_passes(self, test_data):
        """NoneChecksumHook.verify 应始终返回 True"""
        hook = NoneChecksumHook()
        
        assert hook.verify(test_data, b'') is True
        assert hook.verify(test_data, b'anything') is True
        assert hook.verify(b'different data', b'') is True
    
    @pytest.mark.parametrize("hook_cls", [
        CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_verify_correct_checksum(self, hook_cls, test_data):
        """验证正确的校验值应返回 True"""
        hook = hook_cls()
        checksum = hook.compute(test_data)
        
        assert hook.verify(test_data, checksum) is True
    
    @pytest.mark.parametrize("hook_cls", [
        CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_verify_incorrect_checksum(self, hook_cls, test_data):
        """验证错误的校验值应返回 False"""
        hook = hook_cls()
        wrong_checksum = b'\x00' * hook.digest_size
        
        assert hook.verify(test_data, wrong_checksum) is False
    
    @pytest.mark.parametrize("hook_cls", [
        CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_verify_modified_data(self, hook_cls, test_data):
        """修改数据后校验应失败"""
        hook = hook_cls()
        original_checksum = hook.compute(test_data)
        modified_data = test_data + b' modified'
        
        assert hook.verify(modified_data, original_checksum) is False


class TestChecksumEdgeCases:
    """测试边界情况"""
    
    @pytest.mark.parametrize("hook_cls", [
        NoneChecksumHook, CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_empty_data(self, hook_cls):
        """空数据应正常处理"""
        hook = hook_cls()
        result = hook.compute(b'')
        
        assert len(result) == hook.digest_size
        # 验证空数据的校验值也能正确验证
        assert hook.verify(b'', result) is True
    
    @pytest.mark.parametrize("hook_cls", [
        CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_large_data(self, hook_cls):
        """大数据应正常处理"""
        hook = hook_cls()
        large_data = b'x' * (1024 * 1024)  # 1MB
        
        result = hook.compute(large_data)
        assert len(result) == hook.digest_size
        assert hook.verify(large_data, result) is True
    
    @pytest.mark.parametrize("hook_cls", [
        CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_binary_data(self, hook_cls):
        """二进制数据应正常处理"""
        hook = hook_cls()
        binary_data = bytes(range(256))
        
        result = hook.compute(binary_data)
        assert len(result) == hook.digest_size
        assert hook.verify(binary_data, result) is True
    
    @pytest.mark.parametrize("hook_cls", [
        CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_unicode_content(self, hook_cls):
        """Unicode 内容 (UTF-8 编码后) 应正常处理"""
        hook = hook_cls()
        unicode_data = "你好，GrimoireVFS！🎮".encode('utf-8')
        
        result = hook.compute(unicode_data)
        assert len(result) == hook.digest_size
        assert hook.verify(unicode_data, result) is True


class TestChecksumDeterminism:
    """测试校验结果的确定性"""
    
    @pytest.mark.parametrize("hook_cls", [
        NoneChecksumHook, CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_same_data_same_result(self, hook_cls):
        """相同数据应产生相同结果"""
        hook = hook_cls()
        data = b"Deterministic test data"
        
        result1 = hook.compute(data)
        result2 = hook.compute(data)
        
        assert result1 == result2
    
    @pytest.mark.parametrize("hook_cls", [
        CRC32Hook, MD5Hook, SHA1Hook, SHA256Hook
    ])
    def test_different_data_different_result(self, hook_cls):
        """不同数据应产生不同结果 (极少碰撞)"""
        hook = hook_cls()
        
        result1 = hook.compute(b"Data A")
        result2 = hook.compute(b"Data B")
        
        assert result1 != result2
