#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Utils 模块测试

测试工具函数。
"""

import hashlib

import pytest

from grimoire.utils import (
    normalize_path,
    split_path,
    default_path_hash,
    compute_file_hash,
)


# ==================== normalize_path 测试 ====================

class TestNormalizePath:
    """normalize_path 测试"""
    
    @pytest.mark.parametrize("input_path,expected", [
        # 基础路径规范化
        ("Game/MOD/hero.wad", "Game/MOD/hero.wad"),
        ("game/mod/hero.wad", "game/mod/hero.wad"),
        
        # 反斜杠转正斜杠
        ("Game\\MOD\\hero.wad", "Game/MOD/hero.wad"),
        ("Game\\MOD/hero.wad", "Game/MOD/hero.wad"),
        
        # 去除前后斜杠
        ("/Game/MOD/", "Game/MOD"),
        ("/Game/MOD", "Game/MOD"),
        ("Game/MOD/", "Game/MOD"),
        
        # 多余斜杠
        ("//a//b//", "a/b"),
        ("a///b", "a/b"),
        
        # 单个文件
        ("hero.wad", "hero.wad"),
        ("/hero.wad", "hero.wad"),
    ])
    def test_normalize(self, input_path, expected):
        """路径规范化测试"""
        result = normalize_path(input_path)
        assert result == expected
    
    def test_empty_path(self):
        """空路径"""
        result = normalize_path("")
        assert result == ""
    
    def test_root_only(self):
        """仅根路径"""
        result = normalize_path("/")
        assert result == ""


# ==================== split_path 测试 ====================

class TestSplitPath:
    """split_path 测试"""
    
    @pytest.mark.parametrize("input_path,expected", [
        # 标准三部分路径 (注意: normalize_path 会去除前导斜杠)
        ("/Game/MOD/hero_skin.wad", ("Game/MOD", "hero_skin", ".wad")),
        ("Game/MOD/hero.txt", ("Game/MOD", "hero", ".txt")),
        
        # 根目录文件 (无目录时返回 "/")
        ("/config.json", ("/", "config", ".json")),
        ("config.json", ("/", "config", ".json")),
        
        # 多重扩展名
        ("/data/archive.tar.gz", ("data", "archive.tar", ".gz")),
        
        # 无扩展名
        ("/bin/executable", ("bin", "executable", "")),
        
        # 隐藏文件
        (".hidden", ("/", ".hidden", "")),
        ("/dir/.gitignore", ("dir", ".gitignore", "")),
        
        # 深层嵌套
        ("/a/b/c/d/file.ext", ("a/b/c/d", "file", ".ext")),
    ])
    def test_split(self, input_path, expected):
        """路径分割测试"""
        result = split_path(input_path)
        assert result == expected
    
    def test_empty_path(self):
        """空路径"""
        result = split_path("")
        # 空路径时目录返回 "/", 文件名和扩展名为空
        assert result == ("/", "", "")


# ==================== default_path_hash 测试 ====================

class TestDefaultPathHash:
    """default_path_hash 测试"""
    
    def test_returns_int(self):
        """返回整数"""
        result = default_path_hash("/test/path.txt")
        assert isinstance(result, int)
    
    def test_deterministic(self):
        """确定性结果"""
        path = "/game/assets/hero.wad"
        
        result1 = default_path_hash(path)
        result2 = default_path_hash(path)
        
        assert result1 == result2
    
    def test_different_paths_different_hashes(self):
        """不同路径产生不同 Hash"""
        result1 = default_path_hash("/path/a")
        result2 = default_path_hash("/path/b")
        
        assert result1 != result2
    
    def test_uses_md5(self):
        """使用 MD5 算法"""
        path = "/test/path"
        
        # 手动计算期望值 (注意: default_path_hash 会先 normalize 路径)
        normalized = normalize_path(path)  # 变成 "test/path"
        md5_digest = hashlib.md5(normalized.encode('utf-8')).digest()
        expected = int.from_bytes(md5_digest[:8], 'little')
        
        result = default_path_hash(path)
        
        assert result == expected
    
    def test_64bit_range(self):
        """结果应在 64 位范围内"""
        paths = ["/a", "/b/c", "/very/long/path/to/file.ext"]
        
        for path in paths:
            result = default_path_hash(path)
            assert 0 <= result < 2**64
    
    def test_unicode_path(self):
        """Unicode 路径"""
        result = default_path_hash("/游戏/资源/英雄.wad")
        
        assert isinstance(result, int)
        assert 0 <= result < 2**64


# ==================== compute_file_hash 测试 ====================

class TestComputeFileHash:
    """compute_file_hash 测试"""
    
    def test_md5(self, tmp_path):
        """MD5 哈希"""
        file_path = tmp_path / "test.txt"
        content = b"Hello, World!"
        file_path.write_bytes(content)
        
        result = compute_file_hash(str(file_path), "md5")
        expected = hashlib.md5(content).digest()  # 返回 bytes
        
        assert result == expected
    
    def test_sha256(self, tmp_path):
        """SHA256 哈希"""
        file_path = tmp_path / "test.txt"
        content = b"Test content"
        file_path.write_bytes(content)
        
        result = compute_file_hash(str(file_path), "sha256")
        expected = hashlib.sha256(content).digest()
        
        assert result == expected
    
    def test_sha1(self, tmp_path):
        """SHA1 哈希"""
        file_path = tmp_path / "test.txt"
        content = b"SHA1 test"
        file_path.write_bytes(content)
        
        result = compute_file_hash(str(file_path), "sha1")
        expected = hashlib.sha1(content).digest()
        
        assert result == expected
    
    def test_empty_file(self, tmp_path):
        """空文件"""
        file_path = tmp_path / "empty.txt"
        file_path.write_bytes(b"")
        
        result = compute_file_hash(str(file_path), "md5")
        expected = hashlib.md5(b"").digest()
        
        assert result == expected
    
    def test_large_file(self, tmp_path):
        """大文件 (分块读取)"""
        file_path = tmp_path / "large.bin"
        content = b"x" * (1024 * 1024)  # 1MB
        file_path.write_bytes(content)
        
        result = compute_file_hash(str(file_path), "md5")
        expected = hashlib.md5(content).digest()
        
        assert result == expected
    
    def test_unicode_filename(self, tmp_path):
        """Unicode 文件名"""
        file_path = tmp_path / "测试文件.txt"
        content = b"Unicode test"
        file_path.write_bytes(content)
        
        result = compute_file_hash(str(file_path), "md5")
        expected = hashlib.md5(content).digest()
        
        assert result == expected
    
    def test_file_not_found(self, tmp_path):
        """文件不存在"""
        with pytest.raises(FileNotFoundError):
            compute_file_hash(str(tmp_path / "not_exists.txt"), "md5")
