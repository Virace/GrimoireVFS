#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
格式转换测试

测试 Manifest/Archive/JSON 之间的互转功能。
"""

import json
import zlib

import pytest

from grimoire import (
    ManifestBuilder, ManifestReader,
    ArchiveBuilder, ArchiveReader,
    ManifestJsonConverter, ModeConverter,
    MD5Hook,
)
from grimoire.converter import merge_manifests, MergeResult
from grimoire.hooks.checksum import SHA256Hook, CRC32Hook
from grimoire.hooks.crypto import ZlibCompressHook, XorObfuscateHook
from grimoire.hooks.base import CompressionHook
from grimoire.exceptions import (
    ManifestVersionMismatchError,
    ManifestAlgorithmMismatchError,
    PathConflictError,
)


# ==================== 测试用压缩 Hook ====================

class ZlibHook(CompressionHook):
    @property
    def algo_id(self) -> int:
        return 1
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)


# ==================== Manifest ↔ JSON 转换测试 ====================

class TestManifestToJson:
    """Manifest 转 JSON 测试"""
    
    def test_basic_conversion(self, tmp_path, sample_files):
        """基础转换"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "test.manifest"
        json_path = tmp_path / "test.json"
        
        # 创建 Manifest
        builder = ManifestBuilder(str(manifest_path), checksum_hook=MD5Hook())
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 转换为 JSON
        ManifestJsonConverter.manifest_to_json(str(manifest_path), str(json_path))
        
        # 验证 JSON 内容
        assert json_path.exists()
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["version"] == 2
        assert data["checksum_algo"] == 2  # MD5
        assert data["entry_count"] == len(files)
        assert len(data["entries"]) == len(files)
    
    def test_json_contains_hook_names(self, tmp_path, sample_files):
        """JSON 应包含 Hook 名称"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "named.manifest"
        json_path = tmp_path / "named.json"
        
        builder = ManifestBuilder(
            str(manifest_path),
            checksum_hook=MD5Hook(),
            index_crypto=ZlibCompressHook()
        )
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        ManifestJsonConverter.manifest_to_json(str(manifest_path), str(json_path))
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["checksum_algo_name"] == "md5"
        assert data["index_flags_name"] == "zlib"
    
    @pytest.mark.parametrize("checksum_hook,expected_algo_id", [
        (MD5Hook(), 2),
        (SHA256Hook(), 4),
        (CRC32Hook(), 1),
    ])
    def test_different_checksum_algorithms(
        self, checksum_hook, expected_algo_id, tmp_path, sample_files
    ):
        """测试不同校验算法的转换"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "algo.manifest"
        json_path = tmp_path / "algo.json"
        
        builder = ManifestBuilder(str(manifest_path), checksum_hook=checksum_hook)
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        ManifestJsonConverter.manifest_to_json(str(manifest_path), str(json_path))
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["checksum_algo"] == expected_algo_id


class TestJsonToManifest:
    """JSON 转 Manifest 测试"""
    
    def test_basic_conversion(self, tmp_path, sample_files):
        """基础转换"""
        src_dir, files = sample_files
        json_path = tmp_path / "input.json"
        manifest_path = tmp_path / "output.manifest"
        
        # 创建 JSON (路径格式与 normalize_path 输出一致，无前导斜杠)
        entries = [{"path": f"assets/{name}"} for name in files.keys()]
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 2,
                "index_flags": 0,
                "entries": entries
            }, f)
        
        # 转换并验证
        result = ManifestJsonConverter.json_to_manifest(
            str(json_path),
            str(manifest_path),
            local_base_path=str(src_dir),
            path_mappings={"assets": str(src_dir)}
        )
        
        assert result.success_count == len(files)
        assert result.failed_count == 0
        
        # 读取验证
        with ManifestReader(str(manifest_path), checksum_hook=MD5Hook()) as reader:
            assert reader.entry_count == len(files)
    
    def test_with_path_mappings(self, tmp_path, sample_files):
        """路径映射测试"""
        src_dir, files = sample_files
        json_path = tmp_path / "mapped.json"
        manifest_path = tmp_path / "mapped.manifest"
        
        entries = [{"path": f"/virtual/{name}"} for name in files.keys()]
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "entries": entries
            }, f)
        
        result = ManifestJsonConverter.json_to_manifest(
            str(json_path),
            str(manifest_path),
            local_base_path=str(tmp_path),
            path_mappings={"/virtual": str(src_dir)}
        )
        
        assert result.success_count == len(files)


class TestManifestJsonRoundtrip:
    """Manifest ↔ JSON 往返测试"""
    
    def test_roundtrip_preserves_data(self, tmp_path, sample_files):
        """往返转换应保持数据一致"""
        src_dir, files = sample_files
        
        manifest1_path = tmp_path / "original.manifest"
        json_path = tmp_path / "intermediate.json"
        manifest2_path = tmp_path / "restored.manifest"
        
        # 创建原始 Manifest
        builder = ManifestBuilder(str(manifest1_path), checksum_hook=MD5Hook())
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 转换为 JSON
        ManifestJsonConverter.manifest_to_json(str(manifest1_path), str(json_path))
        
        # 转换回 Manifest
        ManifestJsonConverter.json_to_manifest(
            str(json_path),
            str(manifest2_path),
            local_base_path=str(tmp_path),
            path_mappings={"assets": str(src_dir)}
        )
        
        # 比较
        with ManifestReader(str(manifest1_path), checksum_hook=MD5Hook()) as reader1:
            with ManifestReader(str(manifest2_path), checksum_hook=MD5Hook()) as reader2:
                assert reader1.entry_count == reader2.entry_count
                
                paths1 = sorted(reader1.list_all())
                paths2 = sorted(reader2.list_all())
                assert paths1 == paths2


# ==================== Archive ↔ Manifest 转换测试 ====================

class TestArchiveToManifest:
    """Archive 转 Manifest 测试"""
    
    def test_basic_conversion(self, tmp_path, sample_files):
        """基础转换"""
        src_dir, files = sample_files
        archive_path = tmp_path / "source.archive"
        manifest_path = tmp_path / "output.manifest"
        
        # 创建 Archive
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        builder.add_dir(str(src_dir), "/assets", algo_id=1)
        builder.build()
        
        # 转换为 Manifest
        result = ModeConverter.archive_to_manifest(
            str(archive_path),
            str(manifest_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        
        assert result.success_count == len(files)
        
        # 验证 Manifest
        with ManifestReader(str(manifest_path), checksum_hook=MD5Hook()) as reader:
            assert reader.entry_count == len(files)
            for name, content in files.items():
                entry = reader.get_entry(f"/assets/{name}")
                assert entry.raw_size == len(content)


class TestManifestToArchive:
    """Manifest 转 Archive 测试"""
    
    def test_basic_conversion(self, tmp_path, sample_files):
        """基础转换"""
        src_dir, files = sample_files
        manifest_path = tmp_path / "source.manifest"
        archive_path = tmp_path / "output.archive"
        
        # 创建 Manifest
        builder = ManifestBuilder(str(manifest_path), checksum_hook=MD5Hook())
        builder.add_dir(str(src_dir), "/assets")
        builder.build()
        
        # 转换为 Archive
        result = ModeConverter.manifest_to_archive(
            str(manifest_path),
            str(archive_path),
            local_base_path=str(tmp_path),
            path_mappings={"assets": str(src_dir)},
            checksum_hook_read=MD5Hook(),
            compression_hooks=[ZlibHook()],
            default_algo_id=1,
            output_checksum_hook=MD5Hook()
        )
        
        assert result.success_count == len(files)
        
        # 验证 Archive
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        ) as reader:
            assert reader.entry_count == len(files)
            for name, expected in files.items():
                data = reader.read(f"/assets/{name}")
                assert data == expected


# ==================== 三方互转测试 ====================

class TestFullConversionChain:
    """完整转换链测试"""
    
    def test_archive_to_manifest_to_json(self, tmp_path, sample_files):
        """Archive → Manifest → JSON"""
        src_dir, files = sample_files
        
        archive_path = tmp_path / "step1.archive"
        manifest_path = tmp_path / "step2.manifest"
        json_path = tmp_path / "step3.json"
        
        # Step 1: 创建 Archive
        builder = ArchiveBuilder(
            str(archive_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        builder.add_dir(str(src_dir), "/data", algo_id=1)
        builder.build()
        
        # Step 2: Archive → Manifest
        ModeConverter.archive_to_manifest(
            str(archive_path),
            str(manifest_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        
        # Step 3: Manifest → JSON
        ManifestJsonConverter.manifest_to_json(str(manifest_path), str(json_path))
        
        # 验证最终 JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["entry_count"] == len(files)
    
    def test_json_to_manifest_to_archive(self, tmp_path, sample_files):
        """JSON → Manifest → Archive"""
        src_dir, files = sample_files
        
        json_path = tmp_path / "step1.json"
        manifest_path = tmp_path / "step2.manifest"
        archive_path = tmp_path / "step3.archive"
        
        # Step 1: 创建 JSON (路径格式无前导斜杠)
        entries = [{"path": f"files/{name}"} for name in files.keys()]
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 2,
                "entries": entries
            }, f)
        
        # Step 2: JSON → Manifest
        ManifestJsonConverter.json_to_manifest(
            str(json_path),
            str(manifest_path),
            local_base_path=str(tmp_path),
            path_mappings={"files": str(src_dir)}
        )
        
        # Step 3: Manifest → Archive
        ModeConverter.manifest_to_archive(
            str(manifest_path),
            str(archive_path),
            local_base_path=str(tmp_path),
            path_mappings={"files": str(src_dir)},
            checksum_hook_read=MD5Hook(),
            compression_hooks=[ZlibHook()],
            default_algo_id=1
        )
        
        # 验证最终 Archive
        with ArchiveReader(
            str(archive_path),
            compression_hooks=[ZlibHook()]
        ) as reader:
            assert reader.entry_count == len(files)
            for name, expected in files.items():
                data = reader.read(f"/files/{name}")
                assert data == expected
    
    def test_full_roundtrip(self, tmp_path, sample_files):
        """完整往返: Archive → Manifest → JSON → Manifest → Archive"""
        src_dir, files = sample_files
        
        # 路径设置
        archive1_path = tmp_path / "original.archive"
        manifest1_path = tmp_path / "step1.manifest"
        json_path = tmp_path / "step2.json"
        manifest2_path = tmp_path / "step3.manifest"
        archive2_path = tmp_path / "final.archive"
        
        # 原始 Archive
        builder = ArchiveBuilder(
            str(archive1_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        builder.add_dir(str(src_dir), "/data", algo_id=1)
        builder.build()
        
        # Archive → Manifest
        ModeConverter.archive_to_manifest(
            str(archive1_path),
            str(manifest1_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        )
        
        # Manifest → JSON
        ManifestJsonConverter.manifest_to_json(str(manifest1_path), str(json_path))
        
        # JSON → Manifest
        ManifestJsonConverter.json_to_manifest(
            str(json_path),
            str(manifest2_path),
            local_base_path=str(tmp_path),
            path_mappings={"data": str(src_dir)}
        )
        
        # Manifest → Archive
        ModeConverter.manifest_to_archive(
            str(manifest2_path),
            str(archive2_path),
            local_base_path=str(tmp_path),
            path_mappings={"data": str(src_dir)},
            checksum_hook_read=MD5Hook(),
            compression_hooks=[ZlibHook()],
            default_algo_id=1,
            output_checksum_hook=MD5Hook()
        )
        
        # 比较原始和最终 Archive 的内容
        with ArchiveReader(
            str(archive1_path),
            compression_hooks=[ZlibHook()],
            checksum_hook=MD5Hook()
        ) as reader1:
            with ArchiveReader(
                str(archive2_path),
                compression_hooks=[ZlibHook()],
                checksum_hook=MD5Hook()
            ) as reader2:
                assert reader1.entry_count == reader2.entry_count
                
                for name, expected in files.items():
                    data1 = reader1.read(f"/data/{name}")
                    data2 = reader2.read(f"/data/{name}")
                    assert data1 == data2 == expected


# ==================== 清单合并测试 ====================


class TestMergeManifests:
    """清单合并测试"""
    
    def test_merge_two_json_manifests(self, tmp_path, sample_files):
        """合并两个 JSON 清单"""
        src_dir, files = sample_files
        
        # 创建两个 JSON 清单
        json1_path = tmp_path / "manifest1.json"
        json2_path = tmp_path / "manifest2.json"
        merged_path = tmp_path / "merged.json"
        
        files_list = list(files.keys())
        half = len(files_list) // 2
        
        # 第一个清单包含前半部分文件
        entries1 = [{"path": f"part1/{name}", "size": len(files[name])} for name in files_list[:half]]
        with open(json1_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 2,
                "index_flags": 0,
                "entries": entries1
            }, f)
        
        # 第二个清单包含后半部分文件
        entries2 = [{"path": f"part2/{name}", "size": len(files[name])} for name in files_list[half:]]
        with open(json2_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 2,
                "index_flags": 0,
                "entries": entries2
            }, f)
        
        # 合并
        result = merge_manifests(
            [str(json1_path), str(json2_path)],
            str(merged_path),
            output_format="json"
        )
        
        assert result.source_count == 2
        assert result.total_entries == len(files)
        assert result.duplicate_count == 0
        
        # 验证合并结果
        with open(merged_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["entry_count"] == len(files)
        assert len(data["entries"]) == len(files)
    
    def test_merge_json_and_binary(self, tmp_path, sample_files):
        """合并 JSON 和二进制清单"""
        src_dir, files = sample_files
        
        files_list = list(files.keys())
        half = len(files_list) // 2
        
        # 创建二进制清单 (前半部分)
        binary_path = tmp_path / "manifest.grim"
        builder = ManifestBuilder(str(binary_path), checksum_hook=MD5Hook())
        for name in files_list[:half]:
            builder.add_file(str(src_dir / name), f"/binary/{name}")
        builder.build()
        
        # 创建 JSON 清单 (后半部分)
        json_path = tmp_path / "manifest.json"
        entries = [{"path": f"json/{name}", "size": len(files[name])} for name in files_list[half:]]
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 2,  # MD5
                "index_flags": 0,
                "entries": entries
            }, f)
        
        # 合并
        merged_path = tmp_path / "merged.json"
        result = merge_manifests(
            [str(binary_path), str(json_path)],
            str(merged_path),
            output_format="json"
        )
        
        assert result.source_count == 2
        assert result.total_entries == len(files)
    
    def test_merge_conflict_error(self, tmp_path):
        """路径冲突应抛出异常 (on_conflict='error')"""
        json1_path = tmp_path / "m1.json"
        json2_path = tmp_path / "m2.json"
        
        # 两个清单包含相同路径
        for path in [json1_path, json2_path]:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({
                    "version": 2,
                    "checksum_algo": 0,
                    "entries": [{"path": "shared/file.txt"}]
                }, f)
        
        with pytest.raises(PathConflictError) as exc_info:
            merge_manifests(
                [str(json1_path), str(json2_path)],
                str(tmp_path / "merged.json"),
                on_conflict="error"
            )
        
        assert "shared/file.txt" in str(exc_info.value)
    
    def test_merge_conflict_keep_first(self, tmp_path):
        """路径冲突保留第一个 (on_conflict='keep_first')"""
        json1_path = tmp_path / "m1.json"
        json2_path = tmp_path / "m2.json"
        merged_path = tmp_path / "merged.json"
        
        with open(json1_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 0,
                "entries": [{"path": "shared/file.txt", "size": 100}]
            }, f)
        
        with open(json2_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 0,
                "entries": [{"path": "shared/file.txt", "size": 200}]
            }, f)
        
        result = merge_manifests(
            [str(json1_path), str(json2_path)],
            str(merged_path),
            on_conflict="keep_first"
        )
        
        assert result.duplicate_count == 1
        assert result.total_entries == 1
        
        with open(merged_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 应保留第一个 (size=100)
        assert data["entries"][0]["size"] == 100
    
    def test_merge_conflict_keep_last(self, tmp_path):
        """路径冲突保留最后一个 (on_conflict='keep_last')"""
        json1_path = tmp_path / "m1.json"
        json2_path = tmp_path / "m2.json"
        merged_path = tmp_path / "merged.json"
        
        with open(json1_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 0,
                "entries": [{"path": "shared/file.txt", "size": 100}]
            }, f)
        
        with open(json2_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "checksum_algo": 0,
                "entries": [{"path": "shared/file.txt", "size": 200}]
            }, f)
        
        result = merge_manifests(
            [str(json1_path), str(json2_path)],
            str(merged_path),
            on_conflict="keep_last"
        )
        
        assert result.duplicate_count == 1
        
        with open(merged_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 应保留最后一个 (size=200)
        assert data["entries"][0]["size"] == 200
    
    def test_merge_version_mismatch_error(self, tmp_path):
        """版本不匹配应抛出异常"""
        json1_path = tmp_path / "v2.json"
        json2_path = tmp_path / "v3.json"
        
        with open(json1_path, 'w', encoding='utf-8') as f:
            json.dump({"version": 2, "checksum_algo": 0, "entries": []}, f)
        
        with open(json2_path, 'w', encoding='utf-8') as f:
            json.dump({"version": 3, "checksum_algo": 0, "entries": []}, f)
        
        with pytest.raises(ManifestVersionMismatchError):
            merge_manifests(
                [str(json1_path), str(json2_path)],
                str(tmp_path / "merged.json")
            )
    
    def test_merge_algorithm_mismatch_error(self, tmp_path):
        """算法不匹配应抛出异常"""
        json1_path = tmp_path / "md5.json"
        json2_path = tmp_path / "sha256.json"
        
        with open(json1_path, 'w', encoding='utf-8') as f:
            json.dump({"version": 2, "checksum_algo": 2, "entries": []}, f)  # MD5
        
        with open(json2_path, 'w', encoding='utf-8') as f:
            json.dump({"version": 2, "checksum_algo": 4, "entries": []}, f)  # SHA256
        
        with pytest.raises(ManifestAlgorithmMismatchError):
            merge_manifests(
                [str(json1_path), str(json2_path)],
                str(tmp_path / "merged.json")
            )
    
    def test_merge_output_json(self, tmp_path):
        """输出为 JSON 格式"""
        json_path = tmp_path / "source.json"
        merged_path = tmp_path / "merged.json"
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                "version": 2,
                "magic": "TEST",
                "checksum_algo": 0,
                "entries": [{"path": "test.txt"}]
            }, f)
        
        result = merge_manifests(
            [str(json_path)],
            str(merged_path),
            output_format="json"
        )
        
        assert result.total_entries == 1
        assert merged_path.exists()
        
        with open(merged_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data["magic"] == "TEST"
    
    def test_merge_empty_sources(self, tmp_path):
        """空源列表应返回空结果"""
        result = merge_manifests(
            [],
            str(tmp_path / "merged.json")
        )
        
        assert result.total_entries == 0
        assert result.source_count == 0
