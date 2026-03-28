"""
Tri-State Verification Service

Implements tri-state verification logic to distinguish between:
- INTACT: No changes (SHA-256 match)
- RE_ENCODED: Legitimate re-encoding (SHA-256 differs, VIF within tolerant band)
- TAMPERED: High risk of tampering (SHA-256 differs, VIF outside tolerant band)
"""

import logging
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


def hex_bit_hamming(h1: str, h2: str) -> int:
    return (int(h1, 16) ^ int(h2, 16)).bit_count()


class TriStateVerifier:
    """
    双哈希 + 宽容带评分三态验证器 (Tolerant Mode - Phase 4).

    判定流程:
        1. SHA-256 完全匹配 → INTACT (无损失原档)
        2. VIF 缺失或损毁 → TAMPERED（异常阻断，并标记为 TAMPERED_SUSPECT 供细粒度分析）
        3. Risk < tolerant_threshold → RE_ENCODED (安全合法转码宽容带)
        4. Risk ≥ tolerant_threshold → TAMPERED (接口兼容), details/日志标记 "TAMPERED_SUSPECT" 
           (高危嫌疑，非最终判决，需交由细粒度环节确认)。
    """

    def __init__(
        self,
        # 宽容模式主线阈值 (对于 256-bit 归一化汉明距离，基准容忍门限)
        tolerant_threshold: float = 0.35,
        ablation_threshold: Optional[float] = None,
    ):
        """
        Args:
            tolerant_threshold: 数据驱动配置的安全容忍门限（默认主线）
            ablation_threshold: 实验跑分时的备用红线门限（若提供则覆盖默认主线）
        """
        # 优先使用 ablation threshold 如果指定了的话
        self.active_threshold = ablation_threshold if ablation_threshold is not None else tolerant_threshold
        
        logger.info(
            "TriStateVerifier (Tolerant Mode v4) initialized: active_th=%.2f",
            self.active_threshold,
        )

    def verify(
        self,
        orig_sha256: str,
        curr_sha256: str,
        orig_vif: Optional[str],
        curr_vif: Optional[str],
    ) -> tuple:
        # ── 第一级: SHA-256 严格匹配 ──
        if orig_sha256 == curr_sha256:
            logger.debug("SHA-256 match → INTACT")
            return "INTACT", 0.0, {"state_desc": "INTACT"}

        # ── VIF 缺失 ──
        if not orig_vif or not curr_vif:
            return "TAMPERED", 1.0, {"reason": "vif_missing", "state_desc": "TAMPERED_SUSPECT"}

        # ── 计算新版统一 VIF (256-bit) 的汉明距离 ──
        # 归一化：除以位宽 256
        if len(orig_vif) != 64 or len(curr_vif) != 64:
            return "TAMPERED", 1.0, {"reason": "vif_format_invalid", "state_desc": "TAMPERED_SUSPECT"}

        d_vis = hex_bit_hamming(orig_vif, curr_vif) / 256.0

        details = {
            "d_vis": round(d_vis, 4),
            "risk": round(d_vis, 4),
            "vif_version": "v4"
        }

        risk = d_vis

        if risk >= self.active_threshold:
            logger.info("Risk %.4f >= %.2f → TAMPERED_SUSPECT (d=%s)",
                        risk, self.active_threshold, details)
            details["state_desc"] = "TAMPERED_SUSPECT"
            # Return "TAMPERED" for UI compatibility, but log/describe as SUSPECT
            return "TAMPERED", risk, details
        else:
            logger.info("Risk %.4f < %.2f → RE_ENCODED (d=%s)",
                        risk, self.active_threshold, details)
            details["state_desc"] = "RE_ENCODED"
            return "RE_ENCODED", risk, details
