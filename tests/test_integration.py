#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
集成测试

使用项目 src 目录作为真实测试数据进行端到端测试。
"""

import json
import os
import zlib

import pytest

from grimoire import (
    ManifestBuilder, ManifestReader,
    ArchiveBuilder, ArchiveReader,
    ManifestJsonConverter, ModeConverter,
    MD5Hook,
)
from grimoire.hooks.checksum import SHA256Hook
from grimoire.hooks.crypto import ZlibCompressHook
from grimoire.hooks.base import CompressionHook


class ZlibHook(CompressionHook):
    @property
    def algo_id(self) -> int:
        return 1
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data, level=6)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)


# ==================== 真实目录打包测试 ====================

@pytest.mark.slow
class TestPackSrcDirectory:
    """使用 src 目录进行打包测试"""
    
    def test_pack_src_to_manifest(self, src_directory, tmp_path):
        """将 src 目录打包为 Manifest"""
        manifest_path = tmp_path / "src.manifest"
        
        builder = ManifestBuilder(
            str(manifest_path),
            checksum_hook=MD5Hook()
        )
        count = builder.add_dir(str(src_directory), "/grimoire")
        builder.build()
        
        # 验证
        assert count > 0
        assert manifest_path.exists()
        
        with ManifestReader(str(manifest_path), checksum_hook=MD5Hook()) as reader:
            assert reader.entry_count == count
            paths = reader.list_all()
            
            # 应包含 __init__.py
            assert any("__init__.py" in p for p in paths)
            # 应包含 hooks 模块
            assert any("hooks" in p for p in paths)
    
    def test_pack_src_to_archive(self, src_directory, tmp_path):
        """将 src 目录打包为 Archive"""
        archive_path = tmp_path / "src.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        count = builder.add_dir(str(src_directory), "/grimoire", algo_id=1)
        builder.build()
        
        # 验证
        assert count > 0
        assert archive_path.exists()
        
        # 压缩效果验证
        stats = builder.compression_stats
        assert stats["total_raw"] > stats["total_packed"]
        
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        ) as reader:
            assert reader.entry_count == count
    
    def test_pack_and_verify_content(self, src_directory, tmp_path):
        """打包并验证内容一致性"""
        archive_path = tmp_path / "verify.archive"
        
        # 找一个 Python 文件做验证
        init_py = src_directory / "grimoire" / "__init__.py"
        if not init_py.exists():
            pytest.skip("__init__.py not found")
        
        original_content = init_py.read_bytes()
        
        builder = ArchiveBuilder(str(archive_path), checksum_hook=MD5Hook())
        builder.add_file(str(init_py), "/grimoire/__init__.py")
        builder.build()
        
        with ArchiveReader(str(archive_path), checksum_hook=MD5Hook()) as reader:
            packed_content = reader.read("/grimoire/__init__.py", verify=True)
            assert packed_content == original_content


# ==================== 完整转换链测试 ====================

@pytest.mark.slow
class TestFullConversionChain:
    """完整转换链测试"""
    
    def test_archive_manifest_json_chain(self, src_directory, tmp_path):
        """Archive → Manifest → JSON 链路"""
        archive_path = tmp_path / "step1.archive"
        manifest_path = tmp_path / "step2.manifest"
        json_path = tmp_path / "step3.json"
        
        # Step 1: src → Archive
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook(),
            index_crypto=ZlibCompressHook()
        )
        builder.add_dir(str(src_directory), "/code", algo_id=1)
        builder.build()
        
        entry_count = builder.entry_count
        
        # Step 2: Archive → Manifest
        ModeConverter.archive_to_manifest(
            str(archive_path),
            str(manifest_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook(),
            index_crypto_read=ZlibCompressHook()
        )
        
        # Step 3: Manifest → JSON
        ManifestJsonConverter.manifest_to_json(str(manifest_path), str(json_path))
        
        # 验证最终 JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["entry_count"] == entry_count
        assert data["checksum_algo"] == 2  # MD5
        assert len(data["entries"]) == entry_count
    
    def test_json_manifest_archive_chain(self, src_directory, tmp_path):
        """JSON → Manifest → Archive 链路"""
        # 首先创建一个 JSON
        json_path = tmp_path / "input.json"
        manifest_path = tmp_path / "step1.manifest"
        archive_path = tmp_path / "step2.archive"
        
        # 扫描 src 目录创建 JSON
        entries = []
        for root, dirs, files in os.walk(src_directory):
            for file in files:
                if file.endswith('.py'):
                    rel_path = os.path.relpath(os.path.join(root, file), src_directory)
                    entries.append({"path": f"/code/{rel_path.replace(os.sep, '/')}"})
        
        if not entries:
            pytest.skip("No Python files found")
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 2,
                "entries": entries
            }, f)
        
        # JSON → Manifest
        ManifestJsonConverter.json_to_manifest(
            str(json_path),
            str(manifest_path),
            local_base_path=str(tmp_path),
            path_mappings={"/code": str(src_directory)}
        )
        
        # Manifest → Archive
        ModeConverter.manifest_to_archive(
            str(manifest_path),
            str(archive_path),
            local_base_path=str(tmp_path),
            path_mappings={"/code": str(src_directory)},
            checksum_hook_read=MD5Hook(),
            compression_hooks=[ZlibHook()],
            default_algo_id=1,
            output_checksum_hook=MD5Hook()
        )
        
        # 验证 Archive
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        ) as reader:
            assert reader.entry_count == len(entries)


# ==================== 批量操作集成测试 ====================

@pytest.mark.slow
class TestBatchIntegration:
    """批量操作集成测试"""
    
    def test_batch_add_with_progress(self, src_directory, tmp_path):
        """带进度回调的批量添加"""
        archive_path = tmp_path / "batch.archive"
        
        progress_values = []
        
        def on_progress(info):
            progress_values.append(info.progress)
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()]
        )
        result = builder.add_dir_batch(
            str(src_directory),
            mount_point="/code",
            algo_id=1,
            progress_callback=on_progress
        )
        builder.build()
        
        assert result.success_count > 0
        assert result.failed_count == 0
        assert len(progress_values) >= 1
    
    def test_extract_all_to_directory(self, src_directory, tmp_path):
        """解包到目录"""
        archive_path = tmp_path / "extract.archive"
        output_dir = tmp_path / "extracted"
        
        # 打包
        builder = ArchiveBuilder(str(archive_path), checksum_hook=MD5Hook())
        builder.add_dir(str(src_directory), "/code")
        builder.build()
        
        original_count = builder.entry_count
        
        # 解包
        with ArchiveReader(str(archive_path), checksum_hook=MD5Hook()) as reader:
            result = reader.extract_all(str(output_dir))
        
        assert result.success_count == original_count
        
        # 验证解包目录存在
        assert output_dir.exists()
        assert (output_dir / "code").exists()


# ==================== 加密索引集成测试 ====================

@pytest.mark.slow
class TestEncryptedIndexIntegration:
    """加密索引集成测试"""
    
    def test_encrypted_without_key(self, src_directory, tmp_path):
        """不提供密钥时仍可读取 Hash 列表"""
        from grimoire.exceptions import IndexNotDecryptedError
        
        manifest_path = tmp_path / "encrypted.manifest"
        
        builder = ManifestBuilder(
            str(manifest_path),
            checksum_hook=MD5Hook(),
            index_crypto=ZlibCompressHook()
        )
        builder.add_dir(str(src_directory), "/code")
        builder.build()
        
        entry_count = builder.entry_count
        
        # 不提供 index_crypto
        with ManifestReader(str(manifest_path), checksum_hook=MD5Hook()) as reader:
            assert reader.is_decrypted is False
            
            # 可获取 Hash 列表
            hashes = reader.list_hashes()
            assert len(hashes) == entry_count
            
            # 无法获取路径列表
            with pytest.raises(IndexNotDecryptedError):
                reader.list_all()
    
    def test_encrypted_with_key(self, src_directory, tmp_path):
        """提供密钥时可正常读取"""
        manifest_path = tmp_path / "encrypted.manifest"
        
        builder = ManifestBuilder(
            str(manifest_path),
            checksum_hook=MD5Hook(),
            index_crypto=ZlibCompressHook()
        )
        builder.add_dir(str(src_directory), "/code")
        builder.build()
        
        entry_count = builder.entry_count
        
        # 提供 index_crypto
        with ManifestReader(
            str(manifest_path),
            checksum_hook=MD5Hook(),
            index_crypto=ZlibCompressHook()
        ) as reader:
            assert reader.is_decrypted is True
            
            paths = reader.list_all()
            assert len(paths) == entry_count


# ==================== 大文件测试 ====================

@pytest.mark.slow
class TestLargeFileHandling:
    """大文件处理测试"""
    
    def test_large_file_compression(self, tmp_path):
        """大文件压缩"""
        # 创建 5MB 的可压缩文件
        large_file = tmp_path / "large.txt"
        content = b"Compressible content pattern! " * 170000  # ~5MB
        large_file.write_bytes(content)
        
        archive_path = tmp_path / "large.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=SHA256Hook()
        )
        builder.add_file(str(large_file), "/large.txt", algo_id=1)
        builder.build()
        
        # 验证压缩效果
        stats = builder.compression_stats
        compression_ratio = stats["total_packed"] / stats["total_raw"]
        assert compression_ratio < 0.1  # 压缩率应低于 10%
        
        # 验证读取
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=SHA256Hook()
        ) as reader:
            read_content = reader.read("/large.txt", verify=True)
            assert read_content == content
