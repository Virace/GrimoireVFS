#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RcloneHashHook 测试
"""

import os
import tempfile
from grimoire import RcloneHashHook, RcloneNotFoundError, MD5Hook


def test_rclone_available():
    """测试 rclone 是否可用"""
    print("=" * 50)
    print("测试 1: 检查 rclone 可用性")
    print("=" * 50)
    
    try:
        hook = RcloneHashHook('sha256')
        print(f"✅ rclone 可用, 算法: {hook.algorithm}")
        return True
    except RcloneNotFoundError as e:
        print(f"⚠️ rclone 不可用: {e}")
        return False


def test_compute_file():
    """测试单文件计算"""
    print("\n" + "=" * 50)
    print("测试 2: 单文件哈希计算")
    print("=" * 50)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
        f.write(b"Hello, GrimoireVFS!")
        tmp_path = f.name
    
    try:
        # 使用 rclone 计算 MD5
        rclone_hook = RcloneHashHook('md5')
        rclone_hash = rclone_hook.compute_file(tmp_path)
        
        # 使用内置 MD5Hook 计算对比
        with open(tmp_path, 'rb') as f:
            builtin_hash = MD5Hook().compute(f.read())
        
        print(f"rclone MD5:  {rclone_hash.hex()}")
        print(f"builtin MD5: {builtin_hash.hex()}")
        
        assert rclone_hash == builtin_hash, "MD5 不匹配!"
        print("✅ 测试 2 通过!")
        
    finally:
        os.unlink(tmp_path)


def test_compute_bytes():
    """测试内存数据计算"""
    print("\n" + "=" * 50)
    print("测试 3: 内存数据哈希计算")
    print("=" * 50)
    
    data = b"Test data for hashing"
    
    rclone_hook = RcloneHashHook('sha256')
    rclone_hash = rclone_hook.compute(data)
    
    import hashlib
    builtin_hash = hashlib.sha256(data).digest()
    
    print(f"rclone SHA256:  {rclone_hash.hex()}")
    print(f"builtin SHA256: {builtin_hash.hex()}")
    
    assert rclone_hash == builtin_hash, "SHA256 不匹配!"
    print("✅ 测试 3 通过!")


def test_quickxor():
    """测试 QuickXorHash (rclone 特有)"""
    print("\n" + "=" * 50)
    print("测试 4: QuickXorHash 计算")
    print("=" * 50)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
        f.write(b"QuickXorHash test content" * 100)
        tmp_path = f.name
    
    try:
        hook = RcloneHashHook('quickxor')
        hash_bytes = hook.compute_file(tmp_path)
        
        print(f"QuickXorHash: {hash_bytes.hex()}")
        print(f"长度: {len(hash_bytes)} bytes")
        
        assert len(hash_bytes) == 20, "QuickXorHash 应该是 20 bytes"
        print("✅ 测试 4 通过!")
        
    finally:
        os.unlink(tmp_path)


def test_multiple_algorithms():
    """测试多种算法"""
    print("\n" + "=" * 50)
    print("测试 5: 多种算法支持")
    print("=" * 50)
    
    algorithms = ['md5', 'sha1', 'sha256', 'crc32']
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
        f.write(b"Multi-algorithm test")
        tmp_path = f.name
    
    try:
        for algo in algorithms:
            hook = RcloneHashHook(algo)
            hash_bytes = hook.compute_file(tmp_path)
            print(f"  {algo:10}: {hash_bytes.hex()} ({hook.digest_size} bytes)")
        
        print("✅ 测试 5 通过!")
        
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    if test_rclone_available():
        test_compute_file()
        test_compute_bytes()
        test_quickxor()
        test_multiple_algorithms()
        
        print("\n" + "=" * 50)
        print("🎉 所有 RcloneHashHook 测试通过!")
        print("=" * 50)
    else:
        print("\n⚠️ 请安装 rclone 后重新运行测试")
        print("  下载: https://rclone.org/downloads/")
