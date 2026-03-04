#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FABRIC_SAMPLES_PATH="${FABRIC_SAMPLES_PATH:-$HOME/projects/fabric-samples}"
TEST_NETWORK_DIR="${FABRIC_SAMPLES_PATH}/test-network"
ADD_ORG3_DIR="${TEST_NETWORK_DIR}/addOrg3"
CHANNEL_NAME="${CHANNEL_NAME:-mychannel}"

on_error() {
  local exit_code=$?
  local failed_cmd="${BASH_COMMAND:-unknown}"
  echo "[ERR] stage3_setup_network failed (exit=${exit_code})."
  echo "[ERR] failed command: ${failed_cmd}"
  echo "[HINT] Run './network.sh down' under ${TEST_NETWORK_DIR} to clean up and retry."
  exit "${exit_code}"
}

trap on_error ERR

if [[ ! -d "${TEST_NETWORK_DIR}" ]]; then
  echo "[ERR] test-network not found: ${TEST_NETWORK_DIR}"
  exit 1
fi

echo "[INFO] Using test-network: ${TEST_NETWORK_DIR}"
echo "[INFO] Channel: ${CHANNEL_NAME}"

cd "${TEST_NETWORK_DIR}"
./network.sh down
./network.sh up createChannel -c "${CHANNEL_NAME}" -ca

if [[ ! -d "${ADD_ORG3_DIR}" ]]; then
  echo "[ERR] addOrg3 directory not found: ${ADD_ORG3_DIR}"
  exit 1
fi

cd "${ADD_ORG3_DIR}"
./addOrg3.sh up -c "${CHANNEL_NAME}" -ca

cd "${FABRIC_SAMPLES_PATH}"
export PATH="${FABRIC_SAMPLES_PATH}/bin:${PATH}"
export FABRIC_CFG_PATH="${FABRIC_SAMPLES_PATH}/config"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org3MSP
export CORE_PEER_ADDRESS=localhost:11051
export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org3.example.com/peers/peer0.org3.example.com/tls/ca.crt"
export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK_DIR}/organizations/peerOrganizations/org3.example.com/users/Admin@org3.example.com/msp"

echo "[INFO] Verifying Org3 joined channel..."
peer channel getinfo -c "${CHANNEL_NAME}" >/dev/null
echo "[OK] Org3 joined ${CHANNEL_NAME}"

cat <<EOF

[NEXT]
Deploy chaincode with stage3 policy:
cd ${TEST_NETWORK_DIR}
./network.sh deployCC \\
  -ccn evidence \\
  -ccp ${ROOT_DIR}/chaincode \\
  -ccl go \\
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \\
  -cccg ${ROOT_DIR}/chaincode/collections_config.json
EOF
