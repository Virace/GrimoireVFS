# GrimoireVFS

轻量级零依赖 Python 二进制资源管理库。

## ✨ 特性

- **零依赖**: 仅使用 Python 标准库
- **双模式**: Manifest (清单校验) / Archive (资源打包)
- **高性能**: mmap 读取、批量操作、进度回调
- **安全**: 索引加密、路径 Hash、校验算法可配置

## 📦 安装
**当前不可用**
```bash
pip install grimoire-vfs
```

## 🚀 快速开始

### Manifest 模式 (清单校验)

```python
from grimoire import ManifestBuilder, ManifestReader, MD5Hook

# 创建清单
builder = ManifestBuilder("game.manifest", checksum_hook=MD5Hook())
builder.add_dir("./assets", "/game/assets")
builder.build()

# 校验文件
with ManifestReader("game.manifest", checksum_hook=MD5Hook()) as reader:
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
builder.add_dir("./assets", "/game", algo_id=1)
builder.build()

# 读取
with ArchiveReader("game.pak", compression_hooks=[ZlibHook()]) as reader:
    data = reader.read("/game/hero.png")
```

### 批量操作 (带进度)

```python
def on_progress(info):
    print(f"{info.progress:.1%} - {info.current_file}")

# 批量打包
result = builder.add_dir_batch(
    "./assets", "/game",
    progress_callback=on_progress,
    on_error='skip'
)
print(f"成功: {result.success_count}, 失败: {result.failed_count}")

# 批量解包
result = reader.extract_all("./output", progress_callback=on_progress)
```

## 🔧 内置校验算法

| Hook | 输出大小 | 说明 |
|------|---------|------|
| `CRC32Hook` | 4 bytes | 快速校验 |
| `MD5Hook` | 16 bytes | 通用校验 |
| `SHA1Hook` | 20 bytes | Git 使用 |
| `SHA256Hook` | 32 bytes | 强校验 |
| `QuickXorHashHook` | 20 bytes | OneDrive 快速哈希 |

## 📖 文档

详细文档请参阅 [用户指南](docs/user_guide.md)。

## 📄 许可证

MIT License
