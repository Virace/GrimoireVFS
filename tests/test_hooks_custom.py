#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自定义 Hook 单元测试

测试用户自定义 Hook 的功能和集成。
"""

import pytest
import zlib

from grimoire.hooks.base import (
    ChecksumHook,
    IndexCryptoHook,
    CompressionHook,
    PathHashHook,
)


class TestCustomChecksumHook:
    """测试自定义 ChecksumHook"""
    
    def test_custom_hook_properties(self, custom_checksum_hook):
        """自定义 Hook 应具有正确的属性"""
        assert custom_checksum_hook.algo_id == 99
        assert custom_checksum_hook.digest_size == 8
        assert custom_checksum_hook.display_name == "simple_hash"
    
    def test_custom_hook_compute(self, custom_checksum_hook):
        """自定义 Hook 的 compute 方法应正常工作"""
        data = b"Test data"
        result = custom_checksum_hook.compute(data)
        
        assert len(result) == custom_checksum_hook.digest_size
        assert isinstance(result, bytes)
    
    def test_custom_hook_verify(self, custom_checksum_hook):
        """自定义 Hook 的 verify 方法应正常工作"""
        data = b"Test data"
        checksum = custom_checksum_hook.compute(data)
        
        assert custom_checksum_hook.verify(data, checksum) is True
        assert custom_checksum_hook.verify(data, b'\x00' * 8) is False
    
    def test_custom_hook_determinism(self, custom_checksum_hook):
        """自定义 Hook 应产生确定性结果"""
        data = b"Deterministic"
        
        result1 = custom_checksum_hook.compute(data)
        result2 = custom_checksum_hook.compute(data)
        
        assert result1 == result2


class TestCustomIndexCryptoHook:
    """测试自定义 IndexCryptoHook"""
    
    def test_custom_hook_properties(self, custom_crypto_hook):
        """自定义 Hook 应具有正确的属性"""
        assert custom_crypto_hook.flags_id == 0x10
        assert custom_crypto_hook.display_name == "reverse"
    
    def test_custom_hook_roundtrip(self, custom_crypto_hook):
        """自定义 Hook 的加密解密往返应一致"""
        data = b"Test data to reverse"
        
        encrypted = custom_crypto_hook.encrypt(data)
        decrypted = custom_crypto_hook.decrypt(encrypted)
        
        assert decrypted == data
    
    def test_custom_hook_changes_data(self, custom_crypto_hook):
        """自定义 Hook 应改变数据"""
        data = b"ABCD"
        encrypted = custom_crypto_hook.encrypt(data)
        
        assert encrypted == b"DCBA"  # 反转


class TestCustomCompressionHook:
    """测试自定义 CompressionHook"""
    
    @pytest.fixture
    def custom_compression_hook(self):
        """创建自定义压缩 Hook"""
        class LZ77Hook(CompressionHook):
            @property
            def algo_id(self) -> int:
                return 50
            
            def compress(self, data: bytes) -> bytes:
                return zlib.compress(data)
            
            def decompress(self, data: bytes, raw_size: int) -> bytes:
                return zlib.decompress(data)
        
        return LZ77Hook()
    
    def test_custom_compression_properties(self, custom_compression_hook):
        """自定义压缩 Hook 应具有正确的属性"""
        assert custom_compression_hook.algo_id == 50
    
    def test_custom_compression_roundtrip(self, custom_compression_hook):
        """自定义压缩 Hook 的压缩解压往返应一致"""
        data = b"Compressible pattern " * 100
        
        compressed = custom_compression_hook.compress(data)
        decompressed = custom_compression_hook.decompress(compressed, len(data))
        
        assert decompressed == data


class TestCustomPathHashHook:
    """测试自定义 PathHashHook"""
    
    @pytest.fixture
    def custom_path_hash_hook(self):
        """创建自定义路径 Hash Hook"""
        class SimplePathHash(PathHashHook):
            def hash(self, path: str) -> int:
                """简单的字符串长度+字符和哈希"""
                result = len(path)
                for c in path:
                    result = (result * 31 + ord(c)) & 0xFFFFFFFFFFFFFFFF
                return result
        
        return SimplePathHash()
    
    def test_custom_path_hash(self, custom_path_hash_hook):
        """自定义路径 Hash Hook 应正常工作"""
        result = custom_path_hash_hook.hash("/game/assets/hero.txt")
        
        assert isinstance(result, int)
        assert 0 <= result < 2**64
    
    def test_custom_path_hash_determinism(self, custom_path_hash_hook):
        """自定义路径 Hash 应产生确定性结果"""
        path = "/game/assets/hero.txt"
        
        result1 = custom_path_hash_hook.hash(path)
        result2 = custom_path_hash_hook.hash(path)
        
        assert result1 == result2
    
    def test_custom_path_hash_different_paths(self, custom_path_hash_hook):
        """不同路径应产生不同 Hash"""
        result1 = custom_path_hash_hook.hash("/path/a")
        result2 = custom_path_hash_hook.hash("/path/b")
        
        assert result1 != result2


class TestCustomHookInManifest:
    """测试自定义 Hook 在 Manifest 中的集成"""
    
    def test_manifest_with_custom_checksum(self, tmp_path, sample_files, custom_checksum_hook):
        """Manifest 应支持自定义 ChecksumHook"""
        from grimoire import ManifestBuilder, ManifestReader
        
        src_dir, files = sample_files
        manifest_path = tmp_path / "custom.manifest"
        
        # 使用自定义 Hook 构建
        builder = ManifestBuilder(
            str(manifest_path),
            checksum_hook=custom_checksum_hook
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 使用相同 Hook 读取
        with ManifestReader(str(manifest_path), checksum_hook=custom_checksum_hook) as reader:
            assert reader.entry_count == len(files)
            
            for name in files:
                vfs_path = f"/assets/{name}"
                assert reader.exists(vfs_path)
    
    def test_manifest_with_custom_crypto(self, tmp_path, sample_files, custom_crypto_hook):
        """Manifest 应支持自定义 IndexCryptoHook"""
        from grimoire import ManifestBuilder, ManifestReader
        
        src_dir, files = sample_files
        manifest_path = tmp_path / "custom_crypto.manifest"
        
        # 使用自定义 Hook 构建
        builder = ManifestBuilder(
            str(manifest_path),
            index_crypto=custom_crypto_hook
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 使用相同 Hook 读取
        with ManifestReader(str(manifest_path), index_crypto=custom_crypto_hook) as reader:
            assert reader.is_decrypted is True
            assert reader.entry_count == len(files)


class TestCustomHookInArchive:
    """测试自定义 Hook 在 Archive 中的集成"""
    
    @pytest.fixture
    def custom_compression_hook(self):
        """创建自定义压缩 Hook"""
        class TestZlib(CompressionHook):
            @property
            def algo_id(self) -> int:
                return 77
            
            def compress(self, data: bytes) -> bytes:
                return zlib.compress(data, level=9)
            
            def decompress(self, data: bytes, raw_size: int) -> bytes:
                return zlib.decompress(data)
        
        return TestZlib()
    
    def test_archive_with_custom_compression(self, tmp_path, sample_files, custom_compression_hook):
        """Archive 应支持自定义 CompressionHook"""
        from grimoire import ArchiveBuilder, ArchiveReader
        
        src_dir, files = sample_files
        archive_path = tmp_path / "custom.archive"
        
        # 使用自定义 Hook 构建
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[custom_compression_hook]
        )
        builder.add_dir(str(src_dir), "/assets", algo_id=77)
        builder.build()
        
        # 使用相同 Hook 读取
        with ArchiveReader(str(archive_path), compression_hooks=[custom_compression_hook]) as reader:
            assert reader.entry_count == len(files)
            
            for name, expected_content in files.items():
                vfs_path = f"/assets/{name}"
                data = reader.read(vfs_path)
                assert data == expected_content
    
    def test_archive_with_custom_checksum_and_compression(
        self, tmp_path, sample_files, custom_checksum_hook, custom_compression_hook
    ):
        """Archive 应支持同时使用自定义 Checksum 和 Compression Hook"""
        from grimoire import ArchiveBuilder, ArchiveReader
        
        src_dir, files = sample_files
        archive_path = tmp_path / "full_custom.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[custom_compression_hook],
            checksum_hook=custom_checksum_hook
        )
        builder.add_dir(str(src_dir), "/assets", algo_id=77)
        builder.build()
        
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[custom_compression_hook],
            checksum_hook=custom_checksum_hook
        ) as reader:
            for name, expected_content in files.items():
                vfs_path = f"/assets/{name}"
                data = reader.read(vfs_path, verify=True)
                assert data == expected_content
