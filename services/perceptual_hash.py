"""
Perceptual Hash Service

Computes perceptual hashes (pHash) from video keyframes to enable content-based
similarity detection. Used for tri-state verification to distinguish between
legitimate re-encoding and malicious tampering.
"""

import logging
from typing import Optional

import imagehash
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def compute_phash(keyframe_frame: np.ndarray) -> Optional[str]:
    """
    Compute perceptual hash from a keyframe numpy array.

    Args:
        keyframe_frame: BGR24 numpy array (height, width, 3) from OpenCV/av

    Returns:
        64-bit pHash as hexadecimal string, or None if computation fails

    Note:
        - Input is BGR format (OpenCV convention), converted to RGB for PIL
        - Uses 8x8 DCT-based perceptual hash (64 bits)
        - Thread safety: PIL operations are NOT thread-safe, use locks if needed
    """
    if keyframe_frame is None:
        logger.warning("compute_phash: keyframe_frame is None")
        return None

    if not isinstance(keyframe_frame, np.ndarray):
        logger.warning(f"compute_phash: invalid type {type(keyframe_frame)}")
        return None

    if keyframe_frame.size == 0:
        logger.warning("compute_phash: empty array")
        return None

    try:
        # Convert BGR to RGB (OpenCV uses BGR, PIL expects RGB)
        if len(keyframe_frame.shape) == 3 and keyframe_frame.shape[2] == 3:
            rgb_array = keyframe_frame[:, :, ::-1]
        else:
            logger.warning(f"compute_phash: unexpected shape {keyframe_frame.shape}")
            return None

        # Create PIL Image
        pil_image = Image.fromarray(rgb_array, mode='RGB')

        # Compute pHash (8x8 = 64 bits)
        phash = imagehash.phash(pil_image, hash_size=8)

        # Return as hex string
        return str(phash)

    except Exception as e:
        logger.warning(f"compute_phash failed: {e}")
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculate Hamming distance between two perceptual hashes.

    Args:
        hash1: First pHash as hex string
        hash2: Second pHash as hex string

    Returns:
        Number of differing bits (0-64 for 8x8 pHash)

    Raises:
        ValueError: If hash format is invalid
    """
    if not hash1 or not hash2:
        raise ValueError("Hash values cannot be None or empty")

    try:
        # Convert hex strings to ImageHash objects
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)

        # Calculate Hamming distance using imagehash's built-in operator
        distance = h1 - h2

        return distance

    except Exception as e:
        raise ValueError(f"Invalid hash format: {e}")
