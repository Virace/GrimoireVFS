#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IndexCryptoHook 单元测试

测试所有内置索引加密/压缩 Hook 的属性和方法。
"""

import pytest

from grimoire.hooks.crypto import (
    ZlibCompressHook,
    XorObfuscateHook,
    ZlibXorHook,
)


class TestIndexCryptoProperties:
    """测试各索引加密 Hook 的属性"""
    
    @pytest.mark.parametrize("hook_cls,expected_flags,expected_name", [
        (ZlibCompressHook, 0x02, "zlib"),
        (XorObfuscateHook, 0x01, "xor"),
        (ZlibXorHook, 0x03, "zlib_xor"),
    ])
    def test_properties(self, hook_cls, expected_flags, expected_name):
        """验证 flags_id 和 display_name 属性"""
        hook = hook_cls()
        
        assert hook.flags_id == expected_flags
        assert hook.display_name == expected_name


class TestZlibCompressHook:
    """测试 ZlibCompressHook"""
    
    @pytest.fixture
    def hook(self):
        return ZlibCompressHook()
    
    @pytest.fixture
    def compressible_data(self) -> bytes:
        """可压缩的重复数据"""
        return b"Hello, GrimoireVFS! " * 100
    
    def test_encrypt_decrypt_roundtrip(self, hook, compressible_data):
        """加密解密往返应保持数据一致"""
        encrypted = hook.encrypt(compressible_data)
        decrypted = hook.decrypt(encrypted)
        
        assert decrypted == compressible_data
    
    def test_compress_reduces_size(self, hook, compressible_data):
        """压缩应减少可压缩数据的大小"""
        compressed = hook.encrypt(compressible_data)
        
        assert len(compressed) < len(compressible_data)
    
    def test_custom_level(self):
        """测试自定义压缩级别"""
        data = b"Test data " * 100
        
        hook_low = ZlibCompressHook(level=1)
        hook_high = ZlibCompressHook(level=9)
        
        compressed_low = hook_low.encrypt(data)
        compressed_high = hook_high.encrypt(data)
        
        # 高压缩级别应产生更小的输出
        assert len(compressed_high) <= len(compressed_low)
        
        # 两者都应能正确解压
        assert hook_low.decrypt(compressed_low) == data
        assert hook_high.decrypt(compressed_high) == data


class TestXorObfuscateHook:
    """测试 XorObfuscateHook"""
    
    @pytest.fixture
    def hook(self):
        return XorObfuscateHook()
    
    @pytest.fixture
    def test_data(self) -> bytes:
        return b"Secret index data to obfuscate"
    
    def test_encrypt_decrypt_roundtrip(self, hook, test_data):
        """加密解密往返应保持数据一致"""
        encrypted = hook.encrypt(test_data)
        decrypted = hook.decrypt(encrypted)
        
        assert decrypted == test_data
    
    def test_encrypt_changes_data(self, hook, test_data):
        """加密应改变数据"""
        encrypted = hook.encrypt(test_data)
        
        assert encrypted != test_data
    
    def test_size_preserved(self, hook, test_data):
        """XOR 加密应保持数据大小"""
        encrypted = hook.encrypt(test_data)
        
        assert len(encrypted) == len(test_data)
    
    def test_custom_key(self):
        """测试自定义密钥"""
        data = b"Test data"
        
        hook1 = XorObfuscateHook(key=b'key1')
        hook2 = XorObfuscateHook(key=b'key2')
        
        encrypted1 = hook1.encrypt(data)
        encrypted2 = hook2.encrypt(data)
        
        # 不同密钥应产生不同输出
        assert encrypted1 != encrypted2
        
        # 各自能正确解密
        assert hook1.decrypt(encrypted1) == data
        assert hook2.decrypt(encrypted2) == data
        
        # 错误密钥无法解密
        assert hook1.decrypt(encrypted2) != data


class TestZlibXorHook:
    """测试 ZlibXorHook (压缩+混淆)"""
    
    @pytest.fixture
    def hook(self):
        return ZlibXorHook()
    
    @pytest.fixture
    def compressible_data(self) -> bytes:
        return b"Compressible data pattern! " * 50
    
    def test_encrypt_decrypt_roundtrip(self, hook, compressible_data):
        """加密解密往返应保持数据一致"""
        encrypted = hook.encrypt(compressible_data)
        decrypted = hook.decrypt(encrypted)
        
        assert decrypted == compressible_data
    
    def test_compress_then_obfuscate(self, hook, compressible_data):
        """应先压缩后混淆，大小应减少"""
        encrypted = hook.encrypt(compressible_data)
        
        # 压缩后大小应减少
        assert len(encrypted) < len(compressible_data)
    
    def test_custom_parameters(self):
        """测试自定义参数"""
        data = b"Custom params test " * 50
        
        hook = ZlibXorHook(key=b'custom_key', level=9)
        
        encrypted = hook.encrypt(data)
        decrypted = hook.decrypt(encrypted)
        
        assert decrypted == data


class TestIndexCryptoEdgeCases:
    """测试边界情况"""
    
    @pytest.mark.parametrize("hook_cls", [
        ZlibCompressHook, XorObfuscateHook, ZlibXorHook
    ])
    def test_empty_data(self, hook_cls):
        """空数据应正常处理"""
        hook = hook_cls()
        
        encrypted = hook.encrypt(b'')
        decrypted = hook.decrypt(encrypted)
        
        assert decrypted == b''
    
    @pytest.mark.parametrize("hook_cls", [
        ZlibCompressHook, XorObfuscateHook, ZlibXorHook
    ])
    def test_single_byte(self, hook_cls):
        """单字节数据应正常处理"""
        hook = hook_cls()
        data = b'X'
        
        encrypted = hook.encrypt(data)
        decrypted = hook.decrypt(encrypted)
        
        assert decrypted == data
    
    @pytest.mark.parametrize("hook_cls", [
        ZlibCompressHook, XorObfuscateHook, ZlibXorHook
    ])
    def test_binary_data(self, hook_cls):
        """二进制数据应正常处理"""
        hook = hook_cls()
        data = bytes(range(256))
        
        encrypted = hook.encrypt(data)
        decrypted = hook.decrypt(encrypted)
        
        assert decrypted == data
    
    @pytest.mark.parametrize("hook_cls", [
        ZlibCompressHook, XorObfuscateHook, ZlibXorHook
    ])
    def test_large_data(self, hook_cls):
        """大数据应正常处理"""
        hook = hook_cls()
        data = b'Large data block ' * 10000
        
        encrypted = hook.encrypt(data)
        decrypted = hook.decrypt(encrypted)
        
        assert decrypted == data


class TestIndexCryptoDeterminism:
    """测试加密结果的确定性"""
    
    @pytest.mark.parametrize("hook_cls", [
        ZlibCompressHook, XorObfuscateHook, ZlibXorHook
    ])
    def test_same_data_same_result(self, hook_cls):
        """相同数据和配置应产生相同结果"""
        hook = hook_cls()
        data = b"Deterministic test data " * 10
        
        result1 = hook.encrypt(data)
        result2 = hook.encrypt(data)
        
        assert result1 == result2
