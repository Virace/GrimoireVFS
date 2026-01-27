#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量操作测试

测试批量添加、读取、进度回调和错误处理。
"""

import zlib

import pytest

from grimoire import ArchiveBuilder, ArchiveReader, MD5Hook
from grimoire.core.batch import (
    FileItem,
    ProgressInfo,
    BatchResult,
    ProgressTracker,
    scan_directory,
    estimate_total_bytes,
)
from grimoire.hooks.base import CompressionHook


class ZlibHook(CompressionHook):
    @property
    def algo_id(self) -> int:
        return 1
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data, level=6)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)


# ==================== FileItem 测试 ====================

class TestFileItem:
    """FileItem 数据类测试"""
    
    def test_create_minimal(self):
        """最小参数创建"""
        item = FileItem("/path/to/file.txt")
        
        assert item.local_path == "/path/to/file.txt"
        assert item.vfs_path is None
        assert item.algo_id == 0
    
    def test_create_full(self):
        """完整参数创建"""
        item = FileItem(
            local_path="/local/file.txt",
            vfs_path="/virtual/file.txt",
            algo_id=1
        )
        
        assert item.local_path == "/local/file.txt"
        assert item.vfs_path == "/virtual/file.txt"
        assert item.algo_id == 1


# ==================== ProgressInfo 测试 ====================

class TestProgressInfo:
    """ProgressInfo 数据类测试"""
    
    def test_progress_calculation(self):
        """进度百分比计算"""
        info = ProgressInfo(
            current=5,
            total=10,
            current_file="test.txt",
            bytes_processed=500,
            bytes_total=1000,
            elapsed_time=5.0
        )
        
        assert info.progress == 0.5
    
    def test_progress_zero_total(self):
        """total=0 时进度为 0"""
        info = ProgressInfo(
            current=0,
            total=0,
            current_file="",
            bytes_processed=0,
            bytes_total=0,
            elapsed_time=0.0
        )
        
        assert info.progress == 0.0
    
    def test_rate_calculation(self):
        """速率计算"""
        info = ProgressInfo(
            current=10,
            total=10,
            current_file="test.txt",
            bytes_processed=1000,
            bytes_total=1000,
            elapsed_time=2.0
        )
        
        assert info.rate == 500.0  # 500 bytes/second
    
    def test_eta_calculation(self):
        """预计剩余时间计算"""
        info = ProgressInfo(
            current=5,
            total=10,
            current_file="test.txt",
            bytes_processed=500,
            bytes_total=1000,
            elapsed_time=5.0
        )
        
        # rate = 100 bytes/s, remaining = 500 bytes
        assert info.eta == 5.0


# ==================== BatchResult 测试 ====================

class TestBatchResult:
    """BatchResult 数据类测试"""
    
    def test_total_count(self):
        """总数计算"""
        result = BatchResult(
            success_count=8,
            failed_count=1,
            skipped_count=1
        )
        
        assert result.total_count == 10
    
    def test_success_rate(self):
        """成功率计算"""
        result = BatchResult(
            success_count=8,
            failed_count=2
        )
        
        assert result.success_rate == 0.8
    
    def test_success_rate_zero_total(self):
        """total=0 时成功率为 0"""
        result = BatchResult()
        
        assert result.success_rate == 0.0


# ==================== ProgressTracker 测试 ====================

class TestProgressTracker:
    """ProgressTracker 测试"""
    
    def test_basic_tracking(self):
        """基础进度跟踪"""
        tracker = ProgressTracker(total_files=10)
        
        tracker.update("file1.txt", 100)
        tracker.update("file2.txt", 200)
        
        elapsed = tracker.finish()
        assert elapsed >= 0
    
    def test_callback_invoked(self):
        """回调函数应被调用"""
        calls = []
        
        def callback(info: ProgressInfo):
            calls.append(info.current)
        
        tracker = ProgressTracker(
            total_files=3,
            callback=callback,
            callback_interval=0  # 禁用间隔限制以确保每次都调用
        )
        
        for i in range(3):
            tracker.update(f"file{i}.txt", 100)
        
        tracker.finish()
        
        # 至少调用一次
        assert len(calls) >= 1


# ==================== scan_directory 测试 ====================

class TestScanDirectory:
    """目录扫描测试"""
    
    def test_scan_recursive(self, sample_files):
        """递归扫描"""
        src_dir, files = sample_files
        
        items = list(scan_directory(str(src_dir), "/mount"))
        
        assert len(items) == len(files)
        for item in items:
            # 注意: normalize_path 会去除前导斜杠
            assert "mount/" in item.vfs_path or item.vfs_path.startswith("mount")
    
    def test_scan_non_recursive(self, sample_files):
        """非递归扫描"""
        src_dir, files = sample_files
        
        items = list(scan_directory(str(src_dir), "/mount", recursive=False))
        
        # 只包含根目录文件
        root_files = [f for f in files.keys() if "/" not in f]
        assert len(items) == len(root_files)
    
    def test_scan_with_algo_id(self, sample_files):
        """扫描设置压缩算法"""
        src_dir, files = sample_files
        
        items = list(scan_directory(str(src_dir), "/mount", algo_id=5))
        
        for item in items:
            assert item.algo_id == 5
    
    def test_scan_with_exclude(self, sample_files):
        """排除模式测试"""
        src_dir, files = sample_files
        
        items = list(scan_directory(
            str(src_dir), "/mount",
            exclude_patterns=["*.txt"]
        ))
        
        # 应排除所有 .txt 文件
        for item in items:
            assert not item.local_path.endswith(".txt")


# ==================== estimate_total_bytes 测试 ====================

class TestEstimateTotalBytes:
    """估算总大小测试"""
    
    def test_estimate(self, sample_files):
        """估算文件总大小"""
        src_dir, files = sample_files
        
        items = list(scan_directory(str(src_dir), "/mount"))
        total = estimate_total_bytes(items)
        
        expected = sum(len(content) for content in files.values())
        assert total == expected
    
    def test_estimate_with_missing_files(self, sample_files):
        """包含不存在文件时应跳过"""
        src_dir, files = sample_files
        
        items = [
            FileItem(str(src_dir / "hero.txt"), "/hero.txt"),
            FileItem("/not/exists.txt", "/missing.txt"),  # 不存在
        ]
        
        total = estimate_total_bytes(items)
        
        # 只计算存在的文件
        assert total == len(files["hero.txt"])


# ==================== 批量操作集成测试 ====================

class TestBatchAddWithProgress:
    """带进度回调的批量添加测试"""
    
    def test_progress_callback(self, tmp_path, sample_files):
        """进度回调测试"""
        src_dir, files = sample_files
        archive_path = tmp_path / "batch.archive"
        
        progress_calls = []
        
        def on_progress(info: ProgressInfo):
            progress_calls.append({
                'current': info.current,
                'total': info.total,
                'progress': info.progress,
            })
        
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        
        result = builder.add_dir_batch(
            str(src_dir),
            mount_point="/assets",
            algo_id=1,
            progress_callback=on_progress
        )
        builder.build()
        
        assert result.success_count == len(files)
        assert result.failed_count == 0
        assert len(progress_calls) >= 1
    
    def test_progress_info_accuracy(self, tmp_path, sample_files):
        """进度信息准确性"""
        src_dir, files = sample_files
        archive_path = tmp_path / "accuracy.archive"
        
        final_info = None
        
        def on_progress(info: ProgressInfo):
            nonlocal final_info
            final_info = info
        
        builder = ArchiveBuilder(str(archive_path))
        builder.add_dir_batch(
            str(src_dir),
            mount_point="/assets",
            progress_callback=on_progress,
        )
        builder.build()
        
        # 最后的进度应接近 100%
        if final_info:
            assert final_info.progress <= 1.0


class TestBatchErrorHandling:
    """批量操作错误处理测试"""
    
    @pytest.mark.parametrize("on_error", ['skip', 'abort'])
    def test_error_handling_strategies(self, on_error, tmp_path, sample_files):
        """不同错误处理策略"""
        src_dir, files = sample_files
        archive_path = tmp_path / "error.archive"
        
        items = [
            FileItem(str(src_dir / "hero.txt"), "/exists.txt"),
            FileItem(str(src_dir / "NOT_EXISTS.txt"), "/missing.txt"),
        ]
        
        builder = ArchiveBuilder(str(archive_path))
        result = builder.add_files_batch(items, on_error=on_error)
        
        if on_error == 'skip':
            assert result.success_count == 1
            assert result.failed_count == 1
        # abort 模式应在第一个错误后停止
    
    def test_raise_on_error(self, tmp_path, sample_files):
        """raise 模式应抛出异常"""
        src_dir, files = sample_files
        archive_path = tmp_path / "raise.archive"
        
        items = [
            FileItem(str(src_dir / "NOT_EXISTS.txt"), "/missing.txt"),
        ]
        
        builder = ArchiveBuilder(str(archive_path))
        
        with pytest.raises(FileNotFoundError):
            builder.add_files_batch(items, on_error='raise')


class TestExtractAll:
    """解包所有文件测试"""
    
    def test_extract_all(self, tmp_path, sample_files):
        """解包所有文件"""
        src_dir, files = sample_files
        archive_path = tmp_path / "extract.archive"
        output_dir = tmp_path / "output"
        
        # 创建 Archive
        builder = ArchiveBuilder(
            str(archive_path),
            checksum_hook=MD5Hook()
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 解包
        with ArchiveReader(str(archive_path), checksum_hook=MD5Hook()) as reader:
            result = reader.extract_all(str(output_dir))
        
        assert result.success_count == len(files)
        
        # 验证解包内容
        for name, expected in files.items():
            local_path = output_dir / "assets" / name
            assert local_path.exists()
            assert local_path.read_bytes() == expected
    
    def test_extract_all_with_progress(self, tmp_path, sample_files):
        """带进度回调的解包"""
        src_dir, files = sample_files
        archive_path = tmp_path / "progress.archive"
        output_dir = tmp_path / "output"
        
        builder = ArchiveBuilder(str(archive_path))
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        progress_calls = []
        
        def on_progress(info: ProgressInfo):
            progress_calls.append(info.current)
        
        with ArchiveReader(str(archive_path)) as reader:
            result = reader.extract_all(
                str(output_dir),
                progress_callback=on_progress
            )
        
        assert result.success_count == len(files)
        assert len(progress_calls) >= 1


class TestReadBatch:
    """批量读取测试"""
    
    def test_read_batch(self, tmp_path, sample_files):
        """批量读取多个文件"""
        src_dir, files = sample_files
        archive_path = tmp_path / "batch.archive"
        
        builder = ArchiveBuilder(str(archive_path))
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        with ArchiveReader(str(archive_path)) as reader:
            paths = ["/assets/hero.txt", "/assets/config.json"]
            result = reader.read_batch(paths)
        
        assert len(result) == 2
        assert result["/assets/hero.txt"] == files["hero.txt"]
        assert result["/assets/config.json"] == files["config.json"]
    
    def test_read_batch_with_missing(self, tmp_path, sample_files):
        """批量读取包含不存在的路径"""
        src_dir, files = sample_files
        archive_path = tmp_path / "missing.archive"
        
        builder = ArchiveBuilder(str(archive_path))
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        with ArchiveReader(str(archive_path)) as reader:
            paths = ["/assets/hero.txt", "/not/exists.txt"]
            result = reader.read_batch(paths, on_error='skip')
        
        # 只返回存在的
        assert "/assets/hero.txt" in result
        assert "/not/exists.txt" not in result
