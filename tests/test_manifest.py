#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Manifest 模块测试

测试 ManifestBuilder 和 ManifestReader 的功能。
"""

import os

import pytest

from grimoire import ManifestBuilder, ManifestReader, MD5Hook
from grimoire.hooks.checksum import (
    NoneChecksumHook,
    CRC32Hook,
    SHA1Hook,
    SHA256Hook,
)
from grimoire.hooks.crypto import (
    ZlibCompressHook,
    XorObfuscateHook,
    ZlibXorHook,
)
from grimoire.hooks.base import IndexCryptoHook
from grimoire.exceptions import IndexNotDecryptedError


# ==================== ManifestBuilder 测试 ====================

class TestManifestBuilderBasic:
    """ManifestBuilder 基础功能测试"""
    
    def test_create_empty_manifest(self, tmp_path):
        """创建空 Manifest"""
        manifest_path = tmp_path / "empty.manifest"
        
        builder = ManifestBuilder(str(manifest_path))
        builder.build()
        
        assert manifest_path.exists()
        assert manifest_path.stat().st_size > 0
    
    def test_add_single_file(self, tmp_path, sample_files):
        """添加单个文件"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "single.manifest"
        
        builder = ManifestBuilder(str(manifest_path))
        builder.add_file(str(src_dir / "hero.txt"), "/assets/hero.txt")
        builder.build()
        
        assert builder.entry_count == 1
    
    def test_add_directory(self, tmp_path, sample_files):
        """添加整个目录"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "dir.manifest"
        
        builder = ManifestBuilder(str(manifest_path))
        count = builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        assert count == len(files)
        assert builder.entry_count == len(files)
    
    def test_add_directory_non_recursive(self, tmp_path, sample_files):
        """非递归添加目录"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "nonrecursive.manifest"
        
        builder = ManifestBuilder(str(manifest_path))
        count = builder.add_dir(str(src_dir), "/assets", recursive=False)
        builder.build()
        
        # 只有根目录的文件
        root_files = [f for f in files.keys() if "/" not in f]
        assert count == len(root_files)
    
    def test_path_stats(self, tmp_path, sample_files):
        """路径字典统计"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "stats.manifest"
        
        builder = ManifestBuilder(str(manifest_path))
        builder.add_dir(str(src_dir), "/assets")
        
        stats = builder.path_stats
        assert "dirs" in stats
        assert "names" in stats
        assert "exts" in stats


class TestManifestBuilderChecksum:
    """ManifestBuilder 校验算法测试"""
    
    @pytest.mark.parametrize("hook,expected_size", [
        (None, 0),
        (NoneChecksumHook(), 0),
        (CRC32Hook(), 4),
        (MD5Hook(), 16),
        (SHA1Hook(), 20),
        (SHA256Hook(), 32),
    ])
    def test_different_checksum_hooks(self, hook, expected_size, tmp_path, sample_files):
        """测试不同校验算法"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "checksum.manifest"
        
        builder = ManifestBuilder(str(manifest_path), checksum_hook=hook)
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 读取并验证
        with ManifestReader(str(manifest_path), checksum_hook=hook) as reader:
            entry = reader.get_entry("/assets/hero.txt")
            assert len(entry.checksum) == expected_size


class TestManifestBuilderIndexCrypto:
    """ManifestBuilder 索引加密测试"""
    
    @pytest.mark.parametrize("crypto_cls", [
        ZlibCompressHook,
        XorObfuscateHook,
        ZlibXorHook,
    ])
    def test_different_index_crypto(self, crypto_cls, tmp_path, sample_files):
        """测试不同索引加密方式"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "crypto.manifest"
        crypto = crypto_cls()
        
        builder = ManifestBuilder(str(manifest_path), index_crypto=crypto)
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 使用相同加密 Hook 读取
        with ManifestReader(str(manifest_path), index_crypto=crypto) as reader:
            assert reader.is_decrypted is True
            assert reader.entry_count == len(files)


class TestManifestBuilderBatch:
    """ManifestBuilder 批量操作测试"""
    
    def test_add_files_batch(self, tmp_path, sample_files):
        """批量添加文件"""
        from grimoire.core.batch import FileItem
        
        src_dir, files = sample_files
        manifest_path = tmp_path / "batch.manifest"
        
        items = [
            FileItem(str(src_dir / name), f"/batch/{name}")
            for name in files.keys()
        ]
        
        builder = ManifestBuilder(str(manifest_path))
        result = builder.add_files_batch(items)
        builder.build()
        
        assert result.success_count == len(files)
        assert result.failed_count == 0
    
    def test_add_dir_batch_with_progress(self, tmp_path, sample_files):
        """带进度回调的批量添加"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "progress.manifest"
        
        progress_calls = []
        
        def on_progress(info):
            progress_calls.append(info.current)
        
        builder = ManifestBuilder(str(manifest_path))
        result = builder.add_dir_batch(
            str(src_dir), "/assets",
            progress_callback=on_progress
        )
        builder.build()
        
        assert result.success_count == len(files)
        # 进度回调应被调用
        assert len(progress_calls) >= 1


# ==================== ManifestReader 测试 ====================

class TestManifestReaderBasic:
    """ManifestReader 基础功能测试"""
    
    def test_read_manifest(self, manifest_file):
        """读取 Manifest"""
        manifest_path, src_dir, files = manifest_file
        
        with ManifestReader(str(manifest_path)) as reader:
            assert reader.entry_count == len(files)
    
    def test_exists(self, manifest_file):
        """检查路径存在性"""
        manifest_path, src_dir, files = manifest_file
        
        with ManifestReader(str(manifest_path)) as reader:
            assert reader.exists("/assets/hero.txt") is True
            assert reader.exists("/not/exist.txt") is False
    
    def test_get_entry(self, manifest_file):
        """获取条目信息"""
        manifest_path, src_dir, files = manifest_file
        
        with ManifestReader(str(manifest_path)) as reader:
            entry = reader.get_entry("/assets/hero.txt")
            
            assert entry is not None
            assert entry.raw_size == len(files["hero.txt"])
    
    def test_list_all(self, manifest_file):
        """列出所有路径"""
        manifest_path, src_dir, files = manifest_file
        
        with ManifestReader(str(manifest_path)) as reader:
            paths = reader.list_all()
            
            assert len(paths) == len(files)
            # 注意: normalize_path 会去除前导斜杠
            assert any("assets/hero.txt" in p for p in paths)


class TestManifestReaderVerify:
    """ManifestReader 文件校验测试"""
    
    def test_verify_file_success(self, tmp_path, sample_files):
        """校验正确的文件"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "verify.manifest"
        
        # 创建带校验的 Manifest
        builder = ManifestBuilder(str(manifest_path), checksum_hook=MD5Hook())
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        with ManifestReader(str(manifest_path), checksum_hook=MD5Hook()) as reader:
            result = reader.verify_file("/assets/hero.txt", str(src_dir / "hero.txt"))
            assert result is True
    
    def test_verify_file_modified(self, tmp_path, sample_files):
        """校验被修改的文件"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "verify_mod.manifest"
        
        builder = ManifestBuilder(str(manifest_path), checksum_hook=MD5Hook())
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 修改文件
        hero_path = src_dir / "hero.txt"
        hero_path.write_bytes(b"MODIFIED CONTENT")
        
        with ManifestReader(str(manifest_path), checksum_hook=MD5Hook()) as reader:
            result = reader.verify_file("/assets/hero.txt", str(hero_path))
            assert result is False


class TestManifestReaderEncrypted:
    """ManifestReader 加密索引测试"""
    
    @pytest.fixture
    def simple_xor_hook(self):
        """简单 XOR 加密 Hook"""
        class SimpleXor(IndexCryptoHook):
            def __init__(self, key: bytes = b"test_key"):
                self._key = key
            
            @property
            def flags_id(self) -> int:
                return 0x10
            
            def _xor(self, data: bytes) -> bytes:
                return bytes(b ^ self._key[i % len(self._key)] for i, b in enumerate(data))
            
            def encrypt(self, data: bytes) -> bytes:
                return self._xor(data)
            
            def decrypt(self, data: bytes) -> bytes:
                return self._xor(data)
        
        return SimpleXor()
    
    def test_encrypted_index_without_key(self, tmp_path, sample_files, simple_xor_hook):
        """不提供解密器时无法遍历"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "encrypted.manifest"
        
        builder = ManifestBuilder(str(manifest_path), index_crypto=simple_xor_hook)
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 不提供解密器
        with ManifestReader(str(manifest_path)) as reader:
            assert reader.is_decrypted is False
            
            # 可以获取 Hash 列表
            hashes = reader.list_hashes()
            assert len(hashes) == len(files)
            
            # 无法遍历路径
            with pytest.raises(IndexNotDecryptedError):
                reader.list_all()
    
    def test_encrypted_index_with_key(self, tmp_path, sample_files, simple_xor_hook):
        """提供解密器时可以遍历"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "encrypted2.manifest"
        
        builder = ManifestBuilder(str(manifest_path), index_crypto=simple_xor_hook)
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 提供解密器
        with ManifestReader(str(manifest_path), index_crypto=simple_xor_hook) as reader:
            assert reader.is_decrypted is True
            
            paths = reader.list_all()
            assert len(paths) == len(files)


class TestManifestChinesePath:
    """中文路径测试"""
    
    def test_chinese_filename(self, tmp_path, sample_files):
        """中文文件名"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "chinese.manifest"
        
        builder = ManifestBuilder(str(manifest_path), checksum_hook=MD5Hook())
        builder.add_dir(str(src_dir), "/资源")
        builder.build()
        
        with ManifestReader(str(manifest_path), checksum_hook=MD5Hook()) as reader:
            paths = reader.list_all()
            
            # 应包含中文文件
            assert any("中文文件.txt" in p for p in paths)
            assert reader.exists("/资源/中文文件.txt")


class TestManifestIterators:
    """迭代器测试"""
    
    def test_iter_entries(self, manifest_file, md5_hook):
        """迭代所有条目"""
        manifest_path, src_dir, files = manifest_file
        
        with ManifestReader(str(manifest_path), checksum_hook=md5_hook) as reader:
            entries = list(reader.iter_entries())
            
            assert len(entries) == len(files)
            for path, entry in entries:
                # 注意: normalize_path 会去除前导斜杠
                assert "assets/" in path or path.startswith("assets")
    
    def test_get_all_entries(self, manifest_file, md5_hook):
        """获取所有条目元信息"""
        manifest_path, src_dir, files = manifest_file
        
        with ManifestReader(str(manifest_path), checksum_hook=md5_hook) as reader:
            entries = reader.get_all_entries()
            
            assert len(entries) == len(files)
            for entry_info in entries:
                assert "path" in entry_info
                assert "size" in entry_info


class TestManifestCombinations:
    """Checksum + IndexCrypto 组合测试"""
    
    @pytest.mark.parametrize("checksum_hook", [
        None, MD5Hook(), SHA256Hook(), CRC32Hook()
    ])
    @pytest.mark.parametrize("index_crypto", [
        None, ZlibCompressHook(), XorObfuscateHook(), ZlibXorHook()
    ])
    def test_all_combinations(self, checksum_hook, index_crypto, tmp_path, sample_files):
        """测试所有 Checksum + Crypto 组合"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "combo.manifest"
        
        # 构建
        builder = ManifestBuilder(
            str(manifest_path),
            checksum_hook=checksum_hook,
            index_crypto=index_crypto
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 读取
        with ManifestReader(
            str(manifest_path),
            checksum_hook=checksum_hook,
            index_crypto=index_crypto
        ) as reader:
            assert reader.entry_count == len(files)
            
            for name in files:
                vfs_path = f"/assets/{name}"
                assert reader.exists(vfs_path)
