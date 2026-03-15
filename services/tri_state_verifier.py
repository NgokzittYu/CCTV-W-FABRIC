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
