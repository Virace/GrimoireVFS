#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RcloneHashHook 单元测试

测试 rclone 兼容的哈希 Hook。
需要系统安装 rclone。
"""

import hashlib
import os
import tempfile

import pytest

from grimoire.hooks.rclone import RcloneHashHook, RcloneNotFoundError


@pytest.mark.rclone
class TestRcloneHashHookProperties:
    """测试 RcloneHashHook 属性"""
    
    @pytest.mark.parametrize("algorithm,expected_id,expected_size", [
        ("md5", 101, 16),
        ("sha1", 102, 20),
        ("sha256", 103, 32),
        ("sha512", 104, 64),
        ("crc32", 105, 4),
        ("xxh3", 107, 8),
        ("quickxor", 109, 20),
    ])
    def test_algorithm_properties(self, algorithm, expected_id, expected_size):
        """验证各算法的 algo_id 和 digest_size"""
        hook = RcloneHashHook(algorithm)
        
        assert hook.algo_id == expected_id
        assert hook.digest_size == expected_size
        assert hook.algorithm == algorithm
    
    def test_display_name(self):
        """验证 display_name 格式"""
        hook = RcloneHashHook("sha256")
        
        assert hook.display_name == "rclone:sha256"
    
    def test_repr(self):
        """验证 __repr__ 输出"""
        hook = RcloneHashHook("md5")
        
        assert repr(hook) == "RcloneHashHook('md5')"


@pytest.mark.rclone
class TestRcloneHashHookValidation:
    """测试 RcloneHashHook 输入验证"""
    
    def test_invalid_algorithm(self):
        """无效算法应抛出 ValueError"""
        with pytest.raises(ValueError, match="不支持的算法"):
            RcloneHashHook("invalid_algo")
    
    def test_case_insensitive(self):
        """算法名应不区分大小写"""
        hook1 = RcloneHashHook("MD5")
        hook2 = RcloneHashHook("md5")
        hook3 = RcloneHashHook("Md5")
        
        assert hook1.algorithm == "md5"
        assert hook2.algorithm == "md5"
        assert hook3.algorithm == "md5"


@pytest.mark.rclone
class TestRcloneComputeFile:
    """测试 RcloneHashHook.compute_file"""
    
    @pytest.fixture
    def temp_file(self, tmp_path):
        """创建临时测试文件"""
        file_path = tmp_path / "test.txt"
        content = b"Hello, GrimoireVFS!"
        file_path.write_bytes(content)
        return file_path, content
    
    def test_compute_file_md5(self, temp_file):
        """compute_file 应与 hashlib.md5 结果一致"""
        file_path, content = temp_file
        
        hook = RcloneHashHook("md5")
        result = hook.compute_file(str(file_path))
        
        expected = hashlib.md5(content).digest()
        assert result == expected
    
    def test_compute_file_sha256(self, temp_file):
        """compute_file 应与 hashlib.sha256 结果一致"""
        file_path, content = temp_file
        
        hook = RcloneHashHook("sha256")
        result = hook.compute_file(str(file_path))
        
        expected = hashlib.sha256(content).digest()
        assert result == expected
    
    def test_compute_file_sha1(self, temp_file):
        """compute_file 应与 hashlib.sha1 结果一致"""
        file_path, content = temp_file
        
        hook = RcloneHashHook("sha1")
        result = hook.compute_file(str(file_path))
        
        expected = hashlib.sha1(content).digest()
        assert result == expected


@pytest.mark.rclone
class TestRcloneComputeBytes:
    """测试 RcloneHashHook.compute (内存数据)"""
    
    def test_compute_md5(self):
        """compute 应与 hashlib.md5 结果一致"""
        data = b"Test data for hashing"
        
        hook = RcloneHashHook("md5")
        result = hook.compute(data)
        
        expected = hashlib.md5(data).digest()
        assert result == expected
    
    def test_compute_sha256(self):
        """compute 应与 hashlib.sha256 结果一致"""
        data = b"Test data for hashing"
        
        hook = RcloneHashHook("sha256")
        result = hook.compute(data)
        
        expected = hashlib.sha256(data).digest()
        assert result == expected


@pytest.mark.rclone
class TestRcloneQuickXor:
    """测试 QuickXorHash (OneDrive 特有算法)"""
    
    def test_quickxor_output_size(self, tmp_path):
        """QuickXorHash 应输出 20 字节"""
        file_path = tmp_path / "quickxor.txt"
        file_path.write_bytes(b"QuickXorHash test content" * 100)
        
        hook = RcloneHashHook("quickxor")
        result = hook.compute_file(str(file_path))
        
        assert len(result) == 20
    
    def test_quickxor_determinism(self, tmp_path):
        """QuickXorHash 应产生确定性结果"""
        file_path = tmp_path / "determinism.txt"
        file_path.write_bytes(b"Deterministic content")
        
        hook = RcloneHashHook("quickxor")
        result1 = hook.compute_file(str(file_path))
        result2 = hook.compute_file(str(file_path))
        
        assert result1 == result2


@pytest.mark.rclone
class TestRcloneBatchOperations:
    """测试 RcloneHashHook 批量操作"""
    
    def test_compute_dir(self, tmp_path):
        """compute_dir 应返回目录下所有文件的哈希"""
        # 创建测试文件
        (tmp_path / "a.txt").write_bytes(b"Content A")
        (tmp_path / "b.txt").write_bytes(b"Content B")
        
        hook = RcloneHashHook("md5")
        results = hook.compute_dir(str(tmp_path))
        
        assert "a.txt" in results
        assert "b.txt" in results
        assert results["a.txt"] == hashlib.md5(b"Content A").digest()
        assert results["b.txt"] == hashlib.md5(b"Content B").digest()
    
    def test_compute_files_batch(self, tmp_path):
        """compute_files_batch 应批量计算多个文件"""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_bytes(b"File 1")
        file2.write_bytes(b"File 2")
        
        hook = RcloneHashHook("md5")
        results = hook.compute_files_batch([str(file1), str(file2)])
        
        assert str(file1) in results
        assert str(file2) in results


@pytest.mark.rclone
class TestRcloneEdgeCases:
    """测试边界情况"""
    
    def test_empty_file(self, tmp_path):
        """空文件应正常处理"""
        file_path = tmp_path / "empty.txt"
        file_path.write_bytes(b"")
        
        hook = RcloneHashHook("md5")
        result = hook.compute_file(str(file_path))
        
        expected = hashlib.md5(b"").digest()
        assert result == expected
    
    def test_large_file(self, tmp_path):
        """大文件应正常处理"""
        file_path = tmp_path / "large.bin"
        content = b"x" * (1024 * 1024)  # 1MB
        file_path.write_bytes(content)
        
        hook = RcloneHashHook("md5")
        result = hook.compute_file(str(file_path))
        
        expected = hashlib.md5(content).digest()
        assert result == expected
    
    def test_unicode_filename(self, tmp_path):
        """Unicode 文件名应正常处理"""
        file_path = tmp_path / "测试文件.txt"
        content = b"Unicode test"
        file_path.write_bytes(content)
        
        hook = RcloneHashHook("md5")
        result = hook.compute_file(str(file_path))
        
        expected = hashlib.md5(content).digest()
        assert result == expected


class TestRcloneNotInstalled:
    """测试 rclone 未安装的情况"""
    
    def test_check_on_init_with_invalid_path(self):
        """无效的 rclone 路径应抛出 RcloneNotFoundError"""
        with pytest.raises(RcloneNotFoundError):
            RcloneHashHook("md5", rclone_path="/invalid/path/rclone")
    
    def test_skip_check_on_init(self):
        """check_on_init=False 应跳过可用性检查"""
        # 即使路径无效也不抛出异常
        hook = RcloneHashHook("md5", rclone_path="/invalid/path", check_on_init=False)
        assert hook.algorithm == "md5"
