#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Core Schema 模块测试

测试数据结构的序列化/反序列化。
"""

import pytest

from grimoire.core.schema import (
    FileHeader,
    IndexHeader,
    DataHeader,
    ManifestEntry,
    ArchiveEntry,
    MODE_MANIFEST,
    MODE_ARCHIVE,
)


# ==================== FileHeader 测试 ====================

class TestFileHeader:
    """FileHeader 测试"""
    
    def test_size_constant(self):
        """大小常量验证"""
        assert FileHeader.SIZE == 32
    
    def test_default_values(self):
        """默认值验证"""
        header = FileHeader()
        
        assert header.magic == b'GRIM'
        assert header.version == 3
        assert header.mode == MODE_MANIFEST
        assert header.flags == 0
        assert header.checksum_algo == 0
    
    def test_pack_unpack_roundtrip(self):
        """序列化往返测试"""
        original = FileHeader(
            magic=b'TEST',
            version=5,
            mode=MODE_ARCHIVE,
            flags=0x03,
            checksum_algo=4,
            index_offset=100,
            index_size=500,
            data_offset=600,
            entry_count=50
        )
        
        packed = original.pack()
        assert len(packed) == FileHeader.SIZE
        
        unpacked = FileHeader.unpack(packed)
        
        assert unpacked.magic == original.magic
        assert unpacked.version == original.version
        assert unpacked.mode == original.mode
        assert unpacked.flags == original.flags
        assert unpacked.checksum_algo == original.checksum_algo
        assert unpacked.index_offset == original.index_offset
        assert unpacked.index_size == original.index_size
        assert unpacked.data_offset == original.data_offset
        assert unpacked.entry_count == original.entry_count
    
    def test_unpack_invalid_size(self):
        """解包无效大小数据"""
        with pytest.raises(Exception):
            FileHeader.unpack(b'x' * 10)
    
    @pytest.mark.parametrize("mode", [MODE_MANIFEST, MODE_ARCHIVE])
    def test_mode_values(self, mode):
        """模式值测试"""
        header = FileHeader(mode=mode)
        packed = header.pack()
        unpacked = FileHeader.unpack(packed)
        
        assert unpacked.mode == mode


# ==================== IndexHeader 测试 ====================

class TestIndexHeader:
    """IndexHeader 测试"""
    
    def test_size_constant(self):
        """大小常量验证"""
        assert IndexHeader.SIZE == 16
    
    def test_default_values(self):
        """默认值验证"""
        header = IndexHeader()
        
        assert header.dir_count == 0
        assert header.name_count == 0
        assert header.ext_count == 0
        assert header.string_table_size == 0
        assert header.checksum_size == 0
    
    def test_pack_unpack_roundtrip(self):
        """序列化往返测试"""
        original = IndexHeader(
            dir_count=100,
            name_count=5000,
            ext_count=50,
            string_table_size=102400,
            checksum_size=16
        )
        
        packed = original.pack()
        assert len(packed) == IndexHeader.SIZE
        
        unpacked = IndexHeader.unpack(packed)
        
        assert unpacked.dir_count == original.dir_count
        assert unpacked.name_count == original.name_count
        assert unpacked.ext_count == original.ext_count
        assert unpacked.string_table_size == original.string_table_size
        assert unpacked.checksum_size == original.checksum_size


# ==================== DataHeader 测试 ====================

class TestDataHeader:
    """DataHeader 测试"""
    
    def test_size_constant(self):
        """大小常量验证"""
        assert DataHeader.SIZE == 16
    
    def test_default_values(self):
        """默认值验证"""
        header = DataHeader()
        
        assert header.magic == b'DATA'
        assert header.block_count == 0
        assert header.total_size == 0
    
    def test_pack_unpack_roundtrip(self):
        """序列化往返测试"""
        original = DataHeader(
            magic=b'DATA',
            block_count=1000,
            total_size=10240000
        )
        
        packed = original.pack()
        assert len(packed) == DataHeader.SIZE
        
        unpacked = DataHeader.unpack(packed)
        
        assert unpacked.magic == original.magic
        assert unpacked.block_count == original.block_count
        assert unpacked.total_size == original.total_size


# ==================== ManifestEntry 测试 ====================

class TestManifestEntry:
    """ManifestEntry 测试"""
    
    def test_base_size_constant(self):
        """基础大小常量验证"""
        assert ManifestEntry.BASE_SIZE == 24
    
    @pytest.mark.parametrize("checksum_size", [0, 4, 16, 20, 32])
    def test_entry_size(self, checksum_size):
        """条目大小计算"""
        expected = ManifestEntry.BASE_SIZE + checksum_size
        assert ManifestEntry.entry_size(checksum_size) == expected
    
    def test_pack_unpack_no_checksum(self):
        """无校验值的序列化往返"""
        original = ManifestEntry(
            path_hash=0x123456789ABCDEF0,
            dir_id=100,
            name_id=5000,
            ext_id=50,
            raw_size=102400,
            checksum=b''
        )
        
        packed = original.pack()
        assert len(packed) == ManifestEntry.BASE_SIZE
        
        unpacked = ManifestEntry.unpack(packed, checksum_size=0)
        
        assert unpacked.path_hash == original.path_hash
        assert unpacked.dir_id == original.dir_id
        assert unpacked.name_id == original.name_id
        assert unpacked.ext_id == original.ext_id
        assert unpacked.raw_size == original.raw_size
        assert unpacked.checksum == b''
    
    @pytest.mark.parametrize("checksum_size", [4, 16, 32])
    def test_pack_unpack_with_checksum(self, checksum_size):
        """带校验值的序列化往返"""
        checksum = b'X' * checksum_size
        
        original = ManifestEntry(
            path_hash=0xFEDCBA9876543210,
            dir_id=10,
            name_id=200,
            ext_id=5,
            raw_size=999,
            checksum=checksum
        )
        
        packed = original.pack()
        assert len(packed) == ManifestEntry.BASE_SIZE + checksum_size
        
        unpacked = ManifestEntry.unpack(packed, checksum_size=checksum_size)
        
        assert unpacked.path_hash == original.path_hash
        assert unpacked.checksum == checksum


# ==================== ArchiveEntry 测试 ====================

class TestArchiveEntry:
    """ArchiveEntry 测试"""
    
    def test_base_size_constant(self):
        """基础大小常量验证"""
        assert ArchiveEntry.BASE_SIZE == 42
    
    @pytest.mark.parametrize("checksum_size", [0, 4, 16, 20, 32])
    def test_entry_size(self, checksum_size):
        """条目大小计算"""
        expected = ArchiveEntry.BASE_SIZE + checksum_size
        assert ArchiveEntry.entry_size(checksum_size) == expected
    
    def test_pack_unpack_roundtrip(self):
        """序列化往返测试"""
        checksum = b'\xAB' * 16
        
        original = ArchiveEntry(
            path_hash=0x1234567890ABCDEF,
            dir_id=50,
            name_id=1000,
            ext_id=20,
            raw_size=50000,
            packed_size=30000,
            offset=102400,  # 修正字段名
            algo_id=1,
            checksum=checksum
        )
        
        packed = original.pack()
        assert len(packed) == ArchiveEntry.BASE_SIZE + 16
        
        unpacked = ArchiveEntry.unpack(packed, checksum_size=16)
        
        assert unpacked.path_hash == original.path_hash
        assert unpacked.dir_id == original.dir_id
        assert unpacked.name_id == original.name_id
        assert unpacked.ext_id == original.ext_id
        assert unpacked.raw_size == original.raw_size
        assert unpacked.packed_size == original.packed_size
        assert unpacked.offset == original.offset  # 修正字段名
        assert unpacked.algo_id == original.algo_id
        assert unpacked.checksum == original.checksum


# ==================== 边界条件测试 ====================

class TestSchemaEdgeCases:
    """边界条件测试"""
    
    def test_max_path_hash(self):
        """最大路径 Hash 值"""
        entry = ManifestEntry(path_hash=0xFFFFFFFFFFFFFFFF)
        packed = entry.pack()
        unpacked = ManifestEntry.unpack(packed)
        
        assert unpacked.path_hash == 0xFFFFFFFFFFFFFFFF
    
    def test_max_raw_size(self):
        """最大文件大小"""
        entry = ManifestEntry(raw_size=0xFFFFFFFFFFFFFFFF)
        packed = entry.pack()
        unpacked = ManifestEntry.unpack(packed)
        
        assert unpacked.raw_size == 0xFFFFFFFFFFFFFFFF
    
    def test_max_entry_count(self):
        """最大条目数"""
        header = FileHeader(entry_count=0xFFFFFFFF)
        packed = header.pack()
        unpacked = FileHeader.unpack(packed)
        
        assert unpacked.entry_count == 0xFFFFFFFF
