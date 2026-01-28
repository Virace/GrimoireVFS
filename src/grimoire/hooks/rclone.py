#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Rclone 兼容的哈希 Hook

通过调用 rclone hashsum 命令计算文件哈希，支持多种算法。
需要系统已安装 rclone。
"""

import os
import subprocess
import tempfile
from typing import Optional, Dict, List
from .base import ChecksumHook


class RcloneNotFoundError(Exception):
    """rclone 未安装或不在 PATH 中"""
    pass


class RcloneHashHook(ChecksumHook):
    """
    Rclone 兼容的哈希 Hook
    
    通过调用 rclone hashsum 命令计算哈希，支持多种算法。
    性能远超纯 Python 实现，适合大文件和批量处理。
    
    支持的算法:
        md5, sha1, sha256, sha512, crc32, blake3, xxh3, xxh128,
        quickxor, dropbox, whirlpool, hidrive, mailru
    
    Usage:
        hook = RcloneHashHook('quickxor')
        hash_bytes = hook.compute_file('/path/to/file')
    """
    
    # rclone 支持的算法列表
    SUPPORTED_ALGORITHMS = {
        'md5', 'sha1', 'sha256', 'sha512', 'crc32',
        'blake3', 'xxh3', 'xxh128', 'quickxor'
    }
    
    def __init__(
        self,
        algorithm: str = 'sha256',
        rclone_path: str = 'rclone',
        check_on_init: bool = True
    ):
        """
        初始化 RcloneHashHook
        
        Args:
            algorithm: 哈希算法名称
            rclone_path: rclone 可执行文件路径或命令名
            check_on_init: 是否在初始化时检查 rclone 可用性
        """
        algorithm = algorithm.lower()
        if algorithm not in self.SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"不支持的算法: {algorithm}。"
                f"支持的算法: {list(self.SUPPORTED_ALGORITHMS)}"
            )
        
        # 从统一注册表获取 algo_id 和 digest_size
        from .registry import ALGORITHM_REGISTRY
        self._algorithm = algorithm
        self._rclone_path = rclone_path
        self._algo_id, self._digest_size = ALGORITHM_REGISTRY[algorithm]
        
        if check_on_init:
            self._check_rclone()
    
    @property
    def display_name(self) -> str:
        """返回 rclone:algorithm 格式的可读名称"""
        return f"rclone:{self._algorithm}"
    
    def _check_rclone(self) -> None:
        """检查 rclone 是否可用"""
        try:
            result = subprocess.run(
                [self._rclone_path, 'version'],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                raise RcloneNotFoundError(f"rclone 执行失败: {result.stderr.decode()}")
        except FileNotFoundError:
            raise RcloneNotFoundError(
                f"找不到 rclone: {self._rclone_path}。"
                "请安装 rclone 或指定正确路径。"
            )
        except subprocess.TimeoutExpired:
            raise RcloneNotFoundError("rclone 响应超时")
    
    @property
    def algo_id(self) -> int:
        return self._algo_id
    
    @property
    def digest_size(self) -> int:
        return self._digest_size
    
    @property
    def algorithm(self) -> str:
        return self._algorithm
    
    def compute(self, data: bytes) -> bytes:
        """
        计算内存数据的哈希
        
        注意: 此方法会将数据写入临时文件，效率较低。
        如果可能，请使用 compute_file() 直接计算文件。
        
        Args:
            data: 要计算哈希的数据
            
        Returns:
            哈希值 (bytes)
        """
        # 写入临时文件
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        
        try:
            return self.compute_file(tmp_path)
        finally:
            os.unlink(tmp_path)
    
    def compute_file(self, file_path: str) -> bytes:
        """
        计算单个文件的哈希 (推荐使用)
        
        Args:
            file_path: 文件路径
            
        Returns:
            哈希值 (bytes)
        """
        result = subprocess.run(
            [self._rclone_path, 'hashsum', self._algorithm, file_path],
            capture_output=True,
            check=True
        )
        
        # 解析输出: "hash  filename\n"
        output = result.stdout.decode('utf-8').strip()
        if not output:
            raise ValueError(f"rclone 无输出: {file_path}")
        
        hash_hex = output.split()[0]
        return bytes.fromhex(hash_hex)
    
    def compute_files_batch(
        self,
        file_paths: List[str],
        timeout: Optional[int] = None
    ) -> Dict[str, bytes]:
        """
        批量计算多个文件的哈希
        
        对于同一目录下的文件，使用目录模式批量计算。
        
        Args:
            file_paths: 文件路径列表
            timeout: 超时时间 (秒)
            
        Returns:
            {file_path: hash_bytes} 字典
        """
        if not file_paths:
            return {}
        
        # 按目录分组
        from collections import defaultdict
        dir_groups = defaultdict(list)
        for path in file_paths:
            dir_path = os.path.dirname(os.path.abspath(path))
            dir_groups[dir_path].append(path)
        
        results = {}
        
        for dir_path, paths in dir_groups.items():
            # 对每个目录调用 rclone hashsum
            dir_results = self.compute_dir(dir_path, timeout=timeout)
            
            # 匹配请求的文件
            for path in paths:
                filename = os.path.basename(path)
                if filename in dir_results:
                    results[path] = dir_results[filename]
                else:
                    # 回退到单文件计算
                    try:
                        results[path] = self.compute_file(path)
                    except Exception:
                        pass
        
        return results
    
    def compute_dir(
        self,
        dir_path: str,
        recursive: bool = False,
        timeout: Optional[int] = None
    ) -> Dict[str, bytes]:
        """
        计算目录下所有文件的哈希
        
        Args:
            dir_path: 目录路径
            recursive: 是否递归子目录
            timeout: 超时时间 (秒)
            
        Returns:
            {filename: hash_bytes} 字典 (非递归时为文件名，递归时为相对路径)
        """
        cmd = [self._rclone_path, 'hashsum', self._algorithm, dir_path]
        
        if not recursive:
            cmd.extend(['--max-depth', '1'])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            return {}
        
        # 解析输出
        results = {}
        for line in result.stdout.decode('utf-8').strip().split('\n'):
            if line:
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    hash_hex, filename = parts
                    try:
                        results[filename] = bytes.fromhex(hash_hex)
                    except ValueError:
                        pass
        
        return results
    
    def __repr__(self) -> str:
        return f"RcloneHashHook('{self._algorithm}')"


# 便捷工厂函数
def rclone_hash(algorithm: str = 'sha256') -> RcloneHashHook:
    """
    创建 RcloneHashHook 的便捷函数
    
    Args:
        algorithm: 算法名称
        
    Returns:
        RcloneHashHook 实例
    """
    return RcloneHashHook(algorithm)

