#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量操作与进度回调

提供批量文件处理、进度回调和错误处理的通用工具。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, List, Tuple, Iterator, Union
from pathlib import Path
import time


class ErrorPolicy(Enum):
    """错误处理策略"""
    RAISE = "raise"   # 立即抛出异常
    SKIP = "skip"     # 跳过失败文件，继续处理
    ABORT = "abort"   # 停止处理，保留已完成部分


@dataclass
class FileItem:
    """
    待处理的文件项
    
    用于批量操作时指定文件信息。
    """
    local_path: str           # 本地文件路径
    vfs_path: Optional[str] = None  # 虚拟路径 (可选)
    algo_id: int = 0          # 压缩算法 ID (仅 Archive)


@dataclass
class ProgressInfo:
    """
    进度信息
    
    传递给进度回调函数的数据结构。
    """
    current: int              # 当前已处理文件数
    total: int                # 总文件数
    current_file: str         # 当前正在处理的文件路径
    bytes_processed: int      # 已处理字节数
    bytes_total: int          # 总字节数 (预估)
    elapsed_time: float       # 已耗时 (秒)
    
    @property
    def progress(self) -> float:
        """进度百分比 (0.0 - 1.0)"""
        if self.total == 0:
            return 0.0
        return self.current / self.total
    
    @property
    def rate(self) -> float:
        """处理速率 (bytes/second)"""
        if self.elapsed_time == 0:
            return 0.0
        return self.bytes_processed / self.elapsed_time
    
    @property
    def eta(self) -> float:
        """预计剩余时间 (秒)"""
        if self.rate == 0:
            return float('inf')
        remaining_bytes = self.bytes_total - self.bytes_processed
        return remaining_bytes / self.rate


@dataclass
class BatchResult:
    """
    批量操作结果
    
    包含成功/失败统计和详细信息。
    """
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    total_bytes: int = 0
    elapsed_time: float = 0.0
    failed_files: List[Tuple[str, Exception]] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)
    
    @property
    def total_count(self) -> int:
        return self.success_count + self.failed_count + self.skipped_count
    
    @property
    def success_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count


# 进度回调函数类型
ProgressCallback = Callable[[ProgressInfo], None]


class ProgressTracker:
    """
    进度跟踪器
    
    封装进度计算和回调调用逻辑。
    """
    
    def __init__(
        self,
        total_files: int,
        total_bytes: int = 0,
        callback: Optional[ProgressCallback] = None,
        callback_interval: float = 0.1  # 最小回调间隔 (秒)
    ):
        self._total_files = total_files
        self._total_bytes = total_bytes
        self._callback = callback
        self._callback_interval = callback_interval
        
        self._current_file = 0
        self._processed_bytes = 0
        self._start_time = time.time()
        self._last_callback_time = 0.0
    
    def update(self, file_path: str, bytes_processed: int = 0) -> None:
        """
        更新进度
        
        Args:
            file_path: 当前处理的文件路径
            bytes_processed: 本次处理的字节数
        """
        self._current_file += 1
        self._processed_bytes += bytes_processed
        
        if self._callback:
            now = time.time()
            # 限制回调频率
            if now - self._last_callback_time >= self._callback_interval:
                info = ProgressInfo(
                    current=self._current_file,
                    total=self._total_files,
                    current_file=file_path,
                    bytes_processed=self._processed_bytes,
                    bytes_total=self._total_bytes,
                    elapsed_time=now - self._start_time
                )
                self._callback(info)
                self._last_callback_time = now
    
    def finish(self) -> float:
        """完成并返回总耗时"""
        return time.time() - self._start_time


def scan_directory(
    directory: str,
    mount_point: str = "/",
    recursive: bool = True,
    algo_id: int = 0,
    exclude_patterns: Optional[List[str]] = None
) -> Iterator[FileItem]:
    """
    扫描目录生成 FileItem 迭代器
    
    使用生成器节省内存，适用于大目录。
    
    Args:
        directory: 本地目录路径
        mount_point: 虚拟挂载点
        recursive: 是否递归扫描
        algo_id: 压缩算法 ID
        exclude_patterns: 排除的文件模式 (glob)
        
    Yields:
        FileItem 对象
    """
    import fnmatch
    from ..utils import normalize_path
    
    base_path = Path(directory)
    mount_point = normalize_path(mount_point)
    
    def should_exclude(path: Path) -> bool:
        if not exclude_patterns:
            return False
        name = path.name
        return any(fnmatch.fnmatch(name, pattern) for pattern in exclude_patterns)
    
    if recursive:
        for file_path in base_path.rglob("*"):
            if file_path.is_file() and not should_exclude(file_path):
                rel_path = file_path.relative_to(base_path)
                vfs_path = mount_point + "/" + str(rel_path).replace("\\", "/")
                yield FileItem(
                    local_path=str(file_path),
                    vfs_path=vfs_path,
                    algo_id=algo_id
                )
    else:
        for file_path in base_path.iterdir():
            if file_path.is_file() and not should_exclude(file_path):
                vfs_path = mount_point + "/" + file_path.name
                yield FileItem(
                    local_path=str(file_path),
                    vfs_path=vfs_path,
                    algo_id=algo_id
                )


def estimate_total_bytes(items: List[FileItem]) -> int:
    """
    估算文件总大小
    
    Args:
        items: FileItem 列表
        
    Returns:
        总字节数
    """
    import os
    total = 0
    for item in items:
        try:
            total += os.path.getsize(item.local_path)
        except OSError:
            pass
    return total
