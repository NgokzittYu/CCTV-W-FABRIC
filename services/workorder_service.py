"""Workorder and audit trail service for violation management."""
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import SETTINGS
from services.fabric_client import build_fabric_env, invoke_chaincode, query_chaincode


def create_workorder(
    violation_id: str,
    description: str,
    assigned_org: str,
    deadline: int,
) -> Dict[str, Any]:
    """Create a new rectification workorder (Org2 only)."""
    order_id = f"order_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

    # Save Org1 TLS cert path before overriding
    org1_tls_cert = env["CORE_PEER_TLS_ROOTCERT_FILE"]

    # Override to use Org2 MSP identity
    org2_path = fabric_samples / "test-network" / "organizations" / "peerOrganizations" / "org2.example.com"
    env["CORE_PEER_LOCALMSPID"] = "Org2MSP"
    env["CORE_PEER_ADDRESS"] = "localhost:9051"
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = org1_tls_cert
    env["CORE_PEER_MSPCONFIGPATH"] = str(org2_path / "users" / "Admin@org2.example.com" / "msp")

    args = [order_id, violation_id, assigned_org, str(deadline), description]

    invoke_res = invoke_chaincode(
        env,
        orderer_ca,
        org2_tls,
        SETTINGS.channel_name,
        SETTINGS.chaincode_name,
        "CreateRectificationOrder",
        args,
    )

    return {
        "status": "success",
        "orderId": order_id,
        "txId": invoke_res.get("tx_id", ""),
        "message": "Workorder created successfully",
    }


def submit_rectification(order_id: str, rectification_proof: str, attachments: List[str]) -> Dict[str, Any]:
    """Submit rectification proof (Org1 only)."""
    attachment_url = ",".join(attachments) if attachments else rectification_proof

    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

    args = [order_id, attachment_url, rectification_proof]

    invoke_res = invoke_chaincode(
        env,
        orderer_ca,
        org2_tls,
        SETTINGS.channel_name,
        SETTINGS.chaincode_name,
        "SubmitRectification",
        args,
    )

    return {
        "status": "success",
        "orderId": order_id,
        "txId": invoke_res.get("tx_id", ""),
        "message": "Rectification submitted successfully",
    }


def confirm_rectification(order_id: str, approved: bool, comments: str) -> Dict[str, Any]:
    """Confirm or reject rectification (Org2 only)."""
    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

    # Save Org1 TLS cert path before overriding
    org1_tls_cert = env["CORE_PEER_TLS_ROOTCERT_FILE"]

    # Override to use Org2 MSP identity
    org2_path = fabric_samples / "test-network" / "organizations" / "peerOrganizations" / "org2.example.com"
    env["CORE_PEER_LOCALMSPID"] = "Org2MSP"
    env["CORE_PEER_ADDRESS"] = "localhost:9051"
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = org1_tls_cert
    env["CORE_PEER_MSPCONFIGPATH"] = str(org2_path / "users" / "Admin@org2.example.com" / "msp")

    args = [order_id, str(approved).lower(), comments]

    invoke_res = invoke_chaincode(
        env,
        orderer_ca,
        org2_tls,
        SETTINGS.channel_name,
        SETTINGS.chaincode_name,
        "ConfirmRectification",
        args,
    )

    return {
        "status": "success",
        "orderId": order_id,
        "approved": approved,
        "txId": invoke_res.get("tx_id", ""),
        "message": f"Workorder {'approved' if approved else 'rejected'} successfully",
    }


def query_overdue_workorders(org: Optional[str] = None, page: int = 1, limit: int = 20) -> Dict[str, Any]:
    """Query overdue workorders via chaincode QueryOverdueOrders."""
    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

    result = query_chaincode(
        env,
        SETTINGS.channel_name,
        SETTINGS.chaincode_name,
        "QueryOverdueOrders",
        [],
    )

    all_orders: list = json.loads(result) if result else []

    if org:
        all_orders = [o for o in all_orders if o.get("assignedTo") == org or o.get("createdBy") == org]

    total = len(all_orders)
    offset = (page - 1) * limit
    paged = all_orders[offset: offset + limit]

    return {
        "status": "success",
        "data": paged,
        "page": page,
        "limit": limit,
        "total": total,
    }


def query_workorder_by_id(order_id: str) -> Dict[str, Any]:
    """Query workorder by ID."""
    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

    result = query_chaincode(
        env,
        SETTINGS.channel_name,
        SETTINGS.chaincode_name,
        "ReadRectificationOrder",
        [order_id],
    )

    return json.loads(result) if result else {}


def export_audit_trail(batch_id: str) -> Dict[str, Any]:
    """Export audit trail for a batch."""
    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

    result = query_chaincode(
        env,
        SETTINGS.channel_name,
        SETTINGS.chaincode_name,
        "ExportAuditTrail",
        [batch_id],
    )

    return json.loads(result) if result else {}


def auto_trigger_workorder(
    batch_id: str,
    event_count: int,
    violation_level: str = "high",
    auto_create_enabled: bool = True,
    trigger_rules: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """Automatically create workorder for violation events."""
    if not auto_create_enabled:
        return None

    if trigger_rules is None:
        trigger_rules = []

    rule = None
    for r in trigger_rules:
        if r.get("violation_level") == violation_level:
            rule = r
            break

    if not rule:
        print(f"[AUTO-WORKORDER] No rule found for violation level: {violation_level}")
        return None

    try:
        order_id = f"order_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        deadline = int(time.time()) + (rule.get("default_deadline_days", 7) * 24 * 3600)
        description = f"自动创建：检测到 {event_count} 个违规事件，批次 {batch_id}，需要整改"

        fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
        env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

        org1_tls_cert = env["CORE_PEER_TLS_ROOTCERT_FILE"]

        org2_path = fabric_samples / "test-network" / "organizations" / "peerOrganizations" / "org2.example.com"
        env["CORE_PEER_LOCALMSPID"] = "Org2MSP"
        env["CORE_PEER_ADDRESS"] = "localhost:9051"
        env["CORE_PEER_TLS_ROOTCERT_FILE"] = org1_tls_cert
        env["CORE_PEER_MSPCONFIGPATH"] = str(org2_path / "users" / "Admin@org2.example.com" / "msp")

        args = [
            order_id,
            batch_id,
            rule.get("auto_assign_org", "Org1MSP"),
            str(deadline),
            description,
        ]

        invoke_chaincode(
            env,
            orderer_ca,
            org2_tls,
            SETTINGS.channel_name,
            SETTINGS.chaincode_name,
            "CreateRectificationOrder",
            args,
        )

        print(f"[AUTO-WORKORDER] Created workorder {order_id} for batch {batch_id}")
        return order_id
    except Exception as e:
        print(f"[DER] Failed to create workorder: {e}")
        return None
