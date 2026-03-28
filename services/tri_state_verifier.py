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


def hex_bit_hamming(h1: str, h2: str) -> int:
    return (int(h1, 16) ^ int(h2, 16)).bit_count()


class TriStateVerifier:
    """
    加权风险评分三态验证器。

    使用解耦 VIF 指纹的三维加权评分进行判定，解决重压缩误报问题。

    判定流程:
        1. SHA-256 匹配 → INTACT
        2. VIF 缺失 → TAMPERED（保守回退）
        3. 解耦 VIF → D_vis, D_sem, D_tem
        4. Risk = W_vis·D_vis + W_sem·D_sem + W_tem·D_tem
           Risk ≥ threshold → TAMPERED, 否则 → RE_ENCODED
    """

    def __init__(
        self,
        w_vis: float = 0.35,
        w_sem: float = 0.40,
        w_tem: float = 0.25,
        risk_threshold: float = 0.18,
    ):
        """
        Args:
            w_vis: 视觉感知哈希权重
            w_sem: 语义拓扑哈希权重
            w_tem: 时序运动哈希权重
            risk_threshold: 综合风险评分阈值（≥ 时判 TAMPERED）
        """
        self.w_vis = w_vis
        self.w_sem = w_sem
        self.w_tem = w_tem
        self.risk_threshold = risk_threshold
        logger.info(
            "TriStateVerifier initialized: w=(%.2f,%.2f,%.2f) "
            "risk_th=%.2f",
            w_vis, w_sem, w_tem, risk_threshold,
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
        o_vis, o_sem, o_tem = split_vif_hex(orig_vif)
        c_vis, c_sem, c_tem = split_vif_hex(curr_vif)

        if o_vis is None or c_vis is None:
            logger.warning("VIF hex too short, falling back to TAMPERED")
            return "TAMPERED", 1.0, {"reason": "vif_invalid"}

        # ── 计算各模态 bit 级 Hamming 距离（归一化到 [0,1]） ──
        d_vis = hex_bit_hamming(o_vis, c_vis) / 64.0
        d_sem = hex_bit_hamming(o_sem, c_sem) / 64.0
        d_tem = hex_bit_hamming(o_tem, c_tem) / 128.0

        details = {"d_vis": round(d_vis, 4), "d_sem": round(d_sem, 4), "d_tem": round(d_tem, 4)}

        # ── 加权风险评分 ──
        risk = self.w_vis * d_vis + self.w_sem * d_sem + self.w_tem * d_tem
        details["risk"] = round(risk, 4)

        if risk >= self.risk_threshold:
            logger.info("Risk %.4f ≥ %.2f → TAMPERED (d=%s)",
                        risk, self.risk_threshold, details)
            return "TAMPERED", risk, details
        else:
            logger.info("Risk %.4f < %.2f → RE_ENCODED (d=%s)",
                        risk, self.risk_threshold, details)
            return "RE_ENCODED", risk, details

