"""
Tri-State Verification Service

Implements tri-state verification logic to distinguish between:
- INTACT: No changes (SHA-256 and pHash match)
- RE_ENCODED: Legitimate re-encoding (SHA-256 differs, pHash similar)
- TAMPERED: Content modification (SHA-256 differs, pHash significantly different)
"""

import logging
from typing import Optional

from services.perceptual_hash import hamming_distance

logger = logging.getLogger(__name__)


class TriStateVerifier:
    """
    Verifies GOP integrity using combined SHA-256 and perceptual hash analysis.

    The verifier uses a two-stage approach:
    1. SHA-256 comparison for exact byte-level matching
    2. Perceptual hash (pHash) comparison for content-level similarity

    This allows detection of malicious tampering while tolerating legitimate
    video re-encoding (e.g., H.264→H.265 transcoding, JPEG compression).
    """

    def __init__(self, hamming_threshold: int = 10):
        """
        Initialize tri-state verifier.

        Args:
            hamming_threshold: Maximum Hamming distance (bits) to consider
                             pHashes as "similar". Default 10 bits tolerates
                             video transcoding. Lower values (e.g., 5) are more
                             strict but may misclassify legitimate re-encoding.

        Note:
            - Threshold of 5 bits: Conservative, may flag transcoding as tampering
            - Threshold of 10 bits: Balanced, tolerates H.264→H.265 transcoding
            - Threshold of 15+ bits: Permissive, may miss subtle tampering
        """
        if hamming_threshold < 0 or hamming_threshold > 64:
            raise ValueError("hamming_threshold must be between 0 and 64")

        self.hamming_threshold = hamming_threshold
        logger.info(f"TriStateVerifier initialized with threshold={hamming_threshold}")

    def verify(
        self,
        original_sha256: str,
        original_phash: Optional[str],
        current_sha256: str,
        current_phash: Optional[str],
    ) -> str:
        """
        Verify GOP integrity using tri-state logic.

        Args:
            original_sha256: SHA-256 hash of original GOP bytes
            original_phash: Perceptual hash of original keyframe (or None)
            current_sha256: SHA-256 hash of current GOP bytes
            current_phash: Perceptual hash of current keyframe (or None)

        Returns:
            One of: "INTACT", "RE_ENCODED", "TAMPERED"

        Logic:
            1. If SHA-256 matches → "INTACT" (regardless of pHash)
            2. If SHA-256 differs:
               - If pHash missing → "TAMPERED" (conservative fallback)
               - If pHash distance ≤ threshold → "RE_ENCODED"
               - If pHash distance > threshold → "TAMPERED"

        Note:
            When pHash is None (computation failed), the verifier falls back
            to SHA-256-only mode and returns "TAMPERED" for any mismatch.
            This is a conservative approach that prioritizes security over
            convenience, but may produce false positives if pHash computation
            fails on legitimate re-encoded content.
        """
        # Stage 1: SHA-256 comparison (exact byte-level match)
        if original_sha256 == current_sha256:
            logger.debug("SHA-256 match → INTACT")
            return "INTACT"

        # Stage 2: SHA-256 differs, check pHash for content similarity
        logger.debug("SHA-256 mismatch, checking pHash")

        # Fallback: If pHash is missing, cannot determine re-encoding vs tampering
        if original_phash is None or current_phash is None:
            logger.warning(
                "pHash missing (original=%s, current=%s), falling back to TAMPERED",
                original_phash is not None,
                current_phash is not None,
            )
            return "TAMPERED"

        # Calculate perceptual similarity
        try:
            distance = hamming_distance(original_phash, current_phash)
            logger.debug(f"pHash Hamming distance: {distance} bits")

            if distance <= self.hamming_threshold:
                logger.info(f"pHash similar (distance={distance}) → RE_ENCODED")
                return "RE_ENCODED"
            else:
                logger.info(f"pHash different (distance={distance}) → TAMPERED")
                return "TAMPERED"

        except ValueError as e:
            logger.error(f"pHash comparison failed: {e}")
            return "TAMPERED"


# ── VIF v2: 加权风险评分验证器 ─────────────────────────────────────────

def hex_bit_hamming(hex1: str, hex2: str) -> int:
    """计算两个十六进制字符串的二进制位级 Hamming 距离。

    不能用字符级比较！Hex '7'=0111 vs '8'=1000 字符差 1，但 bit 差 4。
    必须通过 XOR → 统计 1 的个数。
    """
    return bin(int(hex1, 16) ^ int(hex2, 16)).count('1')


class TriStateVerifierV2:
    """
    加权风险评分三态验证器 (VIF v2)。

    替代旧 TriStateVerifier 的"串行一票否决"逻辑，采用解耦 VIF 指纹
    的三维加权评分，解决重压缩误报问题。

    判定流程:
        1. SHA-256 匹配 → INTACT
        2. VIF 缺失 → TAMPERED（保守回退）
        3. 解耦 VIF → D_vis, D_sem, D_tem
        4. 语义一票否决: D_sem > semantic_veto → TAMPERED
        5. Risk = W_vis·D_vis + W_sem·D_sem + W_tem·D_tem
           Risk ≥ threshold → TAMPERED, 否则 → RE_ENCODED
    """

    def __init__(
        self,
        w_vis: float = 0.35,
        w_sem: float = 0.40,
        w_tem: float = 0.25,
        risk_threshold: float = 0.18,
        semantic_veto: float = 0.10,
    ):
        """
        Args:
            w_vis: 视觉感知哈希权重
            w_sem: 语义拓扑哈希权重
            w_tem: 时序运动哈希权重
            risk_threshold: 综合风险评分阈值（≥ 时判 TAMPERED）
            semantic_veto: 语义一票否决阈值（D_sem > 此值直接 TAMPERED）
        """
        self.w_vis = w_vis
        self.w_sem = w_sem
        self.w_tem = w_tem
        self.risk_threshold = risk_threshold
        self.semantic_veto = semantic_veto
        logger.info(
            "TriStateVerifierV2 initialized: w=(%.2f,%.2f,%.2f) "
            "risk_th=%.2f sem_veto=%.2f",
            w_vis, w_sem, w_tem, risk_threshold, semantic_veto,
        )

    def verify(
        self,
        orig_sha256: str,
        curr_sha256: str,
        orig_vif: Optional[str],
        curr_vif: Optional[str],
    ) -> tuple:
        """
        使用解耦 VIF 加权评分验证完整性。

        Args:
            orig_sha256: 原始 GOP 的 SHA-256
            curr_sha256: 待验 GOP 的 SHA-256
            orig_vif: 原始 256-bit VIF hex (64 chars)
            curr_vif: 待验 256-bit VIF hex (64 chars)

        Returns:
            (state, risk_score, details)
            - state: "INTACT" | "RE_ENCODED" | "TAMPERED"
            - risk_score: 0.0~1.0 风险评分
            - details: {"d_vis", "d_sem", "d_tem", ...}
        """
        from services.vif import split_vif_hex

        # ── 第一级: SHA-256 严格匹配 ──
        if orig_sha256 == curr_sha256:
            logger.debug("SHA-256 match → INTACT")
            return "INTACT", 0.0, {}

        # ── VIF 缺失 → 保守回退 ──
        if not orig_vif or not curr_vif:
            logger.warning("VIF missing, falling back to TAMPERED")
            return "TAMPERED", 1.0, {"reason": "vif_missing"}

        # ── 解耦 VIF 指纹 ──
        o_vis, o_sem, o_tem, o_tag = split_vif_hex(orig_vif)
        c_vis, c_sem, c_tem, c_tag = split_vif_hex(curr_vif)

        if o_vis is None or c_vis is None:
            logger.warning("VIF hex too short, falling back to TAMPERED")
            return "TAMPERED", 1.0, {"reason": "vif_invalid"}

        # ── 计算各模态 bit 级 Hamming 距离（归一化到 [0,1]） ──
        d_vis = hex_bit_hamming(o_vis, c_vis) / 64.0
        d_sem = hex_bit_hamming(o_sem, c_sem) / 64.0
        d_tem = hex_bit_hamming(o_tem, c_tem) / 128.0

        details = {"d_vis": round(d_vis, 4), "d_sem": round(d_sem, 4),
                   "d_tem": round(d_tem, 4),
                   "orig_tag": o_tag, "curr_tag": c_tag}

        # ── 语义一票否决：目标消失/出现 → 直接 TAMPERED ──
        if d_sem > self.semantic_veto:
            logger.info("Semantic veto triggered: d_sem=%.4f > %.2f → TAMPERED",
                        d_sem, self.semantic_veto)
            details["reason"] = "semantic_veto"
            return "TAMPERED", 1.0, details

        # ── 时序来源不匹配惩罚 ──
        # 原始有 MV (tag='m') 说明视频使用 inter-frame 编码，
        # 篡改侧丢失 MV (tag='f') → P/B 字节被破坏导致解码失败
        # 这本身就是高度可疑的信号（合法重编码会保留 MV）
        mv_loss_penalty = 0.0
        if o_tag == 'm' and c_tag == 'f':
            mv_loss_penalty = 0.10
            details["reason"] = "mv_loss"
            logger.info("MV loss detected: orig=%s curr=%s → penalty %.2f",
                        o_tag, c_tag, mv_loss_penalty)

        # ── 加权风险评分 ──
        risk = self.w_vis * d_vis + self.w_sem * d_sem + self.w_tem * d_tem + mv_loss_penalty
        details["risk"] = round(risk, 4)

        if risk >= self.risk_threshold:
            logger.info("Risk %.4f ≥ %.2f → TAMPERED (d=%s)",
                        risk, self.risk_threshold, details)
            return "TAMPERED", risk, details
        else:
            logger.info("Risk %.4f < %.2f → RE_ENCODED (d=%s)",
                        risk, self.risk_threshold, details)
            return "RE_ENCODED", risk, details

