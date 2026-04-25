#!/usr/bin/env bash
set -euo pipefail

FABRIC_SAMPLES_PATH="${FABRIC_SAMPLES_PATH:-$HOME/projects/fabric-samples}"
TEST_NETWORK_DIR="${FABRIC_SAMPLES_PATH}/test-network"
CHANNEL_NAME="${CHANNEL_NAME:-mychannel}"
CHAINCODE_NAME="${CHAINCODE_NAME:-evidence}"

ORDERER_CA="${TEST_NETWORK_DIR}/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem"
ORG1_CA="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem"
ORG2_CA="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem"
ORG3_CA="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org3.example.com/tlsca/tlsca.org3.example.com-cert.pem"

export PATH="${FABRIC_SAMPLES_PATH}/bin:${PATH}"
export FABRIC_CFG_PATH="${FABRIC_SAMPLES_PATH}/config"
export CORE_PEER_TLS_ENABLED=true

RUN_ID="${RUN_ID:-$(date +%s)}"
KEY_SINGLE_FAIL="stage3_acl_fail_${RUN_ID}"
KEY_OK="stage3_acl_ok_${RUN_ID}"
KEY_ORG3_FAIL="stage3_org3_acl_fail_${RUN_ID}"

set_org1() {
  export CORE_PEER_LOCALMSPID=Org1MSP
  export CORE_PEER_ADDRESS=localhost:7051
  export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
}

set_org2() {
  export CORE_PEER_LOCALMSPID=Org2MSP
  export CORE_PEER_ADDRESS=localhost:9051
  export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp"
}

set_org3() {
  export CORE_PEER_LOCALMSPID=Org3MSP
  export CORE_PEER_ADDRESS=localhost:11051
  export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt"
  export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp"
}

echo "[STEP] Org1 single-endorser invoke should fail..."
set_org1
set +e
peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "${ORDERER_CA}" \
  -C "${CHANNEL_NAME}" -n "${CHAINCODE_NAME}" \
  --peerAddresses localhost:7051 --tlsRootCertFiles "${ORG1_CA}" \
  --waitForEvent --waitForEventTimeout 10s \
  -c "{\"function\":\"CreateEvidence\",\"Args\":[\"${KEY_SINGLE_FAIL}\",\"cam_stage3\",\"detection_test\",\"1\",\"abcdef\",\"file://${KEY_SINGLE_FAIL}.json\"]}" >/tmp/stage3_acl_fail.out 2>&1
res=$?
set -e
if [[ ${res} -eq 0 ]]; then
  echo "[ERR] Expected endorsement failure, but invoke succeeded."
  cat /tmp/stage3_acl_fail.out
  exit 1
fi
echo "[OK] Single-endorser invoke failed as expected."

echo "[STEP] Org1+Org2 endorsed invoke should succeed..."
set_org1
peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "${ORDERER_CA}" \
  -C "${CHANNEL_NAME}" -n "${CHAINCODE_NAME}" \
  --peerAddresses localhost:7051 --tlsRootCertFiles "${ORG1_CA}" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "${ORG2_CA}" \
  --waitForEvent --waitForEventTimeout 20s \
  -c "{\"function\":\"CreateEvidence\",\"Args\":[\"${KEY_OK}\",\"cam_stage3\",\"detection_test\",\"1\",\"abcdef\",\"file://${KEY_OK}.json\"]}"
echo "[OK] Dual-endorser invoke succeeded."

echo "[STEP] Org3 independent query check..."
set_org3
peer chaincode query -C "${CHANNEL_NAME}" -n "${CHAINCODE_NAME}" -c "{\"function\":\"ReadEvidence\",\"Args\":[\"${KEY_OK}\"]}"
echo "[OK] Org3 query succeeded."

echo "[STEP] Org3 write attempt with dual endorsers should fail by ACL..."
set_org3
set +e
peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "${ORDERER_CA}" \
  -C "${CHANNEL_NAME}" -n "${CHAINCODE_NAME}" \
  --peerAddresses localhost:7051 --tlsRootCertFiles "${ORG1_CA}" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "${ORG2_CA}" \
  --waitForEvent --waitForEventTimeout 15s \
  -c "{\"function\":\"CreateEvidence\",\"Args\":[\"${KEY_ORG3_FAIL}\",\"cam_stage3\",\"detection_test\",\"1\",\"abcdef\",\"file://${KEY_ORG3_FAIL}.json\"]}" >/tmp/stage3_org3_acl_fail.out 2>&1
res=$?
set -e
if [[ ${res} -eq 0 ]]; then
  echo "[ERR] Expected ACL failure for Org3 write, but invoke succeeded."
  cat /tmp/stage3_org3_acl_fail.out
  exit 1
fi
echo "[OK] Org3 write denied as expected."

echo "[STEP] PDC write by Org1/Org2 should succeed..."
img_payload="stage3-private-image"
img_b64="$(printf '%s' "${img_payload}" | base64)"
img_sha="$(printf '%s' "${img_payload}" | shasum -a 256 | awk '{print $1}')"
set_org1
peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls --cafile "${ORDERER_CA}" \
  -C "${CHANNEL_NAME}" -n "${CHAINCODE_NAME}" \
  --peerAddresses localhost:7051 --tlsRootCertFiles "${ORG1_CA}" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "${ORG2_CA}" \
  --waitForEvent --waitForEventTimeout 20s \
  -c "{\"function\":\"PutRawEvidencePrivate\",\"Args\":[\"${KEY_OK}\",\"${img_b64}\",\"image/jpeg\",\"${img_sha}\"]}"
echo "[OK] PDC write succeeded."

echo "[STEP] Org3 should read hash metadata but not private raw..."
set_org3
peer chaincode query -C "${CHANNEL_NAME}" -n "${CHAINCODE_NAME}" -c "{\"function\":\"GetRawEvidenceHash\",\"Args\":[\"${KEY_OK}\"]}"
set +e
peer chaincode query -C "${CHANNEL_NAME}" -n "${CHAINCODE_NAME}" -c "{\"function\":\"GetRawEvidencePrivate\",\"Args\":[\"${KEY_OK}\"]}" >/tmp/stage3_org3_private_fail.out 2>&1
res=$?
set -e
if [[ ${res} -eq 0 ]]; then
  echo "[ERR] Expected Org3 private-read denial, but query succeeded."
  cat /tmp/stage3_org3_private_fail.out
  exit 1
fi
echo "[OK] Org3 private-read denied as expected."

echo "[DONE] stage3 verification baseline passed."
