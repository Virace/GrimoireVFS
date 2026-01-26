#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GrimoireVFS 工具函数

提供路径处理、Hash 计算等通用功能。
"""

import os
import hashlib
from typing import Tuple


def normalize_path(path: str) -> str:
    """
    路径规范化
    
    1. 反斜杠统一为正斜杠
    2. 确保以 / 开头
    3. 移除末尾斜杠
    4. 合并连续斜杠
    
    Args:
        path: 原始路径
        
    Returns:
        规范化后的路径
        
    Examples:
        >>> normalize_path("Game\\\\MOD\\\\hero.wad")
        '/Game/MOD/hero.wad'
        >>> normalize_path("/Game/MOD/")
        '/Game/MOD'
        >>> normalize_path("hero.wad")
        '/hero.wad'
    """
    # 反斜杠 → 正斜杠
    path = path.replace("\\", "/")
    
    # 合并连续斜杠
    while "//" in path:
        path = path.replace("//", "/")
    
    # 确保以 / 开头
    if not path.startswith("/"):
        path = "/" + path
    
    # 移除末尾斜杠 (除非是根目录)
    if len(path) > 1:
        path = path.rstrip("/")
    
    return path


def split_path(full_path: str) -> Tuple[str, str, str]:
    """
    拆分完整路径为 (目录, 文件名, 扩展名)
    
    文件名不含扩展名，扩展名包含点号。
    
    Args:
        full_path: 完整路径
        
    Returns:
        (目录路径, 文件名, 扩展名) 元组
        
    Examples:
        >>> split_path("/Game/MOD/hero_skin.wad")
        ('/Game/MOD', 'hero_skin', '.wad')
        >>> split_path("/config.json")
        ('/', 'config', '.json')
        >>> split_path("/data/README")
        ('/data', 'README', '')
    """
    normalized = normalize_path(full_path)
    
    # 分离目录和文件名
    dir_part = os.path.dirname(normalized)
    if not dir_part:
        dir_part = "/"
    
    basename = os.path.basename(normalized)
    
    # 分离文件名和扩展名
    name, ext = os.path.splitext(basename)
    
    return dir_part, name, ext


def default_path_hash(path: str) -> int:
    """
    计算路径的 64-bit Hash 值 (用于快速查找)
    
    使用 MD5 的前 8 字节作为 Hash 值。
    可被 xxhash 替换以获得更好的性能。
    
    Args:
        path: 路径字符串
        
    Returns:
        64-bit 整数 Hash 值
    """
    normalized = normalize_path(path)
    digest = hashlib.md5(normalized.encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'little')


def compute_file_hash(file_path: str, algorithm: str = 'md5', 
                      chunk_size: int = 1024 * 1024) -> bytes:
    """
    计算文件的 Hash 值 (用于校验)
    
    支持分块读取，适用于大文件。
    
    Args:
        file_path: 文件路径
        algorithm: Hash 算法名称 (md5, sha1, sha256 等)
        chunk_size: 分块大小，默认 1MB
        
    Returns:
        Hash 摘要字节
    """
    hasher = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    
    return hasher.digest()
