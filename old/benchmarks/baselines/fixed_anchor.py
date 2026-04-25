"""
Baseline: 固定间隔锚定策略。

每 N 个 GOP 固定锚定一次，不考虑场景活跃度。
"""

from typing import List


class FixedAnchor:
    """固定间隔锚定 baseline。"""

    def __init__(self, interval: int = 5):
        """
        Args:
            interval: 每隔多少个 GOP 锚定一次
        """
        self.interval = interval
        self._counter = 0
        self.anchor_count = 0

    def should_anchor(self, gop_index: int) -> bool:
        self._counter += 1
        if self._counter >= self.interval:
            self._counter = 0
            self.anchor_count += 1
            return True
        return False

    def get_cost(self, total_gops: int) -> dict:
        """计算锚定成本。"""
        num_anchors = total_gops // self.interval
        return {
            "total_gops": total_gops,
            "interval": self.interval,
            "num_anchors": num_anchors,
            "anchor_ratio": round(num_anchors / max(1, total_gops), 4),
        }


def compare_strategies(
    total_gops: int,
    intervals: List[int] = None,
) -> List[dict]:
    """对比不同固定间隔的锚定成本。"""
    if intervals is None:
        intervals = [1, 2, 5, 10, 20, 50]

    results = []
    for interval in intervals:
        anchor = FixedAnchor(interval=interval)
        cost = anchor.get_cost(total_gops)
        results.append(cost)
    return results
