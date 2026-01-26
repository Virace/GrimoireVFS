# GrimoireVFS 用户指南

## 目录

1. [概述](#概述)
2. [安装](#安装)
3. [核心概念](#核心概念)
4. [Manifest 模式](#manifest-模式)
5. [Archive 模式](#archive-模式)
6. [Hook 系统](#hook-系统)
7. [批量操作](#批量操作)
8. [高级用法](#高级用法)
9. [API 参考](#api-参考)
10. [常见问题](#常见问题)

---

## 概述

GrimoireVFS 是一个轻量级、零依赖的 Python 二进制资源管理库，专为游戏资源打包、文件校验和虚拟文件系统设计。

### 核心特性

| 特性 | 描述 |
|------|------|
| **零依赖** | 仅使用 Python 标准库 (`struct`, `io`, `hashlib`, `mmap`) |
| **双模式** | Manifest (清单校验) 和 Archive (资源打包) |
| **高性能** | mmap 内存映射、批量操作、进度回调 |
| **安全性** | 索引加密、路径 Hash、可配置校验算法 |
| **可扩展** | Hook 系统支持自定义压缩、校验、加密算法 |

### 适用场景

- 游戏资源打包和分发
- 文件完整性校验
- 资源热更新系统
- 虚拟文件系统实现

---

## 安装

### PyPI 安装

```bash
pip install grimoire-vfs
```

### 从源码安装

```bash
git clone https://github.com/virace/grimoire-vfs.git
cd grimoire-vfs
pip install -e .
```

### 依赖要求

- Python 3.9+
- 无第三方依赖

---

## 核心概念

### 双模式架构

```
┌─────────────────────────────────────────────────────────┐
│                     GrimoireVFS                         │
├──────────────────────────┬──────────────────────────────┤
│     Manifest 模式        │       Archive 模式           │
├──────────────────────────┼──────────────────────────────┤
│ • 仅记录文件元信息       │ • 包含完整文件数据           │
│ • 用于校验本地文件       │ • 用于资源打包分发           │
│ • 文件体积小             │ • 支持压缩存储               │
│ • 类似 .manifest 清单    │ • 类似 .pak/.zip 归档       │
└──────────────────────────┴──────────────────────────────┘
```

### 文件结构

```
┌──────────────┐
│  FileHeader  │  固定 48 字节
├──────────────┤
│  IndexHeader │  固定 24 字节
├──────────────┤
│ StringTables │  可变长度 (可加密)
├──────────────┤
│  EntryTable  │  每条目固定大小
├──────────────┤
│  DataHeader  │  仅 Archive 模式
├──────────────┤
│  Data Block  │  仅 Archive 模式
└──────────────┘
```

### 三级路径字典

路径 `/game/assets/hero.png` 被拆分为：
- **目录**: `/game/assets` → dir_id
- **文件名**: `hero` → name_id
- **扩展名**: `.png` → ext_id

这种设计：
- 节省存储空间 (相同目录/扩展名只存一次)
- 支持索引加密时隐藏文件名
- 便于按目录/类型遍历

---

## Manifest 模式

### 创建清单

```python
from grimoire import ManifestBuilder, MD5Hook

# 基础用法
builder = ManifestBuilder("output.manifest")
builder.add_file("./hero.png", "/game/hero.png")
builder.add_dir("./assets", "/game/assets")
builder.build()

# 带校验
builder = ManifestBuilder(
    "output.manifest",
    checksum_hook=MD5Hook()  # 可选: CRC32Hook, SHA1Hook, SHA256Hook
)
```

### 读取清单

```python
from grimoire import ManifestReader, MD5Hook

with ManifestReader("output.manifest", checksum_hook=MD5Hook()) as reader:
    # 检查文件存在
    if reader.exists("/game/hero.png"):
        print("文件存在")
    
    # 获取文件信息
    entry = reader.get_entry("/game/hero.png")
    print(f"大小: {entry.raw_size}, 校验: {entry.checksum.hex()}")
    
    # 校验本地文件
    is_valid = reader.verify_file("/game/hero.png", "./hero.png")
    
    # 列出所有文件
    for path in reader.list_all():
        print(path)
```

---

## Archive 模式

### 创建归档

```python
from grimoire import ArchiveBuilder, MD5Hook
import zlib

# 自定义压缩 Hook
class ZlibHook:
    @property
    def algo_id(self) -> int:
        return 1  # 必须唯一标识
    
    def compress(self, data: bytes) -> bytes:
        return zlib.compress(data, level=6)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return zlib.decompress(data)

# 创建归档
builder = ArchiveBuilder(
    "game.pak",
    compression_hooks=[ZlibHook()],
    checksum_hook=MD5Hook()
)

# 添加文件 (algo_id=0 不压缩, algo_id=1 使用 ZlibHook)
builder.add_file("./hero.png", "/game/hero.png", algo_id=1)
builder.add_dir("./assets", "/game/assets", algo_id=1)
builder.build()

# 查看压缩统计
print(builder.compression_stats)
# {'total_raw': 1000000, 'total_packed': 150000, 'ratio': 0.15}
```

### 读取归档

```python
from grimoire import ArchiveReader

with ArchiveReader(
    "game.pak",
    compression_hooks=[ZlibHook()],
    checksum_hook=MD5Hook()
) as reader:
    # 读取文件内容
    data = reader.read("/game/hero.png")
    
    # 以文件对象方式打开
    with reader.open("/game/config.json") as f:
        config = json.load(f)
    
    # 检查 mmap 状态
    print(f"使用 mmap: {reader.is_mmap}")
    
    # 批量读取
    files = reader.read_batch(["/game/a.png", "/game/b.png"])
```

---

## Hook 系统

### 内置 Hook (纯 Python)

| Hook | 用途 | algo_id | 输出大小 |
|------|------|---------|---------|
| `NoneChecksumHook` | 不校验 | 0 | 0 |
| `CRC32Hook` | CRC32 校验 | 1 | 4 |
| `MD5Hook` | MD5 校验 | 2 | 16 |
| `SHA1Hook` | SHA1 校验 | 3 | 20 |
| `SHA256Hook` | SHA256 校验 | 4 | 32 |

### RcloneHashHook (推荐)

通过调用 [rclone](https://rclone.org/) 计算哈希，性能远超纯 Python 实现。

支持 13 种算法: `md5`, `sha1`, `sha256`, `sha512`, `crc32`, `blake3`, `xxh3`, `xxh128`, `quickxor`, `dropbox`, `whirlpool`, `hidrive`, `mailru`

```python
from grimoire import RcloneHashHook

# 创建 hook (algo_id 自动分配 101-113)
hook = RcloneHashHook("quickxor")  # OneDrive 专用，速度最快
hook = RcloneHashHook("blake3")     # 现代快速哈希
hook = RcloneHashHook("xxh3")       # 极速非加密哈希

# 单文件计算 (推荐)
hash_bytes = hook.compute_file("/path/to/file")

# 批量目录计算
hash_map = hook.compute_dir("/path/to/dir", recursive=True)

# 内存数据计算 (会写临时文件，较慢)
hash_bytes = hook.compute(data)
```

### 高性能批量操作

使用 `add_dir_batch_rclone` 可一次性计算整个目录:

```python
from grimoire import ManifestBuilder, RcloneHashHook

builder = ManifestBuilder("game.manifest", checksum_hook=RcloneHashHook("quickxor"))

# ⚡ 1000+ 文件仅需 10 秒 (vs 普通方法 6 分钟)
result = builder.add_dir_batch_rclone("./assets", "/game")
```

### 索引压缩 Hook

| Hook | 用途 |
|------|------|
| `ZlibCompressHook` | zlib 压缩索引区 |
| `XorObfuscateHook` | 简单 XOR 混淆 |
| `ZlibXorHook` | 先压缩后混淆 |

### 自定义压缩 Hook

```python
from grimoire.hooks.base import CompressionHook
import lz4.frame  # 需要安装 lz4

class LZ4Hook(CompressionHook):
    @property
    def algo_id(self) -> int:
        return 2  # 自定义 ID
    
    def compress(self, data: bytes) -> bytes:
        return lz4.frame.compress(data)
    
    def decompress(self, data: bytes, raw_size: int) -> bytes:
        return lz4.frame.decompress(data)
```

### 自定义索引加密 Hook

```python
from grimoire.hooks.base import IndexCryptoHook
from cryptography.fernet import Fernet  # 需要安装 cryptography

class FernetCryptoHook(IndexCryptoHook):
    def __init__(self, key: bytes):
        self._fernet = Fernet(key)
    
    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)
    
    def decrypt(self, data: bytes) -> bytes:
        return self._fernet.decrypt(data)

# 使用
key = Fernet.generate_key()
builder = ArchiveBuilder("secure.pak", index_crypto=FernetCryptoHook(key))
```

---

## 批量操作

### 批量添加 (带进度)

```python
from grimoire import ArchiveBuilder
from grimoire.core import FileItem, ProgressInfo

def on_progress(info: ProgressInfo):
    print(f"[{info.progress:.1%}] {info.current}/{info.total} - {info.current_file}")
    print(f"  速度: {info.rate / 1024 / 1024:.2f} MB/s, 剩余: {info.eta:.1f}s")

builder = ArchiveBuilder("output.pak")

# 方式 1: 使用 add_dir_batch
result = builder.add_dir_batch(
    local_dir="./assets",
    mount_point="/game",
    algo_id=1,
    recursive=True,
    exclude_patterns=["*.tmp", "*.bak"],  # 排除模式
    on_error='skip',  # 'raise', 'skip', 'abort'
    progress_callback=on_progress
)

# 方式 2: 使用 FileItem 列表
items = [
    FileItem("./hero.png", "/game/hero.png", algo_id=1),
    FileItem("./config.json", "/game/config.json", algo_id=0),
]
result = builder.add_files_batch(items, on_error='skip', progress_callback=on_progress)

# 检查结果
print(f"成功: {result.success_count}")
print(f"失败: {result.failed_count}")
print(f"失败文件: {result.failed_files}")
print(f"总字节: {result.total_bytes}")
print(f"耗时: {result.elapsed_time:.2f}s")
```

### 批量解包

```python
from grimoire import ArchiveReader

with ArchiveReader("game.pak") as reader:
    result = reader.extract_all(
        output_dir="./extracted",
        verify=True,
        on_error='skip',
        progress_callback=on_progress
    )
    
    print(f"解包完成: {result.success_count} 个文件")
```

---

## 高级用法

### 自定义路径 Hash 函数

```python
import xxhash  # 需要安装 xxhash

def xxhash_path(path: str) -> int:
    return xxhash.xxh64(path.encode('utf-8')).intdigest()

builder = ArchiveBuilder("output.pak", path_hash_func=xxhash_path)
```

### 自定义魔法数

```python
builder = ArchiveBuilder("game.pak", magic=b'GAME')
```

### 处理加密索引

```python
# 创建加密归档
builder = ArchiveBuilder("secure.pak", index_crypto=my_crypto_hook)
builder.add_dir("./assets", "/game")
builder.build()

# 读取加密归档 (不解密)
with ArchiveReader("secure.pak") as reader:
    print(f"索引已解密: {reader.is_decrypted}")  # False
    
    # 仍可通过 Hash 读取 (如果知道路径)
    data = reader.read("/game/hero.png")  # 可以工作
    
    # 但无法遍历
    reader.list_all()  # 抛出 IndexNotDecryptedError

# 读取加密归档 (解密)
with ArchiveReader("secure.pak", index_crypto=my_crypto_hook) as reader:
    print(f"索引已解密: {reader.is_decrypted}")  # True
    print(reader.list_all())  # 可以工作
```

---

## API 参考

### ManifestBuilder

```python
ManifestBuilder(
    output_path: str,
    magic: bytes = b'GRIM',
    checksum_hook: Optional[ChecksumHook] = None,
    index_crypto: Optional[IndexCryptoHook] = None,
    path_hash_func: Optional[Callable[[str], int]] = None
)
```

| 方法 | 描述 |
|------|------|
| `add_file(local_path, vfs_path)` | 添加单个文件 |
| `add_dir(local_dir, mount_point)` | 添加目录 |
| `build()` | 构建并写入文件 |

### ManifestReader

```python
ManifestReader(
    file_path: str,
    checksum_hook: Optional[ChecksumHook] = None,
    index_crypto: Optional[IndexCryptoHook] = None,
    path_hash_func: Optional[Callable[[str], int]] = None
)
```

| 方法 | 描述 |
|------|------|
| `exists(vfs_path)` | 检查路径是否存在 |
| `get_entry(vfs_path)` | 获取条目信息 |
| `verify_file(vfs_path, local_path)` | 校验本地文件 |
| `list_all()` | 列出所有路径 |

### ArchiveBuilder

```python
ArchiveBuilder(
    output_path: str,
    magic: bytes = b'GRIM',
    compression_hooks: Optional[List[CompressionHook]] = None,
    checksum_hook: Optional[ChecksumHook] = None,
    index_crypto: Optional[IndexCryptoHook] = None,
    path_hash_func: Optional[Callable[[str], int]] = None
)
```

| 方法 | 描述 |
|------|------|
| `add_file(local_path, vfs_path, algo_id)` | 添加单个文件 |
| `add_dir(local_dir, mount_point, algo_id)` | 添加目录 |
| `add_files_batch(items, on_error, progress_callback)` | 批量添加 |
| `add_dir_batch(...)` | 批量添加目录 |
| `build()` | 构建并写入文件 |

### ArchiveReader

```python
ArchiveReader(
    file_path: str,
    compression_hooks: Optional[List[CompressionHook]] = None,
    checksum_hook: Optional[ChecksumHook] = None,
    index_crypto: Optional[IndexCryptoHook] = None,
    path_hash_func: Optional[Callable[[str], int]] = None,
    use_mmap: bool = True
)
```

| 方法 | 描述 |
|------|------|
| `exists(vfs_path)` | 检查路径是否存在 |
| `read(vfs_path, verify)` | 读取文件内容 |
| `open(vfs_path, verify)` | 返回 BytesIO 对象 |
| `get_entry(vfs_path)` | 获取条目信息 |
| `list_all()` | 列出所有路径 |
| `read_batch(vfs_paths, verify, on_error)` | 批量读取 |
| `extract_all(output_dir, ...)` | 解包所有文件 |

---

## 常见问题

### Q: 如何选择 Manifest 还是 Archive 模式？

- **Manifest**: 文件已在本地，只需校验完整性 (如热更新检查)
- **Archive**: 需要将文件打包分发 (如游戏资源包)

### Q: 为什么遍历报 IndexNotDecryptedError？

索引已加密但未提供解密器。解决方法：
1. 提供匹配的 `IndexCryptoHook`
2. 或使用 `list_hashes()` 获取 Hash 列表

### Q: 如何提高大文件打包性能？

1. 使用批量 API (`add_dir_batch`)
2. 对大文件禁用压缩 (`algo_id=0`)
3. 使用更快的压缩算法 (如 LZ4)

### Q: mmap 模式有什么优势？

- 按需加载，内存占用低
- 线程安全，支持并发读取
- 操作系统级缓存优化
