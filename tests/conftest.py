#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pytest 全局配置

提供共享 fixtures、自定义 markers 和测试工具。
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict

import pytest


# ==================== 路径常量 ====================

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# src 目录 (用于集成测试)
SRC_DIR = PROJECT_ROOT / "src"


# ==================== 自定义 Markers ====================

def pytest_configure(config):
    """注册自定义 markers"""
    config.addinivalue_line("markers", "rclone: 需要 rclone 环境的测试")
    config.addinivalue_line("markers", "fhash: 需要 fhash 环境的测试")
    config.addinivalue_line("markers", "slow: 耗时较长的测试")


# ==================== 外置工具检测 ====================

RCLONE_AVAILABLE = shutil.which('rclone') is not None

# fhash 检测：先检查环境变量，再检查 PATH
_fhash_env = os.environ.get('GRIMOIRE_FHASH_PATH')
FHASH_AVAILABLE = (
    (_fhash_env and os.path.exists(_fhash_env)) or
    shutil.which('fhash') is not None
)


def pytest_collection_modifyitems(config, items):
    """自动跳过需要外置工具但环境不可用的测试"""
    skip_rclone = pytest.mark.skip(reason="rclone 未安装，跳过相关测试")
    skip_fhash = pytest.mark.skip(reason="fhash 未安装，跳过相关测试")
    
    for item in items:
        if "rclone" in item.keywords and not RCLONE_AVAILABLE:
            item.add_marker(skip_rclone)
        if "fhash" in item.keywords and not FHASH_AVAILABLE:
            item.add_marker(skip_fhash)


# ==================== 基础 Fixtures ====================

@pytest.fixture
def temp_dir(tmp_path):
    """
    提供临时目录的 fixture
    
    使用 tmp_path 自动清理，测试结束后自动删除。
    """
    return tmp_path


@pytest.fixture
def sample_files(tmp_path) -> tuple:
    """
    创建测试文件集
    
    Returns:
        (目录路径, 文件内容字典)
    """
    files = {
        "hero.txt": b"Hero data content",
        "config.json": b'{"name": "test", "value": 123}',
        "subdir/data.bin": b"\x00\x01\x02\x03\x04\x05\x06\x07",
        "subdir/nested/deep.txt": b"Deep nested file content",
        "中文文件.txt": "这是中文内容测试".encode("utf-8"),
    }
    
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    
    return tmp_path, files


@pytest.fixture
def large_files(tmp_path) -> tuple:
    """
    创建大文件测试集 (用于压缩测试)
    
    Returns:
        (目录路径, 文件内容字典)
    """
    files = {
        "repeated.txt": b"Hello, GrimoireVFS! " * 1000,  # 可压缩内容
        "binary.dat": bytes(range(256)) * 100,  # 二进制数据
        "random.bin": os.urandom(10000),  # 随机数据 (难压缩)
    }
    
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    
    return tmp_path, files


@pytest.fixture(scope="module")
def src_directory():
    """
    项目 src 目录路径 (用于集成测试)
    
    注意: 此 fixture 仅提供只读访问，禁止修改或删除 src 文件！
    """
    assert SRC_DIR.exists(), f"src 目录不存在: {SRC_DIR}"
    return SRC_DIR


# ==================== Hook Fixtures ====================

@pytest.fixture
def md5_hook():
    """MD5Hook 实例"""
    from grimoire.hooks.checksum import MD5Hook
    return MD5Hook()


@pytest.fixture
def sha256_hook():
    """SHA256Hook 实例"""
    from grimoire.hooks.checksum import SHA256Hook
    return SHA256Hook()


@pytest.fixture
def crc32_hook():
    """CRC32Hook 实例"""
    from grimoire.hooks.checksum import CRC32Hook
    return CRC32Hook()


@pytest.fixture
def zlib_crypto():
    """ZlibCompressHook 实例"""
    from grimoire.hooks.crypto import ZlibCompressHook
    return ZlibCompressHook()


@pytest.fixture
def xor_crypto():
    """XorObfuscateHook 实例"""
    from grimoire.hooks.crypto import XorObfuscateHook
    return XorObfuscateHook()


@pytest.fixture
def zlib_xor_crypto():
    """ZlibXorHook 实例"""
    from grimoire.hooks.crypto import ZlibXorHook
    return ZlibXorHook()


# ==================== 压缩 Hook Fixture ====================

@pytest.fixture
def zlib_compression_hook():
    """
    创建 zlib 压缩 Hook
    
    这是一个测试用的简单 CompressionHook 实现。
    """
    import zlib
    from grimoire.hooks.base import CompressionHook
    
    class ZlibHook(CompressionHook):
        @property
        def algo_id(self) -> int:
            return 1
        
        def compress(self, data: bytes) -> bytes:
            return zlib.compress(data, level=6)
        
        def decompress(self, data: bytes, raw_size: int) -> bytes:
            return zlib.decompress(data)
    
    return ZlibHook()


# ==================== Manifest/Archive Fixtures ====================

@pytest.fixture
def manifest_file(tmp_path, sample_files, md5_hook):
    """
    创建一个预构建的 Manifest 文件
    
    Returns:
        (manifest路径, 源文件目录, 文件内容字典)
    """
    from grimoire import ManifestBuilder
    
    src_dir, files = sample_files
    manifest_path = tmp_path / "test.manifest"
    
    builder = ManifestBuilder(str(manifest_path), checksum_hook=md5_hook)
    builder.add_dir(str(src_dir), "/assets")
    builder.build()
    
    return manifest_path, src_dir, files


@pytest.fixture
def archive_file(tmp_path, sample_files, md5_hook, zlib_compression_hook):
    """
    创建一个预构建的 Archive 文件
    
    Returns:
        (archive路径, 源文件目录, 文件内容字典)
    """
    from grimoire import ArchiveBuilder
    
    src_dir, files = sample_files
    archive_path = tmp_path / "test.archive"
    
    builder = ArchiveBuilder(
        str(archive_path),
        compression_hooks=[zlib_compression_hook],
        checksum_hook=md5_hook
    )
    builder.add_dir(str(src_dir), "/assets", algo_id=1)
    builder.build()
    
    return archive_path, src_dir, files


# ==================== 自定义 Hook 测试 Fixtures ====================

@pytest.fixture
def custom_checksum_hook():
    """
    创建自定义 ChecksumHook (用于测试自定义 Hook 功能)
    """
    from grimoire.hooks.base import ChecksumHook
    
    class SimpleHash(ChecksumHook):
        """简单的自定义校验 Hook (仅用于测试)"""
        
        @property
        def algo_id(self) -> int:
            return 99  # 自定义 ID
        
        @property
        def display_name(self) -> str:
            return "simple_hash"
        
        @property
        def digest_size(self) -> int:
            return 8
        
        def compute(self, data: bytes) -> bytes:
            """简单的 XOR 折叠哈希"""
            result = 0
            for i, b in enumerate(data):
                result ^= b << (i % 8 * 8)
            return (result & 0xFFFFFFFFFFFFFFFF).to_bytes(8, 'little')
    
    return SimpleHash()


@pytest.fixture
def custom_crypto_hook():
    """
    创建自定义 IndexCryptoHook (用于测试自定义 Hook 功能)
    """
    from grimoire.hooks.base import IndexCryptoHook
    
    class SimpleReverse(IndexCryptoHook):
        """简单的反转加密 Hook (仅用于测试)"""
        
        @property
        def flags_id(self) -> int:
            return 0x10  # 自定义标志
        
        @property
        def display_name(self) -> str:
            return "reverse"
        
        def encrypt(self, data: bytes) -> bytes:
            return data[::-1]
        
        def decrypt(self, data: bytes) -> bytes:
            return data[::-1]
    
    return SimpleReverse()
