"""Hyperledger Fabric chaincode interaction client."""
import base64
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import SETTINGS


def run(cmd: List[str], env: Optional[Dict[str, str]] = None, check: bool = True):
    """Execute subprocess command."""
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def build_fabric_env(fabric_samples: Path) -> Tuple[Dict[str, str], Path, Path]:
    """Build Fabric environment variables and return orderer/org2 TLS paths."""
    env = os.environ.copy()
    env["PATH"] = f"{fabric_samples / 'bin'}:{env.get('PATH', '')}"
    env["FABRIC_CFG_PATH"] = str(fabric_samples / "config")

    env["CORE_PEER_TLS_ENABLED"] = SETTINGS.core_peer_tls_enabled
    env["CORE_PEER_LOCALMSPID"] = SETTINGS.core_peer_local_mspid
    env["CORE_PEER_ADDRESS"] = SETTINGS.core_peer_address

    org1 = (
        fabric_samples / "test-network" / "organizations" / "peerOrganizations" / SETTINGS.org1_domain
    )
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = str(
        org1 / "peers" / f"peer0.{SETTINGS.org1_domain}" / "tls" / "ca.crt"
    )
    env["CORE_PEER_MSPCONFIGPATH"] = str(
        org1 / "users" / f"Admin@{SETTINGS.org1_domain}" / "msp"
    )

    orderer_ca = (
        fabric_samples / "test-network" / "organizations" / "ordererOrganizations"
        / SETTINGS.orderer_org_domain / "orderers" / SETTINGS.orderer_domain
        / "msp" / "tlscacerts" / f"tlsca.{SETTINGS.orderer_org_domain}-cert.pem"
    )
    org2_tls = (
        fabric_samples / "test-network" / "organizations" / "peerOrganizations"
        / SETTINGS.org2_domain / "peers" / f"peer0.{SETTINGS.org2_domain}" / "tls" / "ca.crt"
    )

    return env, orderer_ca, org2_tls


def query_chaincode(
    env: Dict[str, str],
    channel: str,
    chaincode: str,
    function_name: str,
    args: List[str],
) -> str:
    """Query chaincode function."""
    cmd = [
        "peer", "chaincode", "query",
        "-C", channel, "-n", chaincode,
        "-c", json.dumps({"function": function_name, "Args": args}, ensure_ascii=False),
    ]
    proc = run(cmd, env=env, check=True)
    return (proc.stdout or "").strip()


def _encode_transient_map(transient_map: Optional[Dict[str, Any]]) -> Optional[str]:
    """Encode transient map to base64 JSON."""
    if not transient_map:
        return None
    encoded: Dict[str, str] = {}
    for key, value in transient_map.items():
        if isinstance(value, bytes):
            raw = value
        elif isinstance(value, str):
            raw = value.encode("utf-8")
        else:
            raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encoded[key] = base64.b64encode(raw).decode("ascii")
    return json.dumps(encoded, ensure_ascii=False, separators=(",", ":"))


def invoke_chaincode(
    env: Dict[str, str],
    orderer_ca: Path,
    org2_tls: Path,
    channel: str,
    chaincode: str,
    function_name: str,
    args: List[str],
    transient_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Invoke chaincode function."""
    payload = json.dumps({"function": function_name, "Args": args}, ensure_ascii=False)
    cmd = [
        "peer", "chaincode", "invoke",
        "-o", SETTINGS.orderer_address,
        "--ordererTLSHostnameOverride", SETTINGS.orderer_tls_hostname_override,
        "--tls", "--cafile", str(orderer_ca),
        "-C", channel, "-n", chaincode,
        "--peerAddresses", SETTINGS.org1_peer_address,
        "--tlsRootCertFiles", env["CORE_PEER_TLS_ROOTCERT_FILE"],
        "--peerAddresses", SETTINGS.org2_peer_address,
        "--tlsRootCertFiles", str(org2_tls),
        "--waitForEvent", "--waitForEventTimeout", "30s",
        "-c", payload,
    ]

    transient_json = _encode_transient_map(transient_map)
    if transient_json:
        cmd.extend(["--transient", transient_json])

    proc = run(cmd, env=env, check=True)

    tx_id = ""
    tx_match = re.search(r"txid \[([0-9a-fA-F]+)\]", proc.stderr or "")
    if tx_match:
        tx_id = tx_match.group(1)

    return {"tx_id": tx_id, "stdout": proc.stdout, "stderr": proc.stderr}


def evidence_exists(env: Dict[str, str], channel: str, chaincode: str, evidence_id: str) -> bool:
    """Check if evidence exists on chain."""
    cmd = [
        "peer", "chaincode", "query",
        "-C", channel, "-n", chaincode,
        "-c", json.dumps({"function": "EvidenceExists", "Args": [evidence_id]}),
    ]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if proc.returncode == 0:
        return "true" in proc.stdout.lower()
    return False


def get_latest_block_number(env: Dict[str, str], channel: str) -> Optional[int]:
    """Get latest block number from channel."""
    cmd = ["peer", "channel", "getinfo", "-c", channel]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if proc.returncode != 0:
        return None

    out = (proc.stdout or "").strip()
    if "Blockchain info:" not in out:
        return None
    try:
        payload = out.split("Blockchain info:", 1)[1].strip()
        info = json.loads(payload)
        height = int(info.get("height", 0))
        if height <= 0:
            return None
        return height - 1
    except Exception:
        return None


def get_fabric_config():
    """Get Fabric configuration from settings."""
    return {
        "fabric_samples_path": str(SETTINGS.fabric_samples_path),
        "channel_name": SETTINGS.channel_name,
        "chaincode_name": SETTINGS.chaincode_name,
        "camera_id": SETTINGS.camera_id,
    }


# ---------------------------------------------------------------------------
# Anchor – GOP-level Merkle root anchoring
# ---------------------------------------------------------------------------


def submit_anchor(
    env: Dict[str, str],
    orderer_ca: Path,
    org2_tls: Path,
    channel: str,
    chaincode: str,
    epoch_id: str,
    merkle_root: str,
    timestamp: str,
    device_count: int,
) -> Dict[str, str]:
    """Submit a GOP-level Merkle root anchor to the blockchain."""
    args = [epoch_id, merkle_root, str(timestamp), str(device_count)]
    return invoke_chaincode(
        env, orderer_ca, org2_tls, channel, chaincode, "Anchor", args
    )


def query_anchor(
    env: Dict[str, str],
    channel: str,
    chaincode: str,
    epoch_id: str,
) -> str:
    """Query a single anchor record by epoch ID."""
    return query_chaincode(env, channel, chaincode, "QueryAnchor", [epoch_id])


def verify_anchor(
    env: Dict[str, str],
    orderer_ca: Path,
    org2_tls: Path,
    channel: str,
    chaincode: str,
    epoch_id: str,
    leaf_hash: str,
    proof_json: str,
) -> str:
    """Verify a GOP hash against an anchored Merkle root using a Merkle proof.

    Args:
        env: Fabric environment variables
        orderer_ca: Path to orderer CA certificate (not used for queries)
        org2_tls: Path to org2 TLS certificate (not used for queries)
        channel: Channel name
        chaincode: Chaincode name
        epoch_id: Epoch ID of the anchor
        leaf_hash: SHA-256 hash of the GOP (hex string)
        proof_json: JSON string of Merkle proof

    Returns:
        JSON string with verification result
    """
    args = [epoch_id, leaf_hash, proof_json]
    # Use query_chaincode instead of invoke_chaincode
    # Verification is read-only and doesn't modify state
    result = query_chaincode(env, channel, chaincode, "VerifyAnchor", args)
    return result


def query_anchors_by_range(
    env: Dict[str, str],
    channel: str,
    chaincode: str,
    start_key: str,
    end_key: str,
) -> str:
    """Query anchor records whose keys fall in [start_key, end_key)."""
    return query_chaincode(
        env, channel, chaincode, "QueryAnchorsByRange", [start_key, end_key]
    )
