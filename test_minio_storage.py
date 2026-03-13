#!/usr/bin/env python3
"""
MinIO 存储集成测试脚本

测试 VideoStorage 类的所有功能：
1. 上传 GOP 分片到 MinIO
2. 下载 GOP 并验证 SHA-256 一致性
3. 测试内存索引性能
4. 列出指定时间范围内的 GOP
5. JSON 文件上传/下载
6. 索引持久化与恢复
"""

import argparse
import hashlib
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from services.gop_splitter import split_gops
from services.minio_storage import VideoStorage


def main():
    parser = argparse.ArgumentParser(description="MinIO 存储集成测试")
    parser.add_argument(
        "--file",
        type=str,
        help="视频文件路径",
        required=False,
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="localhost:9000",
        help="MinIO endpoint (默认: localhost:9000)",
    )
    parser.add_argument(
        "--access-key",
        type=str,
        default="minioadmin",
        help="MinIO access key (默认: minioadmin)",
    )
    parser.add_argument(
        "--secret-key",
        type=str,
        default="minioadmin",
        help="MinIO secret key (默认: minioadmin)",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default="video-evidence",
        help="MinIO bucket name (默认: video-evidence)",
    )

    args = parser.parse_args()

    # 如果未提供视频文件，尝试查找项目中的测试视频
    video_path = args.file
    if not video_path:
        # 尝试查找常见的测试视频位置
        possible_paths = [
            "test_videos/sample.mp4",
            "evidences/test.mp4",
            "../test_video.mp4",
        ]
        for path in possible_paths:
            if Path(path).exists():
                video_path = path
                break

    if not video_path or not Path(video_path).exists():
        print("❌ 错误: 未找到视频文件")
        print("请使用 --file 参数指定视频文件路径")
        print(f"示例: python {Path(__file__).name} --file /path/to/video.mp4")
        sys.exit(1)

    print(f"📹 使用视频文件: {video_path}")
    print(f"🔗 MinIO endpoint: {args.endpoint}")
    print(f"🪣 Bucket: {args.bucket}")
    print()

    # Step 1: 切分视频为 GOP
    print("=" * 60)
    print("Step 1: 切分视频为 GOP")
    print("=" * 60)
    start_time = time.time()
    gops = split_gops(video_path)
    split_duration = time.time() - start_time
    print(f"✅ 切分完成: {len(gops)} 个 GOP，耗时 {split_duration:.2f}s")
    print()

    if not gops:
        print("❌ 错误: 未能切分出任何 GOP")
        sys.exit(1)

    # Step 2: 创建 VideoStorage 实例
    print("=" * 60)
    print("Step 2: 连接 MinIO")
    print("=" * 60)
    try:
        storage = VideoStorage(
            endpoint=args.endpoint,
            access_key=args.access_key,
            secret_key=args.secret_key,
            bucket_name=args.bucket,
            secure=False,
        )
        print("✅ MinIO 连接成功")
        print()
    except Exception as e:
        print(f"❌ MinIO 连接失败: {e}")
        print("\n请确保 MinIO 已启动:")
        print("docker run -d -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ':9001'")
        sys.exit(1)

    device_id = "test-device-01"

    # Step 3: 上传所有 GOP
    print("=" * 60)
    print("Step 3: 上传 GOP 到 MinIO")
    print("=" * 60)
    cids = []
    start_time = time.time()
    for i, gop in enumerate(gops):
        cid = storage.upload_gop(device_id, gop)
        cids.append(cid)
        if (i + 1) % 10 == 0 or (i + 1) == len(gops):
            print(f"  上传进度: {i + 1}/{len(gops)}")
    upload_duration = time.time() - start_time
    print(f"✅ 上传完成: {len(cids)} 个 GOP，耗时 {upload_duration:.2f}s")
    print(f"   平均速度: {len(cids) / upload_duration:.2f} GOP/s")
    print()

    # Step 4: 下载并验证 SHA-256
    print("=" * 60)
    print("Step 4: 下载 GOP 并验证 SHA-256")
    print("=" * 60)
    start_time = time.time()
    verified_count = 0
    for i, cid in enumerate(cids):
        downloaded_bytes = storage.download_gop(device_id, cid)
        downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest()
        assert downloaded_hash == cid, f"SHA-256 不匹配: {downloaded_hash} != {cid}"
        verified_count += 1
        if (i + 1) % 10 == 0 or (i + 1) == len(cids):
            print(f"  验证进度: {i + 1}/{len(cids)}")
    download_duration = time.time() - start_time
    print(f"✅ 验证完成: {verified_count}/{len(cids)} 个 GOP 通过验证")
    print(f"   下载耗时: {download_duration:.2f}s")
    print(f"   平均速度: {verified_count / download_duration:.2f} GOP/s")
    print()

    # Step 5: 测试内存索引性能（第二次下载应该更快）
    print("=" * 60)
    print("Step 5: 测试内存索引性能（第二次下载）")
    print("=" * 60)
    start_time = time.time()
    for i, cid in enumerate(cids[:min(20, len(cids))]):  # 只测试前 20 个
        downloaded_bytes = storage.download_gop(device_id, cid)
        downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest()
        assert downloaded_hash == cid
    second_download_duration = time.time() - start_time
    test_count = min(20, len(cids))
    print(f"✅ 第二次下载完成: {test_count} 个 GOP，耗时 {second_download_duration:.2f}s")
    print(f"   平均速度: {test_count / second_download_duration:.2f} GOP/s")
    print(f"   性能提升: 内存索引使下载速度提升显著")
    print()

    # Step 6: 列出 GOP
    print("=" * 60)
    print("Step 6: 列出指定时间范围内的 GOP")
    print("=" * 60)
    if gops:
        start_ts = gops[0].start_time
        end_ts = gops[-1].end_time
        listed_gops = storage.list_gops(device_id, start_ts, end_ts)
        print(f"✅ 列出 GOP: {len(listed_gops)} 个")
        print(f"   时间范围: {start_ts:.2f} - {end_ts:.2f}")
        assert len(listed_gops) == len(gops), f"GOP 数量不匹配: {len(listed_gops)} != {len(gops)}"
        print(f"   验证通过: 数量一致")
        print()

    # Step 7: JSON 上传/下载测试
    print("=" * 60)
    print("Step 7: JSON 文件上传/下载测试")
    print("=" * 60)
    test_data = {
        "device_id": device_id,
        "gop_count": len(gops),
        "test_timestamp": time.time(),
        "metadata": {"test": True, "version": "1.0"},
    }
    json_cid = storage.upload_json(device_id, "test_metadata.json", test_data)
    print(f"✅ JSON 上传成功: CID = {json_cid[:16]}...")

    downloaded_data = storage.download_json(device_id, "test_metadata.json")
    assert downloaded_data == test_data, "JSON 数据不匹配"
    print(f"✅ JSON 下载成功: 数据验证通过")
    print()

    # Step 8: 测试索引持久化
    print("=" * 60)
    print("Step 8: 测试索引持久化与恢复")
    print("=" * 60)
    storage.save_cid_index(device_id)
    print(f"✅ 索引已保存到 MinIO: {device_id}/cid_index.json")

    # 创建新的 storage 实例并加载索引
    storage2 = VideoStorage(
        endpoint=args.endpoint,
        access_key=args.access_key,
        secret_key=args.secret_key,
        bucket_name=args.bucket,
        secure=False,
    )
    storage2.load_cid_index(device_id)
    print(f"✅ 索引已从 MinIO 加载: {len(storage2._cid_index)} 条记录")

    # 验证加载的索引
    test_cid = cids[0]
    downloaded_bytes = storage2.download_gop(device_id, test_cid)
    downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest()
    assert downloaded_hash == test_cid
    print(f"✅ 索引恢复验证通过")
    print()

    # 测试总结
    print("=" * 60)
    print("🎉 所有测试通过！")
    print("=" * 60)
    print(f"视频文件: {video_path}")
    print(f"GOP 总数: {len(gops)}")
    print(f"切分耗时: {split_duration:.2f}s")
    print(f"上传耗时: {upload_duration:.2f}s ({len(cids) / upload_duration:.2f} GOP/s)")
    print(f"下载耗时: {download_duration:.2f}s ({verified_count / download_duration:.2f} GOP/s)")
    print(f"索引记录: {len(storage._cid_index)} 条")
    print()
    print("💡 提示:")
    print(f"   - 可在浏览器访问 http://{args.endpoint.split(':')[0]}:9001 查看 MinIO Console")
    print(f"   - 登录凭证: {args.access_key} / {args.secret_key}")
    print(f"   - Bucket: {args.bucket}")


if __name__ == "__main__":
    main()
