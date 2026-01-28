#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
外置工具发现与管理模块

提供统一的外置可执行文件（如 fhash、rclone）定位策略。
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ToolInfo:
    """外置工具信息"""
    name: str
    path: str
    version: str
    available: bool = True


class ExternalToolLocator:
    """
    外置工具定位器
    
    按优先级搜索可执行文件：
    1. 显式指定路径
    2. 环境变量 (如 GRIMOIRE_FHASH_PATH)
    3. 系统 PATH
    4. 库安装目录下的 vendor/bin/
    5. 用户数据目录 ~/.grimoire/bin/
    """
    
    # 工具名到环境变量名的映射
    ENV_VAR_MAP = {
        'fhash': 'GRIMOIRE_FHASH_PATH',
        'rclone': 'GRIMOIRE_RCLONE_PATH',
    }
    
    # Windows 可执行文件扩展名
    WINDOWS_EXTS = ['.exe', '.cmd', '.bat']
    
    _cache: Dict[str, Optional[str]] = {}
    
    @classmethod
    def clear_cache(cls) -> None:
        """清空路径缓存"""
        cls._cache.clear()
    
    @classmethod
    def find_executable(
        cls,
        name: str,
        explicit_path: Optional[str] = None,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        按优先级搜索可执行文件
        
        Args:
            name: 工具名 (如 'fhash', 'rclone')
            explicit_path: 显式指定的路径 (最高优先级)
            use_cache: 是否使用缓存
            
        Returns:
            可执行文件的完整路径，未找到返回 None
        """
        cache_key = f"{name}:{explicit_path or ''}"
        
        if use_cache and cache_key in cls._cache:
            return cls._cache[cache_key]
        
        result = cls._find_executable_impl(name, explicit_path)
        
        if use_cache:
            cls._cache[cache_key] = result
            
        return result
    
    @classmethod
    def _find_executable_impl(
        cls,
        name: str,
        explicit_path: Optional[str] = None
    ) -> Optional[str]:
        """实际的搜索实现"""
        
        # 1. 显式指定路径
        if explicit_path:
            if cls._is_valid_executable(explicit_path):
                return explicit_path
        
        # 2. 环境变量
        env_var = cls.ENV_VAR_MAP.get(name)
        if env_var:
            env_path = os.environ.get(env_var)
            if env_path and cls._is_valid_executable(env_path):
                return env_path
        
        # 3. 系统 PATH (使用 shutil.which)
        system_path = shutil.which(name)
        if system_path:
            return system_path
        
        # 4. 库 vendor/bin 目录
        vendor_path = cls._find_in_vendor(name)
        if vendor_path:
            return vendor_path
        
        # 5. 用户数据目录
        user_path = cls._find_in_user_data(name)
        if user_path:
            return user_path
        
        return None
    
    @classmethod
    def _is_valid_executable(cls, path: str) -> bool:
        """检查是否为有效的可执行文件"""
        p = Path(path)
        return p.exists() and p.is_file() and os.access(path, os.X_OK)
    
    @classmethod
    def _find_in_vendor(cls, name: str) -> Optional[str]:
        """在库 vendor/bin 目录中查找"""
        vendor_dir = cls.get_package_vendor_path()
        return cls._find_in_directory(vendor_dir, name)
    
    @classmethod
    def _find_in_user_data(cls, name: str) -> Optional[str]:
        """在用户数据目录中查找"""
        user_dir = cls.get_user_data_path()
        return cls._find_in_directory(user_dir, name)
    
    @classmethod
    def _find_in_directory(cls, directory: Path, name: str) -> Optional[str]:
        """在指定目录中查找可执行文件"""
        if not directory.exists():
            return None
        
        # 尝试不同的文件名变体
        candidates = [name]
        
        if os.name == 'nt':
            # Windows: 尝试带扩展名的版本
            for ext in cls.WINDOWS_EXTS:
                candidates.append(f"{name}{ext}")
                # 也尝试带架构后缀的版本
                candidates.append(f"{name}-windows-amd64{ext}")
        
        for candidate in candidates:
            path = directory / candidate
            if path.exists() and os.access(path, os.X_OK):
                return str(path)
        
        return None
    
    @classmethod
    def get_package_vendor_path(cls) -> Path:
        """
        获取库 vendor/bin 目录
        
        返回 grimoire 包目录下的 vendor/bin 路径。
        """
        # 获取当前模块所在目录 (hooks/)
        hooks_dir = Path(__file__).parent
        # 上级目录是 grimoire/
        grimoire_dir = hooks_dir.parent
        return grimoire_dir / 'vendor' / 'bin'
    
    @classmethod
    def get_user_data_path(cls) -> Path:
        """
        获取用户数据目录
        
        返回 ~/.grimoire/bin/ 路径。
        """
        home = Path.home()
        return home / '.grimoire' / 'bin'
    
    @classmethod
    def get_tool_info(cls, name: str, path: Optional[str] = None) -> Optional[ToolInfo]:
        """
        获取工具信息（包括版本）
        
        Args:
            name: 工具名
            path: 可选的显式路径
            
        Returns:
            ToolInfo 对象，工具不可用返回 None
        """
        executable = path or cls.find_executable(name)
        if not executable:
            return None
        
        version = cls._get_tool_version(executable)
        if version is None:
            return None
        
        return ToolInfo(
            name=name,
            path=executable,
            version=version,
            available=True
        )
    
    @classmethod
    def _get_tool_version(cls, path: str) -> Optional[str]:
        """获取工具版本号"""
        try:
            # fhash 和 rclone 都支持 -v 或 version 命令
            result = subprocess.run(
                [path, '-v'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # 解析版本输出
                # fhash: "fhash v0.1.0"
                # rclone: "rclone v1.72.1"
                output = result.stdout.strip()
                if output:
                    first_line = output.split('\n')[0]
                    # 提取 vX.X.X 部分
                    for part in first_line.split():
                        if part.startswith('v') and '.' in part:
                            return part
                    return first_line
            
            # 尝试 version 命令 (rclone)
            result = subprocess.run(
                [path, 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                first_line = result.stdout.strip().split('\n')[0]
                for part in first_line.split():
                    if part.startswith('v') and '.' in part:
                        return part
                return first_line
                
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        
        return None


class ExternalToolManager:
    """
    外置工具管理器
    
    管理多个外置工具，提供统一的获取接口。
    """
    
    # 工具优先级（用于校验算法）
    CHECKSUM_TOOL_PRIORITY = ['fhash', 'rclone']
    
    def __init__(self):
        self._tools: Dict[str, Optional[ToolInfo]] = {}
        self._initialized = False
    
    def initialize(self) -> None:
        """初始化，检测所有可用工具"""
        if self._initialized:
            return
        
        for tool_name in self.CHECKSUM_TOOL_PRIORITY:
            info = ExternalToolLocator.get_tool_info(tool_name)
            self._tools[tool_name] = info
        
        self._initialized = True
    
    def get_best_checksum_tool(self) -> Optional[ToolInfo]:
        """
        获取最佳的校验工具
        
        按优先级返回第一个可用的工具。
        
        Returns:
            ToolInfo 或 None
        """
        self.initialize()
        
        for tool_name in self.CHECKSUM_TOOL_PRIORITY:
            info = self._tools.get(tool_name)
            if info and info.available:
                return info
        
        return None
    
    def get_tool(self, name: str) -> Optional[ToolInfo]:
        """获取指定工具"""
        self.initialize()
        return self._tools.get(name)
    
    def is_available(self, name: str) -> bool:
        """检查工具是否可用"""
        info = self.get_tool(name)
        return info is not None and info.available
    
    def list_available_tools(self) -> list[str]:
        """列出所有可用工具"""
        self.initialize()
        return [name for name, info in self._tools.items() if info and info.available]


# 全局单例
_tool_manager: Optional[ExternalToolManager] = None


def get_tool_manager() -> ExternalToolManager:
    """获取全局工具管理器单例"""
    global _tool_manager
    if _tool_manager is None:
        _tool_manager = ExternalToolManager()
    return _tool_manager
