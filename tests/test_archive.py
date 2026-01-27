#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Archive 模块测试

测试 ArchiveBuilder 和 ArchiveReader 的功能。
"""

import io
import os
import zlib

import pytest

from grimoire import ArchiveBuilder, ArchiveReader, MD5Hook
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
from grimoire.hooks.base import CompressionHook
from grimoire.exceptions import CorruptedDataError, UnknownAlgorithmError


# ==================== 测试用压缩 Hook ====================

class ZlibHook(CompressionHook):
    """Zlib 压缩 Hook (测试用)"""
    
    @property
    def algo_id(self) -> int:
        return 1
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data, level=6)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)


class LZ4MockHook(CompressionHook):
    """模拟 LZ4 压缩 Hook (实际使用 zlib，仅测试多算法)"""
    
    @property
    def algo_id(self) -> int:
        return 2
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data, level=1)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)


# ==================== ArchiveBuilder 测试 ====================

class TestArchiveBuilderBasic:
    """ArchiveBuilder 基础功能测试"""
    
    def test_create_empty_archive(self, tmp_path):
        """创建空 Archive"""
        archive_path = tmp_path / "empty.archive"
        
        builder = ArchiveBuilder(str(archive_path))
        builder.build()
        
        assert archive_path.exists()
        assert archive_path.stat().st_size > 0
    
    def test_add_single_file_no_compression(self, tmp_path, sample_files):
        """添加单个文件 (无压缩)"""
        src_dir, files = sample_files
        archive_path = tmp_path / "single.archive"
        
        builder = ArchiveBuilder(str(archive_path))
        builder.add_file(str(src_dir / "hero.txt"), "/assets/hero.txt", algo_id=0)
        builder.build()
        
        assert builder.entry_count == 1
    
    def test_add_single_file_with_compression(self, tmp_path, large_files):
        """添加单个文件 (带压缩)"""
        src_dir, files = large_files
        archive_path = tmp_path / "compressed.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()]
        )
        builder.add_file(str(src_dir / "repeated.txt"), "/data/repeated.txt", algo_id=1)
        builder.build()
        
        # 压缩后大小应显著减小
        stats = builder.compression_stats
        assert stats["total_raw"] > stats["total_packed"]
    
    def test_add_directory(self, tmp_path, sample_files):
        """添加整个目录"""
        src_dir, files = sample_files
        archive_path = tmp_path / "dir.archive"
        
        builder = ArchiveBuilder(str(archive_path))
        count = builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        assert count == len(files)
        assert builder.entry_count == len(files)


class TestArchiveBuilderCompression:
    """ArchiveBuilder 压缩测试"""
    
    @pytest.fixture
    def compression_hooks(self):
        return [ZlibHook(), LZ4MockHook()]
    
    def test_multiple_compression_hooks(self, tmp_path, large_files, compression_hooks):
        """注册多个压缩 Hook"""
        src_dir, files = large_files
        archive_path = tmp_path / "multi_algo.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=compression_hooks
        )
        
        # 使用不同算法添加文件
        builder.add_file(str(src_dir / "repeated.txt"), "/zlib/file.txt", algo_id=1)
        builder.add_file(str(src_dir / "binary.dat"), "/lz4/file.dat", algo_id=2)
        builder.build()
        
        assert builder.entry_count == 2
    
    def test_compression_stats(self, tmp_path, large_files):
        """压缩统计信息"""
        src_dir, files = large_files
        archive_path = tmp_path / "stats.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()]
        )
        builder.add_dir(str(src_dir), "/data", algo_id=1)
        builder.build()
        
        stats = builder.compression_stats
        assert "total_raw" in stats
        assert "total_packed" in stats
        assert "ratio" in stats


class TestArchiveBuilderChecksum:
    """ArchiveBuilder 校验测试"""
    
    @pytest.mark.parametrize("checksum_hook", [
        None, NoneChecksumHook(), CRC32Hook(), MD5Hook(), SHA256Hook()
    ])
    def test_different_checksum_hooks(self, checksum_hook, tmp_path, sample_files):
        """测试不同校验算法"""
        src_dir, files = sample_files
        archive_path = tmp_path / "checksum.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            checksum_hook=checksum_hook
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 使用相同 Hook 读取验证
        with ArchiveReader(str(archive_path), checksum_hook=checksum_hook) as reader:
            for name in files:
                vfs_path = f"/assets/{name}"
                data = reader.read(vfs_path, verify=True)
                assert data == files[name]


class TestArchiveBuilderBatch:
    """ArchiveBuilder 批量操作测试"""
    
    def test_add_files_batch(self, tmp_path, sample_files):
        """批量添加文件"""
        from grimoire.core.batch import FileItem
        
        src_dir, files = sample_files
        archive_path = tmp_path / "batch.archive"
        
        items = [
            FileItem(str(src_dir / name), f"/batch/{name}", algo_id=0)
            for name in files.keys()
        ]
        
        builder = ArchiveBuilder(str(archive_path))
        result = builder.add_files_batch(items)
        builder.build()
        
        assert result.success_count == len(files)
        assert result.failed_count == 0
    
    def test_add_files_batch_skip_missing(self, tmp_path, sample_files):
        """批量添加时跳过不存在的文件"""
        from grimoire.core.batch import FileItem
        
        src_dir, files = sample_files
        archive_path = tmp_path / "skip.archive"
        
        items = [
            FileItem(str(src_dir / "hero.txt"), "/exists.txt"),
            FileItem(str(src_dir / "NOT_EXISTS.txt"), "/missing.txt"),  # 不存在
        ]
        
        builder = ArchiveBuilder(str(archive_path))
        result = builder.add_files_batch(items, on_error='skip')
        builder.build()
        
        assert result.success_count == 1
        assert result.failed_count == 1
    
    def test_add_dir_batch_with_progress(self, tmp_path, sample_files):
        """带进度回调的批量添加"""
        src_dir, files = sample_files
        archive_path = tmp_path / "progress.archive"
        
        progress_calls = []
        
        def on_progress(info):
            progress_calls.append({
                'current': info.current,
                'total': info.total,
            })
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()]
        )
        result = builder.add_dir_batch(
            str(src_dir), "/assets",
            algo_id=1,
            progress_callback=on_progress
        )
        builder.build()
        
        assert result.success_count == len(files)
        assert len(progress_calls) >= 1


# ==================== ArchiveReader 测试 ====================

class TestArchiveReaderBasic:
    """ArchiveReader 基础功能测试"""
    
    def test_read_archive(self, archive_file):
        """读取 Archive"""
        archive_path, src_dir, files = archive_file
        
        with ArchiveReader(str(archive_path), compression_hooks=[ZlibHook()]) as reader:
            assert reader.entry_count == len(files)
    
    def test_exists(self, archive_file):
        """检查路径存在性"""
        archive_path, src_dir, files = archive_file
        
        with ArchiveReader(str(archive_path), compression_hooks=[ZlibHook()]) as reader:
            assert reader.exists("/assets/hero.txt") is True
            assert reader.exists("/not/exist.txt") is False
    
    def test_read_content(self, archive_file):
        """读取文件内容"""
        archive_path, src_dir, files = archive_file
        
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        ) as reader:
            for name, expected in files.items():
                vfs_path = f"/assets/{name}"
                data = reader.read(vfs_path)
                assert data == expected


class TestArchiveReaderModes:
    """ArchiveReader 读取模式测试"""
    
    def test_mmap_mode(self, archive_file):
        """mmap 模式"""
        archive_path, src_dir, files = archive_file
        
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            use_mmap=True
        ) as reader:
            assert reader.is_mmap is True
            
            data = reader.read("/assets/hero.txt")
            assert data == files["hero.txt"]
    
    def test_traditional_mode(self, archive_file):
        """传统文件模式"""
        archive_path, src_dir, files = archive_file
        
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            use_mmap=False
        ) as reader:
            assert reader.is_mmap is False
            
            data = reader.read("/assets/hero.txt")
            assert data == files["hero.txt"]


class TestArchiveReaderOpen:
    """ArchiveReader.open 测试"""
    
    def test_open_returns_bytesio(self, archive_file):
        """open 应返回 BytesIO"""
        archive_path, src_dir, files = archive_file
        
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()]
        ) as reader:
            file_obj = reader.open("/assets/hero.txt")
            
            assert isinstance(file_obj, io.BytesIO)
            assert file_obj.read() == files["hero.txt"]
    
    def test_open_seekable(self, archive_file):
        """open 返回的对象应支持 seek"""
        archive_path, src_dir, files = archive_file
        
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()]
        ) as reader:
            file_obj = reader.open("/assets/hero.txt")
            
            # 读取部分
            first = file_obj.read(5)
            
            # seek 回起始
            file_obj.seek(0)
            
            # 重新读取应相同
            assert file_obj.read(5) == first


class TestArchiveReaderVerify:
    """ArchiveReader 校验测试"""
    
    def test_verify_success(self, tmp_path, sample_files):
        """校验正确的数据"""
        src_dir, files = sample_files
        archive_path = tmp_path / "verify.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            checksum_hook=MD5Hook()
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        with ArchiveReader(str(archive_path), checksum_hook=MD5Hook()) as reader:
            for name in files:
                data = reader.read(f"/assets/{name}", verify=True)
                assert data == files[name]
    
    def test_verify_corrupted(self, tmp_path, sample_files):
        """校验损坏的数据应抛出异常"""
        src_dir, files = sample_files
        archive_path = tmp_path / "corrupt.archive"
        
        builder = ArchiveBuilder(
            str(archive_path),
            checksum_hook=MD5Hook()
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        archive_size = archive_path.stat().st_size
        
        # 篡改数据区 (文件中间位置)
        corrupt_pos = archive_size // 2
        with open(archive_path, "r+b") as f:
            f.seek(corrupt_pos)
            f.write(b"CORRUPTED!DATA!")
        
        with ArchiveReader(str(archive_path), checksum_hook=MD5Hook()) as reader:
            # 尝试读取所有文件，至少有一个应该校验失败
            corruption_detected = False
            for name in files:
                try:
                    reader.read(f"/assets/{name}", verify=True)
                except CorruptedDataError:
                    corruption_detected = True
                    break
                except Exception:
                    # 其他异常也视为检测到损坏
                    corruption_detected = True
                    break
            
            assert corruption_detected, "应检测到数据损坏"


class TestArchiveReaderBatch:
    """ArchiveReader 批量读取测试"""
    
    def test_read_batch(self, archive_file):
        """批量读取多个文件"""
        archive_path, src_dir, files = archive_file
        
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()]
        ) as reader:
            paths = [f"/assets/{name}" for name in list(files.keys())[:2]]
            result = reader.read_batch(paths)
            
            assert len(result) == 2
            for path in paths:
                assert path in result


class TestArchiveNoCompression:
    """无压缩模式测试"""
    
    def test_no_compression(self, tmp_path, sample_files):
        """无压缩模式"""
        src_dir, files = sample_files
        archive_path = tmp_path / "nocomp.archive"
        
        builder = ArchiveBuilder(str(archive_path))
        builder.add_dir(str(src_dir), "/assets", algo_id=0)
        builder.build()
        
        with ArchiveReader(str(archive_path)) as reader:
            entry = reader.get_entry("/assets/hero.txt")
            
            # 无压缩时 packed_size == raw_size
            assert entry.packed_size == entry.raw_size
            
            data = reader.read("/assets/hero.txt")
            assert data == files["hero.txt"]


class TestArchiveIndexCrypto:
    """Archive 索引加密测试"""
    
    @pytest.mark.parametrize("crypto_cls", [
        ZlibCompressHook, XorObfuscateHook, ZlibXorHook
    ])
    def test_index_crypto(self, crypto_cls, tmp_path, sample_files):
        """测试不同索引加密方式"""
        src_dir, files = sample_files
        archive_path = tmp_path / "crypto.archive"
        crypto = crypto_cls()
        
        builder = ArchiveBuilder(
            str(archive_path),
            index_crypto=crypto
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        with ArchiveReader(str(archive_path), index_crypto=crypto) as reader:
            assert reader.is_decrypted is True
            assert reader.entry_count == len(files)


class TestArchiveCombinations:
    """Archive 功能组合测试"""
    
    @pytest.mark.parametrize("use_compression", [True, False])
    @pytest.mark.parametrize("use_checksum", [True, False])
    @pytest.mark.parametrize("use_crypto", [True, False])
    def test_all_combinations(
        self, use_compression, use_checksum, use_crypto,
        tmp_path, sample_files
    ):
        """测试所有功能组合"""
        src_dir, files = sample_files
        archive_path = tmp_path / "combo.archive"
        
        compression_hooks = [ZlibHook()] if use_compression else None
        checksum_hook = MD5Hook() if use_checksum else None
        index_crypto = ZlibCompressHook() if use_crypto else None
        
        # 构建
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=compression_hooks,
            checksum_hook=checksum_hook,
            index_crypto=index_crypto
        )
        algo_id = 1 if use_compression else 0
        builder.add_dir(str(src_dir), "/assets", algo_id=algo_id)
        builder.build()
        
        # 读取
        with ArchiveReader(
            str(archive_path),
            compression_hooks=compression_hooks,
            checksum_hook=checksum_hook,
            index_crypto=index_crypto
        ) as reader:
            assert reader.entry_count == len(files)
            
            for name, expected in files.items():
                data = reader.read(f"/assets/{name}", verify=use_checksum)
                assert data == expected
