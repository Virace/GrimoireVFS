#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS 批量操作测试
"""

import os
import tempfile
import zlib
from grimoire import ArchiveBuilder, ArchiveReader, MD5Hook
from grimoire.core import FileItem, ProgressInfo, BatchResult
from grimoire.hooks.base import CompressionHook


class ZlibHook(CompressionHook):
    @property
    def algo_id(self) -> int:
        return 1
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data, level=6)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)


def test_batch_add_with_progress():
    """批量添加带进度回调测试"""
    print("=" * 50)
    print("测试 1: 批量添加带进度回调")
    print("=" * 50)
    
    progress_calls = []
    
    def on_progress(info: ProgressInfo):
        progress_calls.append({
            'current': info.current,
            'total': info.total,
            'progress': info.progress,
            'file': os.path.basename(info.current_file)
        })
        print(f"  进度: {info.current}/{info.total} ({info.progress:.1%}) - {os.path.basename(info.current_file)}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "assets")
        os.makedirs(test_dir)
        
        for i in range(10):
            with open(os.path.join(test_dir, f"file_{i}.txt"), "wb") as f:
                f.write(f"Content of file {i}".encode() * 100)
        
        # 批量添加
        archive_path = os.path.join(tmpdir, "batch.archive")
        builder = ArchiveBuilder(
            archive_path,
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        
        result = builder.add_dir_batch(
            test_dir,
            mount_point="/assets",
            algo_id=1,
            progress_callback=on_progress
        )
        
        print(f"\n结果: 成功 {result.success_count}, 失败 {result.failed_count}")
        print(f"总字节: {result.total_bytes}, 耗时: {result.elapsed_time:.3f}s")
        
        builder.build()
        
        # 验证
        assert result.success_count == 10
        assert result.failed_count == 0
        assert len(progress_calls) >= 1  # 可能因为间隔限制而少于 10
        
        print("✅ 测试 1 通过!")


def test_batch_add_with_skip():
    """批量添加跳过失败文件测试"""
    print("\n" + "=" * 50)
    print("测试 2: 批量添加跳过失败文件")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = os.path.join(tmpdir, "mixed")
        os.makedirs(test_dir)
        
        # 创建真实文件
        with open(os.path.join(test_dir, "real.txt"), "wb") as f:
            f.write(b"Real content")
        
        # 准备包含不存在文件的列表
        items = [
            FileItem(os.path.join(test_dir, "real.txt"), "/real.txt"),
            FileItem(os.path.join(test_dir, "not_exist.txt"), "/fake.txt"),  # 不存在
            FileItem(os.path.join(test_dir, "real.txt"), "/real2.txt"),  # 可以再添加
        ]
        
        archive_path = os.path.join(tmpdir, "skip.archive")
        builder = ArchiveBuilder(archive_path)
        
        result = builder.add_files_batch(items, on_error='skip')
        
        print(f"结果: 成功 {result.success_count}, 失败 {result.failed_count}")
        print(f"失败文件: {[os.path.basename(f[0]) for f in result.failed_files]}")
        
        assert result.success_count == 2  # real.txt 添加两次 (不同 vfs_path)
        assert result.failed_count == 1
        
        print("✅ 测试 2 通过!")


def test_extract_all_with_progress():
    """解包所有文件带进度测试"""
    print("\n" + "=" * 50)
    print("测试 3: 解包所有文件带进度")
    print("=" * 50)
    
    progress_calls = []
    
    def on_progress(info: ProgressInfo):
        progress_calls.append(info.current)
        print(f"  解包: {info.current}/{info.total} - {info.current_file}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "source")
        os.makedirs(os.path.join(test_dir, "subdir"))
        
        files = {
            "a.txt": b"Content A",
            "b.dat": b"Content B" * 10,
            "subdir/c.bin": bytes(range(256)),
        }
        
        for name, content in files.items():
            with open(os.path.join(test_dir, name), "wb") as f:
                f.write(content)
        
        # 创建归档
        archive_path = os.path.join(tmpdir, "extract.archive")
        builder = ArchiveBuilder(archive_path, checksum_hook=MD5Hook())
        builder.add_dir(test_dir, "/root")
        builder.build()
        
        # 解包
        output_dir = os.path.join(tmpdir, "output")
        
        with ArchiveReader(archive_path, checksum_hook=MD5Hook()) as reader:
            result = reader.extract_all(
                output_dir,
                progress_callback=on_progress
            )
        
        print(f"\n结果: 成功 {result.success_count}, 失败 {result.failed_count}")
        print(f"总字节: {result.total_bytes}, 耗时: {result.elapsed_time:.3f}s")
        
        # 验证解包内容
        for name, expected in files.items():
            local_path = os.path.join(output_dir, "root", name)
            assert os.path.exists(local_path), f"{name} 不存在"
            with open(local_path, "rb") as f:
                assert f.read() == expected, f"{name} 内容不匹配"
        
        assert result.success_count == 3
        
        print("✅ 测试 3 通过!")


def test_read_batch():
    """批量读取测试"""
    print("\n" + "=" * 50)
    print("测试 4: 批量读取")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "data")
        os.makedirs(test_dir)
        
        files = {
            "1.txt": b"One",
            "2.txt": b"Two",
            "3.txt": b"Three",
        }
        
        for name, content in files.items():
            with open(os.path.join(test_dir, name), "wb") as f:
                f.write(content)
        
        # 创建归档
        archive_path = os.path.join(tmpdir, "multi.archive")
        builder = ArchiveBuilder(archive_path)
        builder.add_dir(test_dir, "/files")
        builder.build()
        
        # 批量读取
        with ArchiveReader(archive_path) as reader:
            paths = ["/files/1.txt", "/files/3.txt"]
            result = reader.read_batch(paths)
            
            print(f"读取结果: {list(result.keys())}")
            
            assert result["/files/1.txt"] == b"One"
            assert result["/files/3.txt"] == b"Three"
            assert "/files/2.txt" not in result  # 未请求
        
        print("✅ 测试 4 通过!")


if __name__ == "__main__":
    test_batch_add_with_progress()
    test_batch_add_with_skip()
    test_extract_all_with_progress()
    test_read_batch()
    
    print("\n" + "=" * 50)
    print("🎉 所有批量操作测试通过!")
    print("=" * 50)
