"""
Tri-State Verification Service

Implements tri-state verification logic to distinguish between:
- INTACT: No changes (SHA-256 and pHash match)
- RE_ENCODED: Legitimate re-encoding (SHA-256 differs, pHash similar)
- TAMPERED: Content modification (SHA-256 differs, pHash significantly different)
"""

import logging
from typing import Optional
import numpy as np

from services.perceptual_hash import hamming_distance

logger = logging.getLogger(__name__)


def hex_bit_hamming(h1: str, h2: str) -> int:
    return (int(h1, 16) ^ int(h2, 16)).bit_count()


class TriStateVerifier:
    """
    加权风险评分三态验证器。

    使用解耦 VIF 指纹的两维加权评分（全局感知与全局光流）进行综合判定。

    判定流程:
        1. SHA-256 匹配 → INTACT
        2. VIF 缺失 → TAMPERED（保守回退）
        3. 解耦 VIF → d_vis, d_tem
        4. Risk = W_vis·d_vis + W_tem·d_tem
    """

    def __init__(
        self,
        w_vis: float = 0.50,
        w_tem: float = 0.50,
        risk_threshold: float = 0.20,
    ):
        """
        Args:
            w_vis: 视觉特征总权重
            w_tem: 时序运动特征总权重
            risk_threshold: 综合风险阈值
        """
        self.w_vis = w_vis
        self.w_tem = w_tem
        self.risk_threshold = risk_threshold
        logger.info(
            "TriStateVerifier initialized: w=(%.2f,%.2f) risk_th=%.2f",
            w_vis, w_tem, risk_threshold,
        )

    def verify(
        self,
        orig_sha256: str,
        curr_sha256: str,
        orig_vif: Optional[str],
        curr_vif: Optional[str],
    ) -> tuple:
        from services.vif import split_vif_hex

        # ── 第一级: SHA-256 严格匹配 ──
        if orig_sha256 == curr_sha256:
            logger.debug("SHA-256 match → INTACT")
            return "INTACT", 0.0, {}

        # ── VIF 缺失 ──
        if not orig_vif or not curr_vif:
            return "TAMPERED", 1.0, {"reason": "vif_missing"}

        # ── 解耦 64HEX 二维 VIF ──
        o_vis, o_tem = split_vif_hex(orig_vif)
        c_vis, c_tem = split_vif_hex(curr_vif)

        if o_vis is None or c_vis is None:
            return "TAMPERED", 1.0, {"reason": "vif_invalid"}

        # ── 计算各维度距离 ──
        d_vis = hex_bit_hamming(o_vis, c_vis) / 128.0
        d_tem = hex_bit_hamming(o_tem, c_tem) / 128.0

        details = {
            "d_vis": round(d_vis, 4),
            "d_tem": round(d_tem, 4),
        }

        # ── 加权风险评分 ──
        risk = self.w_vis * d_vis + self.w_tem * d_tem
        details["risk"] = round(risk, 4)

        if risk >= self.risk_threshold:
            logger.info("Risk %.4f ≥ %.2f → TAMPERED (d=%s)",
                        risk, self.risk_threshold, details)
            return "TAMPERED", risk, details
        else:
            logger.info("Risk %.4f < %.2f → RE_ENCODED (d=%s)",
                        risk, self.risk_threshold, details)
            return "RE_ENCODED", risk, details

