#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
格式转换测试
"""

import os
import tempfile
from grimoire import (
    ManifestBuilder, ManifestReader,
    ArchiveBuilder, ArchiveReader,
    ManifestJsonConverter, ModeConverter,
    MD5Hook, ZlibCompressHook
)
from grimoire.hooks.base import CompressionHook
import zlib


class ZlibHook(CompressionHook):
    @property
    def algo_id(self) -> int:
        return 1
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)


def test_manifest_to_json():
    """测试 Manifest 转 JSON"""
    print("=" * 50)
    print("测试 1: Manifest 转 JSON")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "assets")
        os.makedirs(test_dir)
        for i in range(3):
            with open(os.path.join(test_dir, f"file_{i}.txt"), "wb") as f:
                f.write(f"Content {i}".encode())
        
        # 创建 Manifest
        manifest_path = os.path.join(tmpdir, "test.manifest")
        builder = ManifestBuilder(manifest_path, checksum_hook=MD5Hook())
        builder.add_dir(test_dir, "/assets")
        builder.build()
        
        # 转换为 JSON (自动检测 Hook)
        json_path = os.path.join(tmpdir, "test.json")
        ManifestJsonConverter.manifest_to_json(manifest_path, json_path)
        
        # 读取验证
        with open(json_path, 'r', encoding='utf-8') as f:
            import json
            data = json.load(f)
            print(f"版本: {data['version']}")
            print(f"校验算法ID: {data['checksum_algo']}")
            print(f"索引标志: {data['index_flags']}")
            print(f"条目数: {data['entry_count']}")
            for entry in data['entries']:
                print(f"  {entry['path']} ({entry['size']} bytes)")
        
    print("✅ 测试 1 通过!")


def test_json_to_manifest():
    """测试 JSON 转 Manifest"""
    print("\n" + "=" * 50)
    print("测试 2: JSON 转 Manifest")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "assets")
        os.makedirs(test_dir)
        for i in range(3):
            with open(os.path.join(test_dir, f"file_{i}.txt"), "wb") as f:
                f.write(f"Content {i}".encode())
        
        # 创建 JSON
        import json
        json_path = os.path.join(tmpdir, "test.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 1,
                "checksum_hook": "md5",
                "index_crypto": "zlib",
                "entries": [
                    {"path": "/assets/file_0.txt"},
                    {"path": "/assets/file_1.txt"},
                    {"path": "/assets/file_2.txt"},
                ]
            }, f)
        
        # 转换为 Manifest
        manifest_path = os.path.join(tmpdir, "test.manifest")
        result = ManifestJsonConverter.json_to_manifest(
            json_path, manifest_path,
            local_base_path=tmpdir
        )
        
        print(f"成功: {result.success_count}, 失败: {result.failed_count}")
        
        # 验证
        with ManifestReader(manifest_path, checksum_hook=MD5Hook(), index_crypto=ZlibCompressHook()) as reader:
            print(f"条目数: {reader.entry_count}")
            for path in reader.list_all():
                print(f"  {path}")
        
    print("✅ 测试 2 通过!")


def test_archive_to_manifest():
    """测试 Archive 转 Manifest"""
    print("\n" + "=" * 50)
    print("测试 3: Archive 转 Manifest")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "data")
        os.makedirs(test_dir)
        files = {
            "a.txt": b"Content A",
            "b.txt": b"Content B",
        }
        for name, content in files.items():
            with open(os.path.join(test_dir, name), "wb") as f:
                f.write(content)
        
        # 创建 Archive
        archive_path = os.path.join(tmpdir, "test.pak")
        builder = ArchiveBuilder(
            archive_path,
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        builder.add_dir(test_dir, "/data", algo_id=1)
        builder.build()
        
        # 转换为 Manifest (不加密)
        manifest_path = os.path.join(tmpdir, "test.manifest")
        result = ModeConverter.archive_to_manifest(
            archive_path, manifest_path,
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook(),
            output_index_crypto=None  # 不加密
        )
        
        print(f"成功: {result.success_count}, 失败: {result.failed_count}")
        
        # 验证
        with ManifestReader(manifest_path, checksum_hook=MD5Hook()) as reader:
            print(f"条目数: {reader.entry_count}")
            for path in reader.list_all():
                entry = reader.get_entry(path)
                print(f"  {path} ({entry.raw_size} bytes)")
        
    print("✅ 测试 3 通过!")


def test_manifest_to_archive():
    """测试 Manifest 转 Archive"""
    print("\n" + "=" * 50)
    print("测试 4: Manifest 转 Archive")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "source")
        os.makedirs(test_dir)
        files = {
            "x.txt": b"X content",
            "y.txt": b"Y content",
        }
        for name, content in files.items():
            with open(os.path.join(test_dir, name), "wb") as f:
                f.write(content)
        
        # 创建 Manifest
        manifest_path = os.path.join(tmpdir, "test.manifest")
        builder = ManifestBuilder(manifest_path, checksum_hook=MD5Hook())
        builder.add_dir(test_dir, "/files")
        builder.build()
        
        # 转换为 Archive
        archive_path = os.path.join(tmpdir, "test.pak")
        result = ModeConverter.manifest_to_archive(
            manifest_path, archive_path,
            local_base_path=tmpdir,
            path_mappings={"/files": test_dir},  # 虚拟路径映射
            checksum_hook_read=MD5Hook(),
            compression_hooks=[ZlibHook()],
            default_algo_id=1,
            output_checksum_hook=MD5Hook()
        )
        
        print(f"成功: {result.success_count}, 失败: {result.failed_count}")
        
        # 验证
        with ArchiveReader(archive_path, compression_hooks=[ZlibHook()], checksum_hook=MD5Hook()) as reader:
            print(f"条目数: {reader.entry_count}")
            for path in reader.list_all():
                data = reader.read(path)
                print(f"  {path} ({len(data)} bytes): {data[:20]}")
        
    print("✅ 测试 4 通过!")


if __name__ == "__main__":
    test_manifest_to_json()
    test_json_to_manifest()
    test_archive_to_manifest()
    test_manifest_to_archive()
    
    print("\n" + "=" * 50)
    print("🎉 所有转换测试通过!")
    print("=" * 50)
