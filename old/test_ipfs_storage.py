#!/usr/bin/env python3
"""
IPFS 存储集成测试脚本

测试 VideoStorage 类的所有功能：
1. 连接 IPFS 节点
2. 上传 GOP 分片到 IPFS
3. 下载 GOP 并验证 SHA-256 一致性
4. 按时间范围列出 GOP（SQLite 查询）
5. JSON 文件上传/下载
6. 跨节点验证（如果有多节点）
"""

import argparse
import hashlib
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from services.gop_splitter import split_gops
from services.ipfs_storage import VideoStorage


def main():
    parser = argparse.ArgumentParser(description="IPFS 存储集成测试")
    parser.add_argument(
        "--file",
        type=str,
        help="视频文件路径",
        required=False,
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:5001",
        help="IPFS API URL (默认: http://localhost:5001)",
    )
    parser.add_argument(
        "--gateway-url",
        type=str,
        default="http://localhost:8080",
        help="IPFS Gateway URL (默认: http://localhost:8080)",
    )
    parser.add_argument(
        "--cross-node-url",
        type=str,
        default=None,
        help="第二个 IPFS 节点 API URL（用于跨节点验证，例如 http://localhost:5002）",
    )

    args = parser.parse_args()

    # 如果未提供视频文件，尝试查找项目中的测试视频
    video_path = args.file
    if not video_path:
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
    print(f"🔗 IPFS API: {args.api_url}")
    print(f"🌐 IPFS Gateway: {args.gateway_url}")
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
    print("Step 2: 连接 IPFS 节点")
    print("=" * 60)
    try:
        storage = VideoStorage(
            api_url=args.api_url,
            gateway_url=args.gateway_url,
            pin_enabled=True,
            index_db_path="data/ipfs_test_index.db",
        )
        print("✅ IPFS 节点连接成功")

        # 显示节点信息
        stats = storage.get_node_stats()
        if stats:
            print(f"   存储使用: {stats.get('repo_size', 0) / 1024 / 1024:.1f} MB")
            print(f"   对象数量: {stats.get('num_objects', 0)}")
        print()
    except Exception as e:
        print(f"❌ IPFS 连接失败: {e}")
        print("\n请确保 IPFS 已启动:")
        print("docker compose -f docker-compose.ipfs.yml up -d")
        sys.exit(1)

    device_id = "test-device-01"

    # Step 3: 上传所有 GOP
    print("=" * 60)
    print("Step 3: 上传 GOP 到 IPFS")
    print("=" * 60)
    cids = []
    sha256_hashes = []
    start_time = time.time()
    for i, gop in enumerate(gops):
        cid = storage.upload_gop(device_id, gop)
        cids.append(cid)
        sha256_hashes.append(gop.sha256_hash)
        if (i + 1) % 10 == 0 or (i + 1) == len(gops):
            print(f"  上传进度: {i + 1}/{len(gops)}")
    upload_duration = time.time() - start_time
    print(f"✅ 上传完成: {len(cids)} 个 GOP，耗时 {upload_duration:.2f}s")
    print(f"   平均速度: {len(cids) / upload_duration:.2f} GOP/s")
    print(f"   示例 CID: {cids[0]}")
    print(f"   Gateway URL: {storage.get_gateway_url(cids[0])}")
    print()

    # Step 4: 下载并验证 SHA-256
    print("=" * 60)
    print("Step 4: 下载 GOP 并验证 SHA-256")
    print("=" * 60)
    start_time = time.time()
    verified_count = 0
    for i, (cid, expected_sha) in enumerate(zip(cids, sha256_hashes)):
        downloaded_bytes = storage.download_gop(device_id, cid)
        downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest()
        assert downloaded_hash == expected_sha, (
            f"SHA-256 不匹配: {downloaded_hash} != {expected_sha}"
        )
        verified_count += 1
        if (i + 1) % 10 == 0 or (i + 1) == len(cids):
            print(f"  验证进度: {i + 1}/{len(cids)}")
    download_duration = time.time() - start_time
    print(f"✅ 验证完成: {verified_count}/{len(cids)} 个 GOP 通过 SHA-256 验证")
    print(f"   下载耗时: {download_duration:.2f}s")
    print(f"   平均速度: {verified_count / download_duration:.2f} GOP/s")
    print()

    # Step 5: 通过 SHA-256 下载（兼容性测试）
    print("=" * 60)
    print("Step 5: 通过 SHA-256 下载（兼容旧代码）")
    print("=" * 60)
    test_sha = sha256_hashes[0]
    downloaded_bytes = storage.download_gop(device_id, test_sha)
    downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest()
    assert downloaded_hash == test_sha
    print(f"✅ SHA-256 查找成功: {test_sha[:16]}... → CID {cids[0]}")
    print()

    # Step 6: 列出 GOP
    print("=" * 60)
    print("Step 6: 列出指定时间范围内的 GOP（SQLite 查询）")
    print("=" * 60)
    if gops:
        start_ts = gops[0].start_time
        end_ts = gops[-1].end_time
        listed_gops = storage.list_gops(device_id, start_ts, end_ts)
        print(f"✅ 列出 GOP: {len(listed_gops)} 个")
        print(f"   时间范围: {start_ts:.2f} - {end_ts:.2f}")
        assert len(listed_gops) == len(gops), (
            f"GOP 数量不匹配: {len(listed_gops)} != {len(gops)}"
        )
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
        "storage_backend": "ipfs",
        "metadata": {"test": True, "version": "1.5.0"},
    }
    json_hash = storage.upload_json(device_id, "test_metadata.json", test_data)
    print(f"✅ JSON 上传成功: SHA-256 = {json_hash[:16]}...")

    downloaded_data = storage.download_json(device_id, "test_metadata.json")
    assert downloaded_data == test_data, "JSON 数据不匹配"
    print(f"✅ JSON 下载成功: 数据验证通过")
    print()

    # Step 8: 跨节点验证（可选）
    if args.cross_node_url:
        print("=" * 60)
        print("Step 8: 跨节点验证（去中心化）")
        print("=" * 60)
        try:
            storage2 = VideoStorage(
                api_url=args.cross_node_url,
                gateway_url=args.gateway_url,
                pin_enabled=False,
                index_db_path="data/ipfs_test_index_node2.db",
            )
            print(f"✅ 第二节点连接成功: {args.cross_node_url}")

            # 从第二节点下载第一节点上传的内容
            test_cid = cids[0]
            print(f"   尝试从 node2 获取 node0 的 CID: {test_cid}")
            downloaded_bytes = storage2.client.cat(test_cid)
            downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest()
            assert downloaded_hash == sha256_hashes[0]
            print(f"✅ 跨节点验证通过：内容一致，去中心化存储生效")
        except Exception as e:
            print(f"⚠️  跨节点验证失败: {e}")
            print(f"   (确保两个节点已互联)")
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
    print(f"存储后端: IPFS (去中心化内容寻址)")
    print()
    print("💡 提示:")
    print(f"   - IPFS WebUI: {args.api_url}/webui")
    print(f"   - Gateway: {args.gateway_url}/ipfs/<CID>")
    print(f"   - 示例: {storage.get_gateway_url(cids[0])}")


if __name__ == "__main__":
    main()
