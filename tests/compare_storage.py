import json
import zlib

# 读取真实数据
with open('game.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

entries = data['entries']
print(f'文件数: {len(entries)}')
print('=' * 70)

# 提取路径列表
paths = [e['path'] for e in entries]

# 解析路径
dir_set = set()
name_set = set()
ext_set = set()

for p in paths:
    parts = p.rsplit('/', 1)
    dir_part = parts[0] if len(parts) > 1 else ''
    filename = parts[-1]
    
    ext_idx = filename.find('.')
    if ext_idx != -1:
        name_part = filename[:ext_idx]
        ext_part = filename[ext_idx:]
    else:
        name_part = filename
        ext_part = ''
    
    dir_set.add(dir_part)
    name_set.add(name_part)
    ext_set.add(ext_part)

def encode_string_table(strings):
    data = b''
    for s in sorted(strings):
        encoded = s.encode('utf-8')
        data += len(encoded).to_bytes(2, 'little')
        data += encoded
    return data

dir_table = encode_string_table(dir_set)
name_table = encode_string_table(name_set)
ext_table = encode_string_table(ext_set)
string_tables_raw = dir_table + name_table + ext_table

print(f'目录数: {len(dir_set)}, 名称数: {len(name_set)}, 扩展名数: {len(ext_set)}')
print()

# XOR 混淆
def xor_obfuscate(data, key=b'GrimoireVFS'):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

# Entry Table (每条目: 8 hash + 6 ids + 8 size + 20 checksum = 42 bytes)
entry_table_size = len(entries) * 42

print('方案 A: 字典模式')
print('-' * 70)

# A1: 不压缩
total_a1 = len(string_tables_raw) + entry_table_size
print(f'A1 不压缩:      String Tables {len(string_tables_raw):>6} + Entry {entry_table_size:>6} = {total_a1:>7} bytes')

# A2: 压缩 String Tables
st_compressed = zlib.compress(string_tables_raw, 9)
total_a2 = len(st_compressed) + entry_table_size
print(f'A2 压缩ST:      String Tables {len(st_compressed):>6} + Entry {entry_table_size:>6} = {total_a2:>7} bytes')

# A3: 压缩+混淆 String Tables
st_zlib_xor = xor_obfuscate(st_compressed)
total_a3 = len(st_zlib_xor) + entry_table_size
print(f'A3 压缩+混淆:   String Tables {len(st_zlib_xor):>6} + Entry {entry_table_size:>6} = {total_a3:>7} bytes')

print()
print('方案 B: 完整路径模式')
print('-' * 70)

# 所有路径拼接
all_paths_raw = '\n'.join(paths).encode('utf-8')
all_paths_compressed = zlib.compress(all_paths_raw, 9)

# Entry 固定字段
entry_fixed = len(entries) * 36  # path_offset(4) + path_len(2) + size(8) + checksum(20) + padding(2)

# B1: 不压缩路径
total_b1 = len(all_paths_raw) + entry_fixed
print(f'B1 不压缩:      Path Blob {len(all_paths_raw):>6} + Entry {entry_fixed:>6} = {total_b1:>7} bytes')

# B2: 压缩路径
total_b2 = len(all_paths_compressed) + entry_fixed
print(f'B2 压缩:        Path Blob {len(all_paths_compressed):>6} + Entry {entry_fixed:>6} = {total_b2:>7} bytes')

# B3: 压缩+混淆
paths_zlib_xor = xor_obfuscate(all_paths_compressed)
total_b3 = len(paths_zlib_xor) + entry_fixed
print(f'B3 压缩+混淆:   Path Blob {len(paths_zlib_xor):>6} + Entry {entry_fixed:>6} = {total_b3:>7} bytes')

print()
print('=' * 70)
print('对比总结')
print('=' * 70)
results = [
    ('A1 字典-不压缩', total_a1),
    ('A2 字典-压缩', total_a2),
    ('A3 字典-压缩混淆', total_a3),
    ('B1 完整路径-不压缩', total_b1),
    ('B2 完整路径-压缩', total_b2),
    ('B3 完整路径-压缩混淆', total_b3),
]

results.sort(key=lambda x: x[1])
best = results[0][1]
for name, size in results:
    diff = ((size - best) / best * 100) if size != best else 0
    marker = '(最优)' if diff == 0 else f'+{diff:.1f}%'
    print(f'{name:25} {size:>7} bytes  {marker:>10}')

print()
print('关键洞察:')
print(f'  路径原始: {len(all_paths_raw):>6} bytes → 压缩后 {len(all_paths_compressed):>5} bytes (压缩率 {len(all_paths_compressed)/len(all_paths_raw):.1%})')
print(f'  字典原始: {len(string_tables_raw):>6} bytes → 压缩后 {len(st_compressed):>5} bytes (压缩率 {len(st_compressed)/len(string_tables_raw):.1%})')
