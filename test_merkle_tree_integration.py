#!/usr/bin/env python3
"""
MerkleTree 集成测试脚本

用合成 GOP SHA-256 哈希列表构建 Merkle 树，验证 proof 生成与验证、
JSON 序列化往返、篡改检测。无需 PyAV 或视频文件。
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.merkle_utils import MerkleTree


def main():
    # Step 1: 模拟 GOP 切分产生的 SHA-256 哈希列表
    gop_count = 7  # 非 2 的幂次，测试 padding
    gop_hashes = [
        hashlib.sha256(f"gop_raw_bytes_{i}".encode()).hexdigest()
        for i in range(gop_count)
    ]
    print(f"Step 1: 生成 {gop_count} 个合成 GOP 哈希")
    for i, h in enumerate(gop_hashes):
        print(f"  GOP {i}: {h[:16]}...")

    # Step 2: 构建 MerkleTree
    tree = MerkleTree(gop_hashes)
    print(f"\nStep 2: Merkle root = {tree.root}")

    # Step 3: 对每个 GOP 生成并验证 proof
    print("\nStep 3: 逐个验证 Merkle Proof")
    for i in range(gop_count):
        proof = tree.get_proof(i)
        ok = MerkleTree.verify_proof(gop_hashes[i], proof, tree.root)
        status = "PASS" if ok else "FAIL"
        print(f"  GOP {i}: proof_len={len(proof)}, verify={status}")
        assert ok, f"Proof verification failed for GOP {i}"

    # Step 4: JSON 序列化往返
    json_str = tree.to_json()
    restored = MerkleTree.from_json(json_str)
    assert restored.root == tree.root
    for i in range(gop_count):
        assert restored.get_proof(i) == tree.get_proof(i)
    print(f"\nStep 4: JSON 往返测试 PASS (root match = {restored.root == tree.root})")

    # Step 5: 篡改检测
    tampered = hashlib.sha256(b"tampered_gop").hexdigest()
    proof_0 = tree.get_proof(0)
    assert not MerkleTree.verify_proof(tampered, proof_0, tree.root)
    print(f"Step 5: 篡改检测 PASS (伪造哈希被正确拒绝)")

    print("\n所有集成测试通过。")


if __name__ == "__main__":
    main()
