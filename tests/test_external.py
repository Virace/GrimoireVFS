#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
外置工具管理模块测试

测试 ExternalToolLocator 和 ExternalToolManager。
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from grimoire.hooks.external import (
    ExternalToolLocator,
    ExternalToolManager,
    ToolInfo,
    get_tool_manager,
)


class TestExternalToolLocator:
    """测试 ExternalToolLocator"""
    
    def setup_method(self):
        """每个测试前清空缓存"""
        ExternalToolLocator.clear_cache()
    
    def test_explicit_path_highest_priority(self, tmp_path):
        """显式指定的路径应具有最高优先级"""
        # 创建一个假的可执行文件
        fake_exe = tmp_path / "fake_fhash.exe"
        fake_exe.write_text("fake")
        os.chmod(fake_exe, 0o755)
        
        result = ExternalToolLocator.find_executable(
            'fhash',
            explicit_path=str(fake_exe)
        )
        
        assert result == str(fake_exe)
    
    def test_invalid_explicit_path_returns_none(self):
        """无效的显式路径应继续搜索"""
        result = ExternalToolLocator.find_executable(
            'fhash',
            explicit_path='/nonexistent/path/fhash.exe',
            use_cache=False
        )
        # 如果系统没有 fhash，应返回 None
        # 如果有，返回系统路径
        # 这里只验证不会抛出异常
        assert result is None or os.path.exists(result)
    
    def test_env_var_priority(self, tmp_path):
        """环境变量应在系统 PATH 之前检查"""
        fake_exe = tmp_path / "fhash_from_env.exe"
        fake_exe.write_text("fake")
        os.chmod(fake_exe, 0o755)
        
        with patch.dict(os.environ, {'GRIMOIRE_FHASH_PATH': str(fake_exe)}):
            ExternalToolLocator.clear_cache()
            result = ExternalToolLocator.find_executable('fhash')
        
        assert result == str(fake_exe)
    
    def test_cache_is_used(self, tmp_path):
        """应使用缓存避免重复查找"""
        fake_exe = tmp_path / "cached.exe"
        fake_exe.write_text("fake")
        os.chmod(fake_exe, 0o755)
        
        # 第一次调用
        result1 = ExternalToolLocator.find_executable(
            'test_tool',
            explicit_path=str(fake_exe)
        )
        
        # 删除文件
        fake_exe.unlink()
        
        # 第二次调用应返回缓存结果
        result2 = ExternalToolLocator.find_executable(
            'test_tool',
            explicit_path=str(fake_exe)
        )
        
        assert result1 == result2
    
    def test_cache_bypass(self, tmp_path):
        """use_cache=False 应绕过缓存"""
        fake_exe = tmp_path / "bypass.exe"
        fake_exe.write_text("fake")
        os.chmod(fake_exe, 0o755)
        
        # 缓存结果
        ExternalToolLocator.find_executable(
            'bypass_tool',
            explicit_path=str(fake_exe)
        )
        
        # 删除文件
        fake_exe.unlink()
        
        # 绕过缓存应返回 None
        result = ExternalToolLocator.find_executable(
            'bypass_tool',
            explicit_path=str(fake_exe),
            use_cache=False
        )
        
        assert result is None
    
    def test_get_package_vendor_path(self):
        """应返回正确的 vendor/bin 路径"""
        vendor_path = ExternalToolLocator.get_package_vendor_path()
        
        assert vendor_path.name == 'bin'
        assert vendor_path.parent.name == 'vendor'
    
    def test_get_user_data_path(self):
        """应返回正确的用户数据目录"""
        user_path = ExternalToolLocator.get_user_data_path()
        
        assert user_path.name == 'bin'
        assert user_path.parent.name == '.grimoire'
        assert user_path.parent.parent == Path.home()


class TestExternalToolManager:
    """测试 ExternalToolManager"""
    
    def test_list_available_tools(self):
        """应列出所有可用工具"""
        manager = ExternalToolManager()
        tools = manager.list_available_tools()
        
        # 工具是否可用取决于系统环境
        assert isinstance(tools, list)
    
    def test_is_available(self):
        """is_available 应正确检测工具"""
        manager = ExternalToolManager()
        
        # 测试不存在的工具
        assert manager.is_available('nonexistent_tool_xyz') is False
    
    def test_get_best_checksum_tool_priority(self):
        """应按优先级返回工具 (fhash > rclone)"""
        manager = ExternalToolManager()
        
        # 如果有工具可用，验证返回的是 ToolInfo
        tool = manager.get_best_checksum_tool()
        
        if tool:
            assert isinstance(tool, ToolInfo)
            assert tool.name in ['fhash', 'rclone']


class TestGetToolManager:
    """测试全局单例"""
    
    def test_returns_same_instance(self):
        """应返回相同的单例实例"""
        manager1 = get_tool_manager()
        manager2 = get_tool_manager()
        
        assert manager1 is manager2


@pytest.mark.fhash
class TestFhashIntegration:
    """fhash 集成测试 (需要安装 fhash)"""
    
    def test_find_fhash(self):
        """应能找到 fhash"""
        path = ExternalToolLocator.find_executable('fhash')
        assert path is not None, "fhash 未安装"
    
    def test_get_fhash_info(self):
        """应能获取 fhash 版本信息"""
        info = ExternalToolLocator.get_tool_info('fhash')
        
        assert info is not None
        assert info.name == 'fhash'
        assert info.version.startswith('v')


@pytest.mark.rclone
class TestRcloneIntegration:
    """rclone 集成测试 (需要安装 rclone)"""
    
    def test_find_rclone(self):
        """应能找到 rclone"""
        path = ExternalToolLocator.find_executable('rclone')
        assert path is not None, "rclone 未安装"
    
    def test_get_rclone_info(self):
        """应能获取 rclone 版本信息"""
        info = ExternalToolLocator.get_tool_info('rclone')
        
        assert info is not None
        assert info.name == 'rclone'
        assert info.version.startswith('v')
