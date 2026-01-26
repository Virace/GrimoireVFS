#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS Manifest 端到端测试
"""

import os
import tempfile
import shutil
from grimoire import ManifestBuilder, ManifestReader, MD5Hook


def test_manifest_basic():
    """基础功能测试"""
    print("=" * 50)
    print("测试 1: 基础 Manifest 创建和读取")
    print("=" * 50)
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = os.path.join(tmpdir, "assets")
        os.makedirs(test_dir)
        
        files = {
            "hero.txt": b"Hero data content",
            "config.json": b'{"name": "test"}',
            "subdir/data.bin": b"\x00\x01\x02\x03\x04",
        }
        
        for name, content in files.items():
            path = os.path.join(test_dir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)
        
        # 创建 Manifest
        manifest_path = os.path.join(tmpdir, "test.manifest")
        builder = ManifestBuilder(manifest_path, checksum_hook=MD5Hook())
        count = builder.add_dir(test_dir, "/game/assets")
        print(f"添加文件数: {count}")
        print(f"字典统计: {builder.path_stats}")
        builder.build()
        print(f"Manifest 已创建: {manifest_path}")
        
        # 读取 Manifest
        with ManifestReader(manifest_path, checksum_hook=MD5Hook()) as reader:
            print(f"条目数量: {reader.entry_count}")
            print(f"所有路径: {reader.list_all()}")
            
            # 测试存在性检查
            assert reader.exists("/game/assets/hero.txt"), "hero.txt 应该存在"
            assert not reader.exists("/not/exist.txt"), "不存在的文件应返回 False"
            
            # 测试文件校验
            hero_path = os.path.join(test_dir, "hero.txt")
            assert reader.verify_file("/game/assets/hero.txt", hero_path), "校验应通过"
            
            # 修改文件后校验应失败
            with open(hero_path, "wb") as f:
                f.write(b"Modified content")
            assert not reader.verify_file("/game/assets/hero.txt", hero_path), "修改后校验应失败"
        
        print("✅ 测试 1 通过!")


def test_manifest_chinese_path():
    """中文路径测试"""
    print("\n" + "=" * 50)
    print("测试 2: 中文路径支持")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建中文文件
        test_file = os.path.join(tmpdir, "测试文件.txt")
        with open(test_file, "wb") as f:
            f.write("这是中文内容".encode("utf-8"))
        
        manifest_path = os.path.join(tmpdir, "chinese.manifest")
        builder = ManifestBuilder(manifest_path, checksum_hook=MD5Hook())
        builder.add_file(test_file, "/游戏/资源/测试文件.txt")
        builder.build()
        
        with ManifestReader(manifest_path, checksum_hook=MD5Hook()) as reader:
            paths = reader.list_all()
            print(f"路径列表: {paths}")
            assert "/游戏/资源/测试文件.txt" in paths
            assert reader.exists("/游戏/资源/测试文件.txt")
        
        print("✅ 测试 2 通过!")


def test_manifest_encrypted():
    """加密索引测试"""
    print("\n" + "=" * 50)
    print("测试 3: 索引加密")
    print("=" * 50)
    
    from grimoire.hooks.base import IndexCryptoHook
    
    class SimpleXor(IndexCryptoHook):
        def __init__(self, key: bytes):
            self._key = key
        
        def _xor(self, data: bytes) -> bytes:
            return bytes(b ^ self._key[i % len(self._key)] for i, b in enumerate(data))
        
        def encrypt(self, data: bytes) -> bytes:
            return self._xor(data)
        
        def decrypt(self, data: bytes) -> bytes:
            return self._xor(data)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "secret.dat")
        with open(test_file, "wb") as f:
            f.write(b"Secret content")
        
        manifest_path = os.path.join(tmpdir, "encrypted.manifest")
        crypto = SimpleXor(b"mysecretkey")
        
        # 创建加密 Manifest
        builder = ManifestBuilder(manifest_path, index_crypto=crypto)
        builder.add_file(test_file, "/secret/data.dat")
        builder.build()
        
        # 不提供解密器，无法遍历
        with ManifestReader(manifest_path) as reader:
            assert not reader.is_decrypted, "未提供解密器应为未解密状态"
            # 但仍可通过 Hash 查询
            hashes = reader.list_hashes()
            print(f"Hash 列表 (可访问): {[hex(h) for h in hashes]}")
            
            try:
                reader.list_all()
                assert False, "应该抛出异常"
            except Exception as e:
                print(f"预期异常: {e}")
        
        # 提供解密器，可以遍历
        with ManifestReader(manifest_path, index_crypto=crypto) as reader:
            assert reader.is_decrypted
            paths = reader.list_all()
            print(f"解密后路径: {paths}")
            assert "/secret/data.dat" in paths
        
        print("✅ 测试 3 通过!")


if __name__ == "__main__":
    test_manifest_basic()
    test_manifest_chinese_path()
    test_manifest_encrypted()
    
    print("\n" + "=" * 50)
    print("🎉 所有测试通过!")
    print("=" * 50)
