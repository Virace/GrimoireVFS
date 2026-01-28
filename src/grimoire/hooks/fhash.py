#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fhash 外置工具 Hook

通过调用 fhash CLI 工具计算文件哈希，支持多种算法。
需要系统安装 fhash 或将其放置在可发现的路径。

fhash 项目地址: https://github.com/Virace/fast-hasher
"""

import base64
import json
import os
import subprocess
import tempfile
from typing import Optional, Dict, List

from .base import ChecksumHook
from .external import ExternalToolLocator


class FhashNotFoundError(Exception):
    """fhash 未安装或不可用"""
    pass


class FhashHook(ChecksumHook):
    """
    fhash 外置工具 Hook
    
    通过调用 fhash CLI 计算哈希，支持多种算法。
    性能远超纯 Python 实现，适合大文件和批量处理。
    
    支持的算法:
        md5, sha1, sha256, sha512, crc32, blake3, xxh3, xxh128, quickxor
    
    Usage:
        hook = FhashHook('sha256')
        hash_bytes = hook.compute_file('/path/to/file')
        
        # 批量处理
        results = hook.compute_files_batch(['/path/to/file1', '/path/to/file2'])
    """
    
    # fhash 支持的算法列表
    SUPPORTED_ALGORITHMS = {
        'md5', 'sha1', 'sha256', 'sha512', 'crc32',
        'blake3', 'xxh3', 'xxh128', 'quickxor'
    }
    
    # 使用 Base64 编码输出的算法
    BASE64_ALGORITHMS = {'quickxor'}
    
    def __init__(
        self,
        algorithm: str = 'sha256',
        fhash_path: Optional[str] = None,
        check_on_init: bool = True
    ):
        """
        初始化 FhashHook
        
        Args:
            algorithm: 哈希算法名称
            fhash_path: fhash 可执行文件路径 (可选，自动查找)
            check_on_init: 是否在初始化时检查 fhash 可用性
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
        self._algo_id, self._digest_size = ALGORITHM_REGISTRY[algorithm]
        
        # 查找 fhash 可执行文件
        self._fhash_path = fhash_path or ExternalToolLocator.find_executable('fhash')
        
        if check_on_init:
            self._check_fhash()
    
    @property
    def display_name(self) -> str:
        """返回 fhash:algorithm 格式的可读名称"""
        return f"fhash:{self._algorithm}"
    
    def _check_fhash(self) -> None:
        """检查 fhash 是否可用"""
        if not self._fhash_path:
            raise FhashNotFoundError(
                "找不到 fhash。请安装 fhash 或设置 GRIMOIRE_FHASH_PATH 环境变量。"
            )
        
        try:
            result = subprocess.run(
                [self._fhash_path, '-v'],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                raise FhashNotFoundError(f"fhash 执行失败: {result.stderr.decode()}")
        except FileNotFoundError:
            raise FhashNotFoundError(
                f"找不到 fhash: {self._fhash_path}。请安装或指定正确路径。"
            )
        except subprocess.TimeoutExpired:
            raise FhashNotFoundError("fhash 响应超时")
    
    @property
    def algo_id(self) -> int:
        return self._algo_id
    
    @property
    def digest_size(self) -> int:
        return self._digest_size
    
    @property
    def algorithm(self) -> str:
        return self._algorithm
    
    @property
    def fhash_path(self) -> Optional[str]:
        """返回 fhash 可执行文件路径"""
        return self._fhash_path
    
    def _decode_hash(self, hash_str: str) -> bytes:
        """
        解码哈希字符串
        
        quickxor 使用 Base64 编码，其他算法使用十六进制。
        
        Args:
            hash_str: 哈希字符串
            
        Returns:
            哈希值 (bytes)
        """
        if self._algorithm in self.BASE64_ALGORITHMS:
            return base64.b64decode(hash_str)
        return bytes.fromhex(hash_str)
    
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
            [self._fhash_path, '-a', self._algorithm, '-m', '-j', file_path],
            capture_output=True,
            check=True
        )
        
        # 解析 JSON Lines 输出
        output = result.stdout.decode('utf-8').strip()
        if not output:
            raise ValueError(f"fhash 无输出: {file_path}")
        
        data = json.loads(output)
        
        # 检查是否有错误
        if 'error' in data:
            raise ValueError(f"fhash 错误: {data['error']}")
        
        hash_hex = data.get(self._algorithm)
        if not hash_hex:
            raise ValueError(f"fhash 输出中找不到 {self._algorithm} 哈希")
        
        return self._decode_hash(hash_hex)
    
    def compute_files_batch(
        self,
        file_paths: List[str],
        timeout: Optional[int] = None
    ) -> Dict[str, bytes]:
        """
        批量计算多个文件的哈希
        
        使用 fhash 的批量处理能力，效率远高于逐个计算。
        
        Args:
            file_paths: 文件路径列表
            timeout: 超时时间 (秒)
            
        Returns:
            {file_path: hash_bytes} 字典
        """
        if not file_paths:
            return {}
        
        # 创建临时文件列表
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp:
            for path in file_paths:
                tmp.write(f"{path}\n")
            tmp_list_path = tmp.name
        
        try:
            result = subprocess.run(
                [self._fhash_path, '-a', self._algorithm, '-m', '-j', '-f', tmp_list_path],
                capture_output=True,
                timeout=timeout
            )
            
            results = {}
            for line in result.stdout.decode('utf-8').strip().split('\n'):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if 'error' in data:
                        # 跳过错误的文件
                        continue
                    
                    path = data.get('path', '')
                    hash_hex = data.get(self._algorithm)
                    
                    if path and hash_hex:
                        results[path] = self._decode_hash(hash_hex)
                except (json.JSONDecodeError, ValueError):
                    continue
            
            return results
            
        finally:
            os.unlink(tmp_list_path)
    
    def compute_dir(
        self,
        dir_path: str,
        recursive: bool = True,
        timeout: Optional[int] = None
    ) -> Dict[str, bytes]:
        """
        计算目录下所有文件的哈希
        
        Args:
            dir_path: 目录路径
            recursive: 是否递归子目录 (默认 True)
            timeout: 超时时间 (秒)
            
        Returns:
            {relative_path: hash_bytes} 字典
        """
        cmd = [self._fhash_path, '-a', self._algorithm, '-m', '-j', dir_path]
        
        if not recursive:
            # fhash 默认递归，需要限制深度
            cmd.extend(['--max-depth', '1'])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            return {}
        
        results = {}
        for line in result.stdout.decode('utf-8').strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)
                if 'error' in data:
                    continue
                
                path = data.get('path', '')
                hash_hex = data.get(self._algorithm)
                
                if path and hash_hex:
                    results[path] = self._decode_hash(hash_hex)
            except (json.JSONDecodeError, ValueError):
                continue
        
        return results
    
    def __repr__(self) -> str:
        return f"FhashHook('{self._algorithm}')"


# 便捷工厂函数
def fhash_hash(algorithm: str = 'sha256') -> FhashHook:
    """
    创建 FhashHook 的便捷函数
    
    Args:
        algorithm: 算法名称
        
    Returns:
        FhashHook 实例
    """
    return FhashHook(algorithm)
