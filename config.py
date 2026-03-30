import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # Keep working even if python-dotenv is not installed.
    pass


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    token = value.strip().lower()
    if token in {"1", "true", "yes", "y", "on"}:
        return True
    if token in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env_int_list(name: str, default: List[int]) -> List[int]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return list(default)

    parsed: List[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            parsed.append(int(token))
        except ValueError:
            continue

    return parsed if parsed else list(default)


def _env_str_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return list(default)
    parsed = [token.strip() for token in raw.split(",") if token.strip()]
    return parsed if parsed else list(default)


@dataclass(frozen=True)
class Settings:
    fabric_samples_path: Path
    evidence_dir: Path
    camera_id: str
    channel_name: str
    chaincode_name: str
    core_peer_tls_enabled: str
    core_peer_local_mspid: str
    core_peer_address: str
    orderer_address: str
    orderer_tls_hostname_override: str
    org1_peer_address: str
    org2_peer_address: str
    org3_peer_address: str
    org1_domain: str
    org2_domain: str
    org3_domain: str
    orderer_org_domain: str
    orderer_domain: str
    video_source: str
    model_candidates: List[str]
    detect_default_model: str

    aggregate_min_frames: int
    aggregate_max_missed_frames: int
    aggregate_iou_threshold: float
    aggregate_window_seconds: float

    merkle_batch_window_seconds: int
    merkle_flush_poll_seconds: float

    confidence_threshold: float
    road_target_class_ids: List[int]

    detect_confidence_threshold: float
    detect_save_every: int
    detect_output_dir: str
    detect_imgsz: int
    detect_reconnect_every: int
    detect_retry_sleep: float
    detect_reconnect_sleep: float

    device_cert_path: Path
    device_key_path: Path
    device_sign_algo: str
    device_signature_required: bool

    # IPFS 去中心化存储
    ipfs_api_url: str
    ipfs_gateway_url: str
    ipfs_pin_enabled: bool

    # Perceptual hash verification
    phash_hamming_threshold: int

    # Semantic fingerprint configuration
    semantic_model_path: str
    semantic_confidence: float
    vif_version: str
    vif_sample_frames: int


def load_settings() -> Settings:
    default_fabric_samples = str(Path.home() / "projects" / "fabric-samples")
    default_evidence_dir = "evidences"

    return Settings(
        fabric_samples_path=Path(_env_str("FABRIC_SAMPLES_PATH", default_fabric_samples)).expanduser().resolve(),
        evidence_dir=Path(_env_str("EVIDENCE_DIR", default_evidence_dir)).expanduser().resolve(),
        camera_id=_env_str("CAMERA_ID", "cctv-kctmc-apple-01"),
        channel_name=_env_str("CHANNEL_NAME", "mychannel"),
        chaincode_name=_env_str("CHAINCODE_NAME", "evidence"),
        core_peer_tls_enabled=_env_str("CORE_PEER_TLS_ENABLED", "true"),
        core_peer_local_mspid=_env_str("CORE_PEER_LOCALMSPID", "Org1MSP"),
        core_peer_address=_env_str("CORE_PEER_ADDRESS", "localhost:7051"),
        orderer_address=_env_str("ORDERER_ADDRESS", "localhost:7050"),
        orderer_tls_hostname_override=_env_str(
            "ORDERER_TLS_HOSTNAME_OVERRIDE", "orderer.example.com"
        ),
        org1_peer_address=_env_str("ORG1_PEER_ADDRESS", "localhost:7051"),
        org2_peer_address=_env_str("ORG2_PEER_ADDRESS", "localhost:9051"),
        org3_peer_address=_env_str("ORG3_PEER_ADDRESS", "localhost:11051"),
        org1_domain=_env_str("ORG1_DOMAIN", "org1.example.com"),
        org2_domain=_env_str("ORG2_DOMAIN", "org2.example.com"),
        org3_domain=_env_str("ORG3_DOMAIN", "org3.example.com"),
        orderer_org_domain=_env_str("ORDERER_ORG_DOMAIN", "example.com"),
        orderer_domain=_env_str("ORDERER_DOMAIN", "orderer.example.com"),
        video_source=_env_str("VIDEO_SOURCE", "https://cctv1.kctmc.nat.gov.tw/6e559e58/"),
        model_candidates=_env_str_list("MODEL_CANDIDATES", ["yolo11n.pt", "yolo11m.pt", "yolo11x.pt"]),
        detect_default_model=_env_str("DETECT_MODEL", "yolo11n.pt"),
        aggregate_min_frames=_env_int("AGGREGATE_MIN_FRAMES", 3),
        aggregate_max_missed_frames=_env_int("AGGREGATE_MAX_MISSED_FRAMES", 6),
        aggregate_iou_threshold=_env_float("AGGREGATE_IOU_THRESHOLD", 0.45),
        aggregate_window_seconds=_env_float("AGGREGATE_WINDOW_SECONDS", 5.0),
        merkle_batch_window_seconds=_env_int("MERKLE_BATCH_WINDOW_SECONDS", 60),
        merkle_flush_poll_seconds=_env_float("MERKLE_FLUSH_POLL_SECONDS", 1.0),
        confidence_threshold=_env_float("CONFIDENCE_THRESHOLD", 0.45),
        road_target_class_ids=_env_int_list("ROAD_TARGET_CLASS_IDS", [0, 1, 2, 3, 5, 7]),
        detect_confidence_threshold=_env_float("DETECT_CONFIDENCE_THRESHOLD", 0.25),
        detect_save_every=_env_int("DETECT_SAVE_EVERY", 10),
        detect_output_dir=_env_str("DETECT_OUTPUT_DIR", default_evidence_dir),
        detect_imgsz=_env_int("DETECT_IMGSZ", 1280),
        detect_reconnect_every=_env_int("DETECT_RECONNECT_EVERY", 20),
        detect_retry_sleep=_env_float("DETECT_RETRY_SLEEP", 0.2),
        detect_reconnect_sleep=_env_float("DETECT_RECONNECT_SLEEP", 1.0),
        device_cert_path=Path(_env_str("DEVICE_CERT_PATH", "device_keys/default/cert.pem")).expanduser().resolve(),
        device_key_path=Path(_env_str("DEVICE_KEY_PATH", "device_keys/default/key.pem")).expanduser().resolve(),
        device_sign_algo=_env_str("DEVICE_SIGN_ALGO", "ECDSA_SHA256"),
        device_signature_required=_env_bool("DEVICE_SIGNATURE_REQUIRED", True),
        ipfs_api_url=_env_str("IPFS_API_URL", "http://localhost:5001"),
        ipfs_gateway_url=_env_str("IPFS_GATEWAY_URL", "http://localhost:8080"),
        ipfs_pin_enabled=_env_bool("IPFS_PIN_ENABLED", True),
        phash_hamming_threshold=_env_int("PHASH_HAMMING_THRESHOLD", 10),
        semantic_model_path=_env_str("SEMANTIC_MODEL_PATH", "yolov8n.pt"),
        semantic_confidence=_env_float("SEMANTIC_CONFIDENCE", 0.5),
        vif_version=_env_str("VIF_VERSION", "v4"),
        vif_sample_frames=_env_int("VIF_SAMPLE_FRAMES", 1),
    )


SETTINGS = load_settings()
