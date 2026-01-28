# GrimoireVFS

[![PyPI Version](https://img.shields.io/pypi/v/grimoirevfs?label=PyPI&logo=pypi&logoColor=white)](https://pypi.org/project/grimoirevfs/)
[![Python Version](https://img.shields.io/pypi/pyversions/grimoirevfs?logo=python&logoColor=white)](https://pypi.org/project/grimoirevfs/)
[![CI](https://github.com/Virace/GrimoireVFS/actions/workflows/ci.yml/badge.svg)](https://github.com/Virace/GrimoireVFS/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/Virace/GrimoireVFS)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/grimoirevfs?label=Downloads&logo=pypi&logoColor=white)](https://pypi.org/project/grimoirevfs/)

轻量级零依赖 Python 二进制资源管理库。

## ✨ 特性

- **零依赖**: 仅使用 Python 标准库 (3.7+)
- **双模式**: Manifest (清单校验) / Archive (资源打包)
- **高性能**: mmap 读取、批量操作、fhash/rclone 加速
- **安全**: 索引加密、路径 Hash、校验算法可配置

## 📦 安装

```bash
pip install grimoirevfs
```

或从源码安装:

```bash
git clone https://github.com/Virace/GrimoireVFS.git
cd GrimoireVFS
pip install .
```

## 🚀 快速开始

### Manifest 模式 (清单校验) - 推荐使用 fhash

```python
from grimoire import ManifestBuilder, ManifestReader, FhashHook
from grimoire.hooks import ZlibCompressHook

# 创建清单 (使用 fhash quickxor，性能最优)
builder = ManifestBuilder(
    "game.manifest",
    checksum_hook=FhashHook("quickxor"),  # 或 sha256, md5, blake3...
    index_crypto=ZlibCompressHook()  # 压缩索引区
)

# 添加文件
builder.add_dir("./assets", "/game/assets")
builder.build()

# 校验文件
with ManifestReader("game.manifest", 
    checksum_hook=FhashHook("quickxor"),
    index_crypto=ZlibCompressHook()
) as reader:
    is_valid = reader.verify_file("/game/assets/hero.png", "./assets/hero.png")
```

### Archive 模式 (资源打包)

```python
from grimoire import ArchiveBuilder, ArchiveReader, MD5Hook
import zlib

# 自定义压缩 Hook
class ZlibHook:
    @property
    def algo_id(self): return 1
    def compress(self, data): return zlib.compress(data)
    def decompress(self, data, size): return zlib.decompress(data)

# 打包
builder = ArchiveBuilder("game.pak", compression_hooks=[ZlibHook()])
builder.add_dir("./assets", "game", algo_id=1)
builder.build()

# 读取
with ArchiveReader("game.pak", compression_hooks=[ZlibHook()]) as reader:
    data = reader.read("game/hero.png")
```

### 格式转换

```python
from grimoire import ManifestJsonConverter, ModeConverter

# Manifest 转 JSON
ManifestJsonConverter.manifest_to_json("game.manifest", "game.json")

# JSON 转 Manifest
ManifestJsonConverter.json_to_manifest("game.json", "new.manifest", "./local")

# Archive 转 Manifest
ModeConverter.archive_to_manifest("game.pak", "game.manifest")
```

## 🔧 校验算法

### 内置 (纯 Python)

| Hook | algo_id | 输出大小 | 说明 |
|------|---------|---------|------|
| `NoneChecksumHook` | 0 | 0 | 不校验 |
| `CRC32Hook` | 1 | 4 bytes | 快速校验 |
| `MD5Hook` | 2 | 16 bytes | 通用校验 |
| `SHA1Hook` | 3 | 20 bytes | Git 使用 |
| `SHA256Hook` | 4 | 32 bytes | 强校验 |

### FhashHook ⭐ 推荐 (需安装 [fhash](https://github.com/Virace/fast-hasher))

高性能外置工具，支持批量文件处理和多种算法。

| 算法 | algo_id | 输出大小 | 说明 |
|------|---------|---------|------|
| `quickxor` | 9 | 20 bytes | OneDrive，速度最快 |
| `blake3` | 6 | 32 bytes | 现代快速哈希 |
| `xxh3` / `xxh128` | 7/8 | 8/16 bytes | 极速非加密哈希 |
| `md5` / `sha256` | 2/4 | 16/32 bytes | 标准算法 |

```python
from grimoire import FhashHook

# 创建 hook
hook = FhashHook("quickxor")

# 单文件计算
hash_bytes = hook.compute_file("/path/to/file")

# 批量计算 (性能最佳)
results = hook.compute_files_batch(["/path/to/file1", "/path/to/file2"])
```

### RcloneHashHook (备选，需安装 [rclone](https://rclone.org/))

```python
from grimoire import RcloneHashHook

# 与 FhashHook 兼容的 API
hook = RcloneHashHook("sha256")
```

### 外置工具发现

外置工具按以下优先级自动发现:

1. 环境变量 (`GRIMOIRE_FHASH_PATH`, `GRIMOIRE_RCLONE_PATH`)
2. 系统 PATH
3. 库 `vendor/bin/` 目录
4. 用户目录 `~/.grimoire/bin/`

## 📖 文档

详细文档请参阅 [用户指南](docs/user_guide.md)。

## 🤖 致谢

本项目大部分代码由 [Claude Opus 4](https://www.anthropic.com/claude) (Anthropic) 辅助生成，Virace 负责需求设计、架构决策和代码审查。

## 📄 许可证

MIT License
