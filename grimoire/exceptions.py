#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS 异常定义

所有异常均继承自 GrimoireError，便于统一捕获。
"""

from typing import List


class GrimoireError(Exception):
    """GrimoireVFS 基础异常"""
    pass


class HashCollisionError(GrimoireError):
    """
    路径 Hash 冲突异常
    
    当两个不同的路径产生相同的 path_hash 时抛出。
    这种情况极为罕见 (xxHash64 冲突概率约 1/2^64)，但理论上存在。
    """
    def __init__(self, path1: str, path2: str, hash_value: int):
        self.path1 = path1
        self.path2 = path2
        self.hash_value = hash_value
        super().__init__(
            f"路径 Hash 冲突: '{path1}' 与 '{path2}' "
            f"产生相同的 Hash 值 {hash_value:#018x}"
        )


class CorruptedDataError(GrimoireError):
    """
    数据损坏异常
    
    当文件校验失败时抛出，可能由于传输错误或文件被篡改。
    """
    def __init__(self, vfs_path: str, expected: bytes, actual: bytes):
        self.vfs_path = vfs_path
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"文件 '{vfs_path}' 校验失败: "
            f"期望 {expected.hex()}, 实际 {actual.hex()}"
        )


class UnknownAlgorithmError(GrimoireError):
    """
    未知算法 ID 异常
    
    当遇到未注册的压缩/校验算法 ID 时抛出。
    """
    def __init__(self, algo_id: int, algo_type: str = "algorithm"):
        self.algo_id = algo_id
        self.algo_type = algo_type
        super().__init__(f"未知的 {algo_type} ID: {algo_id}")


class InvalidFormatError(GrimoireError):
    """
    文件格式无效异常
    
    当文件魔法数、版本号或结构不符合预期时抛出。
    """
    def __init__(self, message: str, expected: str = None, actual: str = None):
        self.expected = expected
        self.actual = actual
        if expected and actual:
            message = f"{message}: 期望 {expected}, 实际 {actual}"
        super().__init__(message)


class VersionMismatchError(GrimoireError):
    """
    版本不匹配异常
    
    当文件版本不受当前库版本支持时抛出。
    """
    def __init__(self, file_version: int, supported_versions: List[int]):
        self.file_version = file_version
        self.supported_versions = supported_versions
        super().__init__(
            f"不支持的文件版本 {file_version}, "
            f"支持的版本: {supported_versions}"
        )


class IndexNotDecryptedError(GrimoireError):
    """
    索引未解密异常
    
    当尝试遍历文件列表但索引区加密且未提供解密器时抛出。
    """
    def __init__(self, message: str = None):
        super().__init__(
            message or "索引区已加密，需要提供 IndexCryptoHook 才能遍历文件列表"
        )
