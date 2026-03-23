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

import imagehash
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
                        transforms.Resize(256),
                        transforms.CenterCrop(224),
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
    def extract(self, keyframe_frame: np.ndarray) -> Optional[np.ndarray]:
        pil_image = _frame_to_pil_image(keyframe_frame)
        if pil_image is None:
            return None

        try:
            model = self._load_model()
            tensor = self._transform(pil_image).unsqueeze(0).to(self.device)
            with self._model_lock:
                features = model(tensor)
            features = torch.nn.functional.normalize(features, p=2, dim=1)
            vector = features.squeeze(0).detach().cpu().numpy().astype(np.float64)
            if vector.shape != (_LSH_INPUT_DIM,):
                logger.warning("deep feature dimension mismatch: %s", vector.shape)
                return None
            return vector
        except Exception as e:
            logger.warning("deep feature extraction failed: %s", e)
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

    def save_projection(self, filepath: str):
        np.save(filepath, self.projection_matrix)

    @classmethod
    def load_projection(
        cls,
        filepath: str,
        input_dim: int = _LSH_INPUT_DIM,
        hash_bits: int = _LSH_HASH_BITS,
        seed: int = _LSH_SEED,
    ) -> "LSHCompressor":
        path = Path(filepath)
        if not path.exists():
            return cls(input_dim=input_dim, hash_bits=hash_bits, seed=seed)

        try:
            matrix = np.load(path, allow_pickle=False)
            return cls(
                input_dim=input_dim,
                hash_bits=hash_bits,
                seed=seed,
                projection_matrix=matrix,
            )
        except Exception as e:
            logger.warning("failed to load projection matrix from %s: %s", filepath, e)
            return cls(input_dim=input_dim, hash_bits=hash_bits, seed=seed)


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


def _compute_legacy_phash(keyframe_frame: np.ndarray) -> Optional[str]:
    pil_image = _frame_to_pil_image(keyframe_frame)
    if pil_image is None:
        return None

    try:
        return str(imagehash.phash(pil_image, hash_size=8))
    except Exception as e:
        logger.warning("legacy compute_phash failed: %s", e)
        return None


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


def _compute_deep_phash(keyframe_frame: np.ndarray) -> Optional[str]:
    feature = _get_deep_hasher().extract(keyframe_frame)
    if feature is None:
        return None

    try:
        return _get_lsh_compressor().hash_vector(feature)
    except Exception as e:
        logger.warning("deep compute_phash failed: %s", e)
        return None


def compute_phash(keyframe_frame: np.ndarray) -> Optional[str]:
    """
    Compute perceptual hash from a keyframe numpy array.

    Args:
        keyframe_frame: BGR24 numpy array (height, width, 3) from OpenCV/av

    Returns:
        64-bit pHash as hexadecimal string, or None if computation fails
    """
    mode = os.getenv("PHASH_MODE", "legacy").strip().lower()
    if mode == "deep":
        return _compute_deep_phash(keyframe_frame)
    if mode != "legacy":
        logger.warning("unknown PHASH_MODE=%s, falling back to legacy", mode)
    return _compute_legacy_phash(keyframe_frame)


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
