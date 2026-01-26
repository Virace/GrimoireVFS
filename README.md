# GrimoireVFS

[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](https://github.com/Virace/GrimoireVFS)

轻量级零依赖 Python 二进制资源管理库。

## ✨ 特性

- **零依赖**: 仅使用 Python 标准库 (3.7+)
- **双模式**: Manifest (清单校验) / Archive (资源打包)
- **高性能**: mmap 读取、批量操作、rclone 加速
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

### Manifest 模式 (清单校验) - 推荐使用 rclone

```python
from grimoire import ManifestBuilder, ManifestReader, RcloneHashHook
from grimoire.hooks import ZlibCompressHook

# 创建清单 (使用 rclone quickxor，性能最优)
builder = ManifestBuilder(
    "game.manifest",
    checksum_hook=RcloneHashHook("quickxor"),  # 或 sha256, md5, blake3...
    index_crypto=ZlibCompressHook()  # 压缩索引区
)

# 批量添加 (使用 rclone 批量计算，1000+ 文件仅需 10 秒)
result = builder.add_dir_batch_rclone("./assets", "game/assets")
print(f"成功: {result.success_count}, 耗时: {result.elapsed_time:.1f}s")
builder.build()

# 校验文件
with ManifestReader("game.manifest", 
    checksum_hook=RcloneHashHook("quickxor"),
    index_crypto=ZlibCompressHook()
) as reader:
    is_valid = reader.verify_file("game/assets/hero.png", "./assets/hero.png")

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

# Manifest 转 JSON (支持 rclone hook)
ManifestJsonConverter.manifest_to_json("game.manifest", "game.json")

# JSON 转 Manifest
ManifestJsonConverter.json_to_manifest("game.json", "new.manifest", "./local")

# Archive 转 Manifest
ModeConverter.archive_to_manifest("game.pak", "game.manifest")
```

## 🔧 校验算法

### 内置 (纯 Python)

| Hook | 输出大小 | 说明 |
|------|---------|------|
| `CRC32Hook` | 4 bytes | 快速校验 |
| `MD5Hook` | 16 bytes | 通用校验 |
| `SHA1Hook` | 20 bytes | Git 使用 |
| `SHA256Hook` | 32 bytes | 强校验 |

### RcloneHashHook (推荐，需安装 [rclone](https://rclone.org/))

| 算法 | 输出大小 | 说明 |
|------|---------|------|
| `quickxor` | 20 bytes | OneDrive，速度最快 |
| `md5` / `sha256` | 16/32 bytes | 标准算法 |
| `blake3` | 32 bytes | 现代快速哈希 |
| `xxh3` / `xxh128` | 8/16 bytes | 极速非加密哈希 |

```python
from grimoire import RcloneHashHook

# 支持 13 种算法
hook = RcloneHashHook("quickxor")  # 或 md5, sha256, blake3, xxh3...
```

## 📖 文档

详细文档请参阅 [用户指南](docs/user_guide.md)。

## 🤖 致谢

本项目大部分代码由 [Claude Opus 4](https://www.anthropic.com/claude) (Anthropic) 辅助生成，Virace 负责需求设计、架构决策和代码审查。

## 📄 许可证

MIT License
