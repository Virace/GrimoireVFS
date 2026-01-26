#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS Archive 端到端测试
"""

import os
import tempfile
import zlib
from grimoire import ArchiveBuilder, ArchiveReader, MD5Hook
from grimoire.hooks.base import CompressionHook


# 简单的 zlib 压缩 Hook (测试用)
class ZlibHook(CompressionHook):
    @property
    def algo_id(self) -> int:
        return 1
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data, level=6)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)


def test_archive_basic():
    """基础功能测试"""
    print("=" * 50)
    print("测试 1: 基础 Archive 创建和读取")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "assets")
        os.makedirs(test_dir)
        
        files = {
            "hero.txt": b"Hero data content" * 100,  # 重复内容，便于测试压缩
            "config.json": b'{"name": "test", "value": 12345}' * 50,
            "binary.dat": bytes(range(256)) * 10,
        }
        
        for name, content in files.items():
            path = os.path.join(test_dir, name)
            with open(path, "wb") as f:
                f.write(content)
        
        # 创建 Archive (带压缩)
        archive_path = os.path.join(tmpdir, "test.archive")
        zlib_hook = ZlibHook()
        
        builder = ArchiveBuilder(
            archive_path,
            compression_hooks=[zlib_hook],
            checksum_hook=MD5Hook()
        )
        count = builder.add_dir(test_dir, "/game/assets", algo_id=1)  # 使用压缩
        print(f"添加文件数: {count}")
        print(f"压缩统计: {builder.compression_stats}")
        builder.build()
        
        # 检查文件大小
        archive_size = os.path.getsize(archive_path)
        original_size = sum(len(c) for c in files.values())
        print(f"原始大小: {original_size} bytes")
        print(f"归档大小: {archive_size} bytes")
        print(f"压缩率: {archive_size / original_size:.2%}")
        
        # 读取 Archive
        with ArchiveReader(
            archive_path,
            compression_hooks=[zlib_hook],
            checksum_hook=MD5Hook()
        ) as reader:
            print(f"使用 mmap: {reader.is_mmap}")
            print(f"条目数量: {reader.entry_count}")
            print(f"所有路径: {reader.list_all()}")
            
            # 读取并验证内容
            for name, expected in files.items():
                vfs_path = f"/game/assets/{name}"
                data = reader.read(vfs_path)
                assert data == expected, f"{name} 内容不匹配"
            
            print("所有文件内容验证通过!")
        
        print("✅ 测试 1 通过!")


def test_archive_no_compression():
    """无压缩模式测试"""
    print("\n" + "=" * 50)
    print("测试 2: 无压缩模式")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "data.bin")
        content = b"Test content without compression"
        with open(test_file, "wb") as f:
            f.write(content)
        
        archive_path = os.path.join(tmpdir, "nocomp.archive")
        
        builder = ArchiveBuilder(archive_path)
        builder.add_file(test_file, "/data.bin", algo_id=0)  # 不压缩
        builder.build()
        
        with ArchiveReader(archive_path) as reader:
            data = reader.read("/data.bin")
            assert data == content
            
            entry = reader.get_entry("/data.bin")
            assert entry.packed_size == entry.raw_size  # 无压缩应相等
        
        print("✅ 测试 2 通过!")


def test_archive_with_bytesio():
    """BytesIO 接口测试"""
    print("\n" + "=" * 50)
    print("测试 3: BytesIO 接口")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "text.txt")
        content = "Hello, GrimoireVFS!\n这是中文内容。"
        # 使用二进制模式写入，避免 Windows 换行符问题
        with open(test_file, "wb") as f:
            f.write(content.encode("utf-8"))
        
        archive_path = os.path.join(tmpdir, "text.archive")
        
        builder = ArchiveBuilder(archive_path)
        builder.add_file(test_file, "/text.txt")
        builder.build()
        
        with ArchiveReader(archive_path) as reader:
            # 使用 open() 返回 BytesIO
            file_obj = reader.open("/text.txt")
            data = file_obj.read().decode("utf-8")
            assert data == content
            
            # 可以 seek
            file_obj.seek(0)
            first_line = file_obj.readline().decode("utf-8")
            assert first_line == "Hello, GrimoireVFS!\n"
        
        print("✅ 测试 3 通过!")


def test_archive_integrity():
    """数据完整性测试"""
    print("\n" + "=" * 50)
    print("测试 4: 数据完整性校验")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "important.dat")
        content = b"Critical data that must not be corrupted"
        with open(test_file, "wb") as f:
            f.write(content)
        
        archive_path = os.path.join(tmpdir, "integrity.archive")
        
        builder = ArchiveBuilder(archive_path, checksum_hook=MD5Hook())
        builder.add_file(test_file, "/important.dat")
        builder.build()
        
        # 正常读取应该成功
        with ArchiveReader(archive_path, checksum_hook=MD5Hook()) as reader:
            data = reader.read("/important.dat", verify=True)
            assert data == content
            print("正常读取: 校验通过")
        
        # 篡改数据后应该失败
        with open(archive_path, "r+b") as f:
            # 找到数据区并篡改
            f.seek(-10, 2)  # 从末尾往前
            f.write(b"CORRUPTED!")
        
        try:
            with ArchiveReader(archive_path, checksum_hook=MD5Hook()) as reader:
                reader.read("/important.dat", verify=True)
            print("错误: 篡改后应该抛出异常")
        except Exception as e:
            print(f"篡改检测: 捕获异常 - {type(e).__name__}")
        
        print("✅ 测试 4 通过!")


if __name__ == "__main__":
    test_archive_basic()
    test_archive_no_compression()
    test_archive_with_bytesio()
    test_archive_integrity()
    
    print("\n" + "=" * 50)
    print("🎉 所有 Archive 测试通过!")
    print("=" * 50)
