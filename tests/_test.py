from grimoire import ManifestBuilder, ManifestReader, MD5Hook, ManifestJsonConverter, RcloneHashHook
from grimoire.hooks import ZlibCompressHook
import time

chook = MD5Hook()

def on_progress(info):
    print(f"{info.progress:.1%} - {info.current_file}")

def test_build():
    """使用优化的 add_dir_batch_rclone 方法"""
    start = time.time()
    
    builder = ManifestBuilder(
        "game.manifest",
        index_crypto=ZlibCompressHook(),
        checksum_hook=RcloneHashHook("md5")
    )
    
    # 使用专门优化的 rclone 批量方法
    result = builder.add_dir_batch_rclone(
        r"src\grimoire", 
        "DATA",    
        progress_callback=on_progress
    )
    
    elapsed = time.time() - start
    print(f"\n成功: {result.success_count}, 失败: {result.failed_count}")
    print(f"总耗时: {elapsed:.2f}s")
    
    builder.build()

def test_read():
    with ManifestReader(
        "game.manifest", 
        index_crypto=ZlibCompressHook(),
        checksum_hook=RcloneHashHook("md5", check_on_init=False)
    ) as reader:
        print(f"条目数: {reader.entry_count}")
        for item in reader.list_all()[:10]:
            print(item)

def test_convert():
    ManifestJsonConverter.manifest_to_json(
        "game.manifest", 
        "game.json"
    )
    print("JSON 转换完成!")

if __name__ == "__main__":
    test_build()
    # test_read()
    test_convert()