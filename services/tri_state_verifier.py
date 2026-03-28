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
    加权风险评分三态验证器 (宽容模式 / Tolerant Mode).

    在复杂、高动态的真实监控/视频流中，合法重压制（RE_ENCODED）带来的
    特征漂移（特别是马赛克导致的 d_vis 波动）可能达到 P99 > 0.32。
    因此，本验证器不再强求区分极细微的局部/时序篡改（细粒度检出率让步给后级 MAB），
    而是优先保证合法业务转码的“0 误伤”，作为系统的高效前置基准点（Pre-filter）。

    判定流程:
        1. SHA-256 匹配 → INTACT (无损失原档)
        2. VIF 缺失或损毁 → TAMPERED（异常阻断）
        3. Risk < tampered_alert_threshold → RE_ENCODED (安全合法转码区间)
        4. Risk ≥ tampered_alert_threshold → TAMPERED (显著攻击或极其恶劣的破坏)
    """

    def __init__(
        self,
        w_vis: float = 0.50,
        w_tem: float = 0.50,
        # 基于真实复杂视频数据集 (如 LE SSERAFIM Benchmark_v2 P99上尾分布的 0.3203)
        # 宽容模式主线阈值 (推荐置于合法转码上尾 P99 以上, e.g., 0.35)
        tolerant_threshold: float = 0.35,
        # 用于剥离宽容模式、执行激进实验配置下的旧版阈值 (如 0.25)
        ablation_threshold: Optional[float] = None,
    ):
        """
        Args:
            w_vis: 视觉特征总权重
            w_tem: 时序运动特征总权重
            tolerant_threshold: 数据驱动配置的安全容忍门限（默认主线）
            ablation_threshold: 实验跑分时的备用红线门限（若提供则覆盖默认主线）
        """
        self.w_vis = w_vis
        self.w_tem = w_tem
        
        # 优先使用 ablation threshold 如果指定了的话
        self.active_threshold = ablation_threshold if ablation_threshold is not None else tolerant_threshold
        
        logger.info(
            "TriStateVerifier (Tolerant Mode) initialized: w=(%.2f,%.2f) active_th=%.2f",
            w_vis, w_tem, self.active_threshold,
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

        if risk >= self.active_threshold:
            logger.info("Risk %.4f ≥ %.2f → TAMPERED (d=%s)",
                        risk, self.active_threshold, details)
            return "TAMPERED", risk, details
        else:
            logger.info("Risk %.4f < %.2f → RE_ENCODED (d=%s)",
                        risk, self.active_threshold, details)
            return "RE_ENCODED", risk, details

