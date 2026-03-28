"""
Perceptual Hash Service

Computes perceptual hashes (pHash) from video keyframes to enable content-based
similarity detection. Used for tri-state verification to distinguish between
legitimate re-encoding and malicious tampering.
"""

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)

_LSH_INPUT_DIM = 576
_LSH_HASH_BITS = 64
_LSH_SEED = 42

_deep_hasher: Optional["DeepPerceptualHasher"] = None
_lsh_compressor: Optional["LSHCompressor"] = None
_singleton_lock = threading.Lock()


class DeepPerceptualHasher:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model: Optional[torch.nn.Module] = None
        self._transform = None
        self._model_lock = threading.Lock()

    def _load_model(self) -> torch.nn.Module:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from torchvision import transforms
                    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

                    weights = MobileNet_V3_Small_Weights.DEFAULT
                    model = mobilenet_v3_small(weights=weights)
                    model.classifier = torch.nn.Identity()
                    model.eval()
                    model.to(self.device)

                    self._transform = transforms.Compose([
                        transforms.Resize((224, 224)),
                        transforms.ToTensor(),
                        transforms.Normalize(
                            mean=[0.485, 0.456, 0.406],
                            std=[0.229, 0.224, 0.225],
                        ),
                    ])
                    self._model = model
                    logger.info("Deep perceptual hasher loaded on %s", self.device)
        return self._model

    @torch.no_grad()
    def extract_visual_features(self, keyframe_frame: np.ndarray) -> Optional[dict]:
        """Extract both global (1x1) and local (2x2) spatial features."""
        pil_image = _frame_to_pil_image(keyframe_frame)
        if pil_image is None:
            return None

        try:
            model = self._load_model()
            tensor = self._transform(pil_image).unsqueeze(0).to(self.device)
            with self._model_lock:
                features_map = model.features(tensor)
            
            # Global Average Pooling
            gap = features_map.mean(dim=[2, 3]).squeeze(0)
            global_vec = gap.detach().cpu().numpy().astype(np.float64)
            # L2 Normalize precisely
            gnorm = np.linalg.norm(global_vec)
            if gnorm > 1e-8:
                global_vec = global_vec / gnorm
                
            # Local 2x2 Grid using AdaptiveAvgPool2d
            grid = torch.nn.functional.adaptive_avg_pool2d(features_map, (2, 2)).squeeze(0)
            local_vecs = []
            for i in range(2):
                for j in range(2):
                    vec = grid[:, i, j].detach().cpu().numpy().astype(np.float64)
                    lnorm = np.linalg.norm(vec)
                    if lnorm > 1e-8:
                        vec = vec / lnorm
                    local_vecs.append(vec)
                    
            # Ensure pad or truncate to _LSH_INPUT_DIM
            def fix_dim(v):
                if v.shape[0] >= _LSH_INPUT_DIM:
                    return v[:_LSH_INPUT_DIM]
                return np.pad(v, (0, _LSH_INPUT_DIM - v.shape[0]))
                
            return {
                "global": fix_dim(global_vec),
                "local": [fix_dim(v) for v in local_vecs]
            }
        except Exception as e:
            logger.warning("visual feature extraction failed: %s", e)
            return None


class LSHCompressor:
    def __init__(
        self,
        input_dim: int = _LSH_INPUT_DIM,
        hash_bits: int = _LSH_HASH_BITS,
        seed: int = _LSH_SEED,
        projection_matrix: Optional[np.ndarray] = None,
    ):
        self.input_dim = input_dim
        self.hash_bits = hash_bits
        self.seed = seed

        if projection_matrix is None:
            rng = np.random.RandomState(seed)
            self.projection_matrix = rng.randn(hash_bits, input_dim).astype(np.float64)
        else:
            matrix = np.asarray(projection_matrix, dtype=np.float64)
            expected_shape = (hash_bits, input_dim)
            if matrix.shape != expected_shape:
                raise ValueError(
                    f"projection matrix shape must be {expected_shape}, got {matrix.shape}"
                )
            self.projection_matrix = matrix

    def hash_vector(self, feature: np.ndarray) -> str:
        vector = np.asarray(feature, dtype=np.float64).reshape(-1)
        if vector.shape != (self.input_dim,):
            raise ValueError(f"feature vector must have shape ({self.input_dim},), got {vector.shape}")

        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            bits = (self.projection_matrix @ vector) > 0
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)
        return f"{value:016x}"
def _frame_to_pil_image(keyframe_frame: np.ndarray) -> Optional[Image.Image]:
    if keyframe_frame is None:
        logger.warning("compute_phash: keyframe_frame is None")
        return None

    if not isinstance(keyframe_frame, np.ndarray):
        logger.warning("compute_phash: invalid type %s", type(keyframe_frame))
        return None

    if keyframe_frame.size == 0:
        logger.warning("compute_phash: empty array")
        return None

    if len(keyframe_frame.shape) != 3 or keyframe_frame.shape[2] != 3:
        logger.warning("compute_phash: unexpected shape %s", keyframe_frame.shape)
        return None

    rgb_array = keyframe_frame[:, :, ::-1]
    return Image.fromarray(rgb_array, mode="RGB")


def _get_deep_hasher() -> DeepPerceptualHasher:
    global _deep_hasher
    if _deep_hasher is None:
        with _singleton_lock:
            if _deep_hasher is None:
                _deep_hasher = DeepPerceptualHasher()
    return _deep_hasher


def _get_lsh_compressor() -> LSHCompressor:
    global _lsh_compressor
    if _lsh_compressor is None:
        with _singleton_lock:
            if _lsh_compressor is None:
                _lsh_compressor = LSHCompressor()
    return _lsh_compressor


def _compute_deep_phash(keyframe_frame: np.ndarray) -> str:
    """内部特征提取机制（深度学习版）"""
    feats = _get_deep_hasher().extract_visual_features(keyframe_frame)
    if feats is None or "global" not in feats:
        return "0000000000000000"
    feature = feats["global"]

    try:
        return _get_lsh_compressor().hash_vector(feature)
    except Exception as e:
        logger.warning("deep compute_phash failed: %s", e)
        return "0000000000000000"


def compute_phash(keyframe_frame: np.ndarray) -> Optional[str]:
    """
    Compute perceptual hash from a keyframe numpy array.

    Args:
        keyframe_frame: BGR24 numpy array (height, width, 3) from OpenCV/av

    Returns:
        64-bit pHash as hexadecimal string, or None if computation fails
    """
    return _compute_deep_phash(keyframe_frame)


def _parse_hash_value(hash_value: str) -> int:
    if not hash_value:
        raise ValueError("Hash values cannot be None or empty")

    if not isinstance(hash_value, str):
        raise ValueError("Hash values must be hexadecimal strings")

    normalized = hash_value.strip().lower()
    if len(normalized) != 16 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError(f"Invalid hash format: {hash_value}")

    return int(normalized, 16)


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculate Hamming distance between two perceptual hashes.

    Args:
        hash1: First pHash as hex string
        hash2: Second pHash as hex string

    Returns:
        Number of differing bits (0-64 for 64-bit pHash)

    Raises:
        ValueError: If hash format is invalid
    """
    value1 = _parse_hash_value(hash1)
    value2 = _parse_hash_value(hash2)
    return (value1 ^ value2).bit_count()
