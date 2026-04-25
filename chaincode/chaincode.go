package main

import (
	"crypto/ecdsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/asn1"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"math/big"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

const (
	org1MSP = "Org1MSP"
	org2MSP = "Org2MSP"
	org3MSP = "Org3MSP"

	collectionRawEvidence = "collectionRawEvidence"
	rawEvidenceHashPrefix = "rawhash:"
	rectificationPrefix   = "rectify:"
	anchorPrefix          = "anchor:"
	anchorLastTsPrefix    = "anchor_last_ts:"
)

// EvidenceSmartContract provides functions for managing evidence assets.
type EvidenceSmartContract struct {
	contractapi.Contract
}

// Evidence describes one event evidence asset in world state.
type Evidence struct {
	ID           string `json:"id"`
	Timestamp    int64  `json:"timestamp"`
	CameraID     string `json:"cameraId"`
	Location     string `json:"location"`
	EventType    string `json:"eventType"`
	ObjectCount  int    `json:"objectCount"`
	EvidenceHash string `json:"evidenceHash"`
	RawDataURL   string `json:"rawDataUrl"`
}

// MerkleBatch stores one anchored Merkle root and its event window metadata.
type MerkleBatch struct {
	ID                  string   `json:"id"`
	MerkleRoot          string   `json:"merkleRoot"`
	CameraID            string   `json:"cameraId"`
	EventCount          int      `json:"eventCount"`
	EventIDs            []string `json:"eventIds"`
	EventVifs           []string `json:"eventVifs"`
	WindowStart         int64    `json:"windowStart"`
	WindowEnd           int64    `json:"windowEnd"`
	Timestamp           int64    `json:"timestamp"`
	PayloadHash         string   `json:"payloadHash"`
	Signature           string   `json:"signature"`
	DeviceCertSHA256    string   `json:"deviceCertSha256"`
	SignerMSP           string   `json:"signerMsp"`
	DeviceIdentityLabel string   `json:"deviceIdentityLabel"`
}

// MerkleProofStep describes one sibling hash in a Merkle proof.
type MerkleProofStep struct {
	Position string `json:"position"`
	Hash     string `json:"hash"`
}

// KeyHistory represents one historical modification for a key.
type KeyHistory struct {
	TxID      string `json:"txId"`
	Timestamp int64  `json:"timestamp"`
	IsDelete  bool   `json:"isDelete"`
	Value     string `json:"value"`
}

// RawEvidencePrivate is stored in private data collection.
type RawEvidencePrivate struct {
	EventID     string `json:"eventId"`
	ImageBase64 string `json:"imageBase64"`
	MimeType    string `json:"mimeType"`
	ImageSHA256 string `json:"imageSha256"`
	CameraID    string `json:"cameraId"`
	Timestamp   int64  `json:"timestamp"`
}

// RawEvidenceHash is public metadata for private raw evidence.
type RawEvidenceHash struct {
	EventID     string `json:"eventId"`
	ImageSHA256 string `json:"imageSha256"`
	CameraID    string `json:"cameraId"`
	Timestamp   int64  `json:"timestamp"`
	Collection  string `json:"collection"`
}

// RectificationHistoryEntry describes one state transition in rectification workflow.
type RectificationHistoryEntry struct {
	At      int64  `json:"at"`
	ByMSP   string `json:"byMsp"`
	Action  string `json:"action"`
	Comment string `json:"comment"`
}

// RectificationOrder models one remediation/rectification workflow order.
type RectificationOrder struct {
	ID          string                      `json:"id"`
	BatchID     string                      `json:"batchId"`
	CreatedBy   string                      `json:"createdBy"`
	AssignedTo  string                      `json:"assignedTo"`
	Status      string                      `json:"status"`
	Deadline    int64                       `json:"deadline"`
	Attachments []string                    `json:"attachments"`
	CreatedAt   int64                       `json:"createdAt"`
	UpdatedAt   int64                       `json:"updatedAt"`
	History     []RectificationHistoryEntry `json:"history"`
}

// AuditTrail is returned for cross-organization auditing.
type AuditTrail struct {
	Batch          *MerkleBatch          `json:"batch"`
	Events         []*Evidence           `json:"events"`
	Rectifications []*RectificationOrder `json:"rectifications"`
}

// AnchorRecord stores one GOP-level Merkle root anchor on-chain (lean storage).
type AnchorRecord struct {
	EpochId     string `json:"epochId"`
	MerkleRoot  string `json:"merkleRoot"`
	Timestamp   int64  `json:"timestamp"`
	DeviceCount int    `json:"deviceCount"`
	GatewayId   string `json:"gatewayId"`
}

type ecdsaSignature struct {
	R *big.Int
	S *big.Int
}

func rawEvidenceHashKey(eventID string) string {
	return rawEvidenceHashPrefix + eventID
}

func rectificationKey(orderID string) string {
	return rectificationPrefix + orderID
}

func (s *EvidenceSmartContract) getMSPID(ctx contractapi.TransactionContextInterface) (string, error) {
	ci := ctx.GetClientIdentity()
	if ci == nil {
		return "", fmt.Errorf("client identity is unavailable")
	}
	mspID, err := ci.GetMSPID()
	if err != nil {
		return "", fmt.Errorf("failed to get invoker MSP: %v", err)
	}
	return strings.TrimSpace(mspID), nil
}

func (s *EvidenceSmartContract) requireMSP(ctx contractapi.TransactionContextInterface, allowed ...string) (string, error) {
	mspID, err := s.getMSPID(ctx)
	if err != nil {
		return "", err
	}
	for _, a := range allowed {
		if strings.EqualFold(mspID, strings.TrimSpace(a)) {
			return mspID, nil
		}
	}
	sorted := append([]string{}, allowed...)
	sort.Strings(sorted)
	return "", fmt.Errorf("permission denied for MSP %s, allowed: %s", mspID, strings.Join(sorted, ","))
}

func canonicalBatchPayloadHash(batchID string, cameraID string, merkleRoot string, windowStart int64, windowEnd int64, eventIDs []string, eventHashes []string, eventVifs []string) (string, error) {
	payload := map[string]interface{}{
		"batchId":     batchID,
		"cameraId":    cameraID,
		"merkleRoot":  merkleRoot,
		"windowStart": windowStart,
		"windowEnd":   windowEnd,
		"eventIds":    eventIDs,
		"eventHashes": eventHashes,
		"eventVifs":   eventVifs,
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payloadJSON)
	return hex.EncodeToString(sum[:]), nil
}

func verifyDeviceSignature(deviceCertPEM string, signatureB64 string, payloadHashHex string, cameraID string) (string, string, error) {
	certPEM := strings.TrimSpace(deviceCertPEM)
	sigText := strings.TrimSpace(signatureB64)
	hashText := strings.ToLower(strings.TrimSpace(payloadHashHex))
	if certPEM == "" || sigText == "" || hashText == "" {
		return "", "", fmt.Errorf("device signature fields cannot be empty")
	}

	payloadHashBytes, err := hex.DecodeString(hashText)
	if err != nil {
		return "", "", fmt.Errorf("invalid payloadHashHex: %v", err)
	}

	block, _ := pem.Decode([]byte(certPEM))
	if block == nil {
		return "", "", fmt.Errorf("invalid device cert PEM")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return "", "", fmt.Errorf("failed to parse device cert: %v", err)
	}

	identityLabel := strings.TrimSpace(cert.Subject.CommonName)
	if identityLabel == "" {
		identityLabel = cert.Subject.String()
	}

	orgRef := strings.ToLower(cert.Subject.String() + "|" + cert.Issuer.String() + "|" + strings.Join(cert.DNSNames, ",") + "|" + strings.Join(cert.EmailAddresses, ","))
	if !strings.Contains(orgRef, "org1") {
		return "", "", fmt.Errorf("device cert is not scoped to Org1")
	}
	if strings.TrimSpace(cameraID) != "" {
		camRef := strings.ToLower(strings.TrimSpace(cameraID))
		if !strings.Contains(strings.ToLower(identityLabel), camRef) && !strings.Contains(orgRef, camRef) {
			return "", "", fmt.Errorf("device cert identity does not match cameraId %s", cameraID)
		}
	}

	sigBytes, err := base64.StdEncoding.DecodeString(sigText)
	if err != nil {
		return "", "", fmt.Errorf("invalid signatureB64: %v", err)
	}

	var sig ecdsaSignature
	rest, err := asn1.Unmarshal(sigBytes, &sig)
	if err != nil || len(rest) != 0 || sig.R == nil || sig.S == nil {
		return "", "", fmt.Errorf("invalid ECDSA ASN.1 signature")
	}

	pub, ok := cert.PublicKey.(*ecdsa.PublicKey)
	if !ok {
		return "", "", fmt.Errorf("device cert public key is not ECDSA")
	}
	if !ecdsa.Verify(pub, payloadHashBytes, sig.R, sig.S) {
		return "", "", fmt.Errorf("device signature verification failed")
	}

	fp := sha256.Sum256(cert.Raw)
	return hex.EncodeToString(fp[:]), identityLabel, nil
}

// InitLedger adds a base set of evidences to the ledger.
func (s *EvidenceSmartContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	evidences := []Evidence{
		{ID: "event_init_01", Timestamp: time.Now().Unix(), CameraID: "init_cam", EventType: "system_start", EvidenceHash: "init_hash", ObjectCount: 0},
	}

	for _, evidence := range evidences {
		assetJSON, err := json.Marshal(evidence)
		if err != nil {
			return err
		}

		err = ctx.GetStub().PutState(evidence.ID, assetJSON)
		if err != nil {
			return fmt.Errorf("failed to put to world state. %v", err)
		}
	}

	return nil
}

// CreateEvidence issues a new evidence to the world state with given details.
func (s *EvidenceSmartContract) CreateEvidence(ctx contractapi.TransactionContextInterface, id string, cameraID string, eventType string, objectCount int, evidenceHash string, rawDataURL string) error {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP); err != nil {
		return err
	}

	exists, err := s.EvidenceExists(ctx, id)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("the evidence %s already exists", id)
	}

	evidence := Evidence{
		ID:           id,
		Timestamp:    time.Now().Unix(),
		CameraID:     cameraID,
		EventType:    eventType,
		ObjectCount:  objectCount,
		EvidenceHash: strings.ToLower(strings.TrimSpace(evidenceHash)),
		RawDataURL:   rawDataURL,
		Location:     "default_location",
	}
	evidenceJSON, err := json.Marshal(evidence)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState(id, evidenceJSON)
}

// CreateEvidenceBatch writes one Merkle root and links N event IDs in the same transaction.
func (s *EvidenceSmartContract) CreateEvidenceBatch(
	ctx contractapi.TransactionContextInterface,
	batchID string,
	cameraID string,
	merkleRoot string,
	windowStart int64,
	windowEnd int64,
	eventIDsJSON string,
	eventHashesJSON string,
	eventVifsJSON string,
	deviceCertPEM string,
	signatureB64 string,
	payloadHashHex string,
) error {
	signerMSP, err := s.requireMSP(ctx, org1MSP, org2MSP)
	if err != nil {
		return err
	}

	exists, err := s.EvidenceExists(ctx, batchID)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("the batch %s already exists", batchID)
	}

	var eventIDs []string
	if err := json.Unmarshal([]byte(eventIDsJSON), &eventIDs); err != nil {
		return fmt.Errorf("invalid eventIDs JSON: %v", err)
	}
	if len(eventIDs) == 0 {
		return fmt.Errorf("eventIDs cannot be empty")
	}

	var eventHashes []string
	if err := json.Unmarshal([]byte(eventHashesJSON), &eventHashes); err != nil {
		return fmt.Errorf("invalid eventHashes JSON: %v", err)
	}
	if len(eventHashes) == 0 {
		return fmt.Errorf("eventHashes cannot be empty")
	}
	if len(eventIDs) != len(eventHashes) {
		return fmt.Errorf("eventIDs/eventHashes length mismatch")
	}

	var eventVifs []string
	if err := json.Unmarshal([]byte(eventVifsJSON), &eventVifs); err != nil {
		return fmt.Errorf("invalid eventVifs JSON: %v", err)
	}
	if len(eventVifs) != len(eventIDs) {
		return fmt.Errorf("eventVifs/eventIDs length mismatch")
	}

	seen := map[string]bool{}
	normalizedEventIDs := make([]string, 0, len(eventIDs))
	normalizedEventHashes := make([]string, 0, len(eventHashes))
	for idx, raw := range eventIDs {
		eventID := strings.TrimSpace(raw)
		if eventID == "" {
			return fmt.Errorf("eventID cannot be empty")
		}
		if seen[eventID] {
			return fmt.Errorf("duplicate eventID in batch: %s", eventID)
		}
		seen[eventID] = true
		normalizedEventIDs = append(normalizedEventIDs, eventID)

		eventHash := strings.ToLower(strings.TrimSpace(eventHashes[idx]))
		if eventHash == "" {
			return fmt.Errorf("eventHash cannot be empty for eventID %s", eventID)
		}
		if _, err := hex.DecodeString(eventHash); err != nil {
			return fmt.Errorf("invalid eventHash for eventID %s: %v", eventID, err)
		}
		normalizedEventHashes = append(normalizedEventHashes, eventHash)
	}

	for _, eventID := range normalizedEventIDs {
		eventExists, err := s.EvidenceExists(ctx, eventID)
		if err != nil {
			return err
		}
		if eventExists {
			return fmt.Errorf("the evidence %s already exists", eventID)
		}
	}

	normalizedRoot := strings.ToLower(strings.TrimSpace(merkleRoot))
	if normalizedRoot == "" {
		return fmt.Errorf("merkleRoot cannot be empty")
	}
	if _, err := hex.DecodeString(normalizedRoot); err != nil {
		return fmt.Errorf("invalid merkleRoot: %v", err)
	}

	expectedPayloadHash, err := canonicalBatchPayloadHash(
		batchID,
		cameraID,
		normalizedRoot,
		windowStart,
		windowEnd,
		normalizedEventIDs,
		normalizedEventHashes,
		eventVifs,
	)
	if err != nil {
		return fmt.Errorf("failed to build payload hash: %v", err)
	}
	normalizedPayloadHash := strings.ToLower(strings.TrimSpace(payloadHashHex))
	if normalizedPayloadHash == "" {
		return fmt.Errorf("payloadHashHex cannot be empty")
	}
	if normalizedPayloadHash != expectedPayloadHash {
		return fmt.Errorf("payloadHash mismatch")
	}

	deviceCertSHA256, deviceIdentityLabel, err := verifyDeviceSignature(deviceCertPEM, signatureB64, normalizedPayloadHash, cameraID)
	if err != nil {
		return err
	}

	now := time.Now().Unix()
	batchRecord := MerkleBatch{
		ID:                  batchID,
		MerkleRoot:          normalizedRoot,
		CameraID:            cameraID,
		EventCount:          len(normalizedEventIDs),
		EventIDs:            normalizedEventIDs,
		EventVifs:           eventVifs,
		WindowStart:         windowStart,
		WindowEnd:           windowEnd,
		Timestamp:           now,
		PayloadHash:         normalizedPayloadHash,
		Signature:           strings.TrimSpace(signatureB64),
		DeviceCertSHA256:    deviceCertSHA256,
		SignerMSP:           signerMSP,
		DeviceIdentityLabel: deviceIdentityLabel,
	}
	batchJSON, err := json.Marshal(batchRecord)
	if err != nil {
		return err
	}
	if err := ctx.GetStub().PutState(batchID, batchJSON); err != nil {
		return fmt.Errorf("failed to put batch %s: %v", batchID, err)
	}

	for idx, eventID := range normalizedEventIDs {
		memberHash := normalizedEventHashes[idx]
		eventEvidence := Evidence{
			ID:           eventID,
			Timestamp:    now,
			CameraID:     cameraID,
			EventType:    "batch_member",
			ObjectCount:  1,
			EvidenceHash: memberHash,
			RawDataURL:   fmt.Sprintf("batch://%s#%d", batchID, idx),
			Location:     "default_location",
		}
		eventJSON, err := json.Marshal(eventEvidence)
		if err != nil {
			return err
		}
		if err := ctx.GetStub().PutState(eventID, eventJSON); err != nil {
			return fmt.Errorf("failed to put event %s: %v", eventID, err)
		}
	}

	return nil
}

// ReadEvidence returns the evidence stored in the world state with given id.
func (s *EvidenceSmartContract) ReadEvidence(ctx contractapi.TransactionContextInterface, id string) (*Evidence, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return nil, err
	}

	evidenceJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if evidenceJSON == nil {
		return nil, fmt.Errorf("the evidence %s does not exist", id)
	}

	var evidence Evidence
	err = json.Unmarshal(evidenceJSON, &evidence)
	if err != nil {
		return nil, err
	}

	return &evidence, nil
}

// ReadMerkleBatch returns one MerkleBatch by batch ID.
func (s *EvidenceSmartContract) ReadMerkleBatch(ctx contractapi.TransactionContextInterface, batchID string) (*MerkleBatch, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return nil, err
	}

	batchJSON, err := ctx.GetStub().GetState(batchID)
	if err != nil {
		return nil, fmt.Errorf("failed to read batch %s: %v", batchID, err)
	}
	if batchJSON == nil {
		return nil, fmt.Errorf("the batch %s does not exist", batchID)
	}

	var batch MerkleBatch
	if err := json.Unmarshal(batchJSON, &batch); err != nil {
		return nil, err
	}
	if strings.TrimSpace(batch.MerkleRoot) == "" {
		return nil, fmt.Errorf("key %s is not a merkle batch", batchID)
	}
	return &batch, nil
}

// EvidenceExists returns true when asset with given ID exists in world state.
func (s *EvidenceSmartContract) EvidenceExists(ctx contractapi.TransactionContextInterface, id string) (bool, error) {
	evidenceJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return false, fmt.Errorf("failed to read from world state: %v", err)
	}

	return evidenceJSON != nil, nil
}

// GetAllEvidences returns all evidence-like records found in world state.
func (s *EvidenceSmartContract) GetAllEvidences(ctx contractapi.TransactionContextInterface) ([]*Evidence, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return nil, err
	}

	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var evidences []*Evidence
	for resultsIterator.HasNext() {
		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}
		if strings.HasPrefix(queryResponse.Key, rectificationPrefix) || strings.HasPrefix(queryResponse.Key, rawEvidenceHashPrefix) {
			continue
		}

		var evidence Evidence
		err = json.Unmarshal(queryResponse.Value, &evidence)
		if err != nil {
			continue
		}
		if strings.TrimSpace(evidence.ID) == "" {
			continue
		}
		evidences = append(evidences, &evidence)
	}

	return evidences, nil
}

// VerifyEvidence checks if the provided hash matches the stored hash for a given evidence ID.
func (s *EvidenceSmartContract) VerifyEvidence(ctx contractapi.TransactionContextInterface, id string, hashToVerify string) (bool, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return false, err
	}

	evidence, err := s.ReadEvidence(ctx, id)
	if err != nil {
		return false, err
	}

	return evidence.EvidenceHash == strings.ToLower(strings.TrimSpace(hashToVerify)), nil
}

// VerifyEvent validates one event leaf hash against a Merkle root using the provided proof.
func (s *EvidenceSmartContract) VerifyEvent(
	ctx contractapi.TransactionContextInterface,
	batchID string,
	eventHash string,
	merkleProofJSON string,
	merkleRoot string,
) (bool, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return false, err
	}

	batchJSON, err := ctx.GetStub().GetState(batchID)
	if err != nil {
		return false, fmt.Errorf("failed to read batch %s: %v", batchID, err)
	}
	if batchJSON == nil {
		return false, nil
	}

	var batch MerkleBatch
	if err := json.Unmarshal(batchJSON, &batch); err != nil {
		return false, fmt.Errorf("failed to decode batch %s: %v", batchID, err)
	}
	if strings.TrimSpace(batch.MerkleRoot) == "" {
		return false, nil
	}

	expectedRoot := strings.ToLower(strings.TrimSpace(merkleRoot))
	storedRoot := strings.ToLower(strings.TrimSpace(batch.MerkleRoot))
	if expectedRoot == "" || storedRoot != expectedRoot {
		return false, nil
	}

	var proof []MerkleProofStep
	if err := json.Unmarshal([]byte(merkleProofJSON), &proof); err != nil {
		return false, fmt.Errorf("invalid merkle proof JSON: %v", err)
	}

	leaf := strings.ToLower(strings.TrimSpace(eventHash))
	if leaf == "" {
		return false, nil
	}
	node, err := hex.DecodeString(leaf)
	if err != nil {
		return false, fmt.Errorf("invalid eventHash: %v", err)
	}

	for _, step := range proof {
		sibling, err := hex.DecodeString(strings.ToLower(strings.TrimSpace(step.Hash)))
		if err != nil {
			return false, fmt.Errorf("invalid proof hash: %v", err)
		}

		switch strings.ToLower(strings.TrimSpace(step.Position)) {
		case "left":
			sum := sha256.Sum256(append(sibling, node...))
			node = sum[:]
		case "right":
			sum := sha256.Sum256(append(node, sibling...))
			node = sum[:]
		default:
			return false, fmt.Errorf("invalid proof position: %s", step.Position)
		}
	}

	computedRoot := hex.EncodeToString(node)
	return computedRoot == storedRoot, nil
}

// VerifyAnchor verifies a GOP hash against an anchored Merkle root using a Merkle proof.
// Returns JSON with verification status.
func (s *EvidenceSmartContract) VerifyAnchor(
	ctx contractapi.TransactionContextInterface,
	epochId string,
	leafHash string,
	merkleProofJSON string,
) (string, error) {
	// --- access control ---
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return "", err
	}

	// --- read anchor record ---
	key := anchorKey(epochId)
	anchorJSON, err := ctx.GetStub().GetState(key)
	if err != nil {
		return "", fmt.Errorf("failed to read anchor %s: %v", epochId, err)
	}
	if anchorJSON == nil {
		result := map[string]interface{}{
			"status": "NOT_INTACT",
			"reason": "anchor not found",
		}
		resultJSON, _ := json.Marshal(result)
		return string(resultJSON), nil
	}

	var anchor AnchorRecord
	if err := json.Unmarshal(anchorJSON, &anchor); err != nil {
		return "", fmt.Errorf("failed to decode anchor %s: %v", epochId, err)
	}

	// --- validate inputs ---
	leafHash = strings.ToLower(strings.TrimSpace(leafHash))
	if leafHash == "" {
		result := map[string]interface{}{
			"status": "NOT_INTACT",
			"reason": "empty leaf hash",
		}
		resultJSON, _ := json.Marshal(result)
		return string(resultJSON), nil
	}

	storedRoot := strings.ToLower(strings.TrimSpace(anchor.MerkleRoot))
	if storedRoot == "" {
		result := map[string]interface{}{
			"status": "NOT_INTACT",
			"reason": "empty merkle root in anchor",
		}
		resultJSON, _ := json.Marshal(result)
		return string(resultJSON), nil
	}

	// --- parse merkle proof ---
	var proof []MerkleProofStep
	if err := json.Unmarshal([]byte(merkleProofJSON), &proof); err != nil {
		return "", fmt.Errorf("invalid merkle proof JSON: %v", err)
	}

	// --- compute root from leaf using proof ---
	currentBytes, err := hex.DecodeString(leafHash)
	if err != nil {
		return "", fmt.Errorf("invalid leaf hash: %v", err)
	}

	for _, step := range proof {
		siblingBytes, err := hex.DecodeString(strings.ToLower(strings.TrimSpace(step.Hash)))
		if err != nil {
			return "", fmt.Errorf("invalid proof hash: %v", err)
		}

		var combined []byte
		switch strings.ToLower(strings.TrimSpace(step.Position)) {
		case "left":
			combined = append(siblingBytes, currentBytes...)
		case "right":
			combined = append(currentBytes, siblingBytes...)
		default:
			return "", fmt.Errorf("invalid proof position: %s", step.Position)
		}

		hash := sha256.Sum256(combined)
		currentBytes = hash[:]
	}

	computedRoot := strings.ToLower(hex.EncodeToString(currentBytes))

	// --- compare roots ---
	if computedRoot == storedRoot {
		result := map[string]interface{}{
			"status":     "INTACT",
			"epochId":    epochId,
			"leafHash":   leafHash,
			"merkleRoot": storedRoot,
		}
		resultJSON, _ := json.Marshal(result)
		return string(resultJSON), nil
	}

	result := map[string]interface{}{
		"status":   "NOT_INTACT",
		"reason":   "computed root mismatch",
		"computed": computedRoot,
		"expected": storedRoot,
	}
	resultJSON, _ := json.Marshal(result)
	return string(resultJSON), nil
}

// PutRawEvidencePrivate stores raw evidence content in private data collection (Org1+Org2).
func (s *EvidenceSmartContract) PutRawEvidencePrivate(
	ctx contractapi.TransactionContextInterface,
	eventID string,
	imageBase64 string,
	mimeType string,
	imageSHA256 string,
) error {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP); err != nil {
		return err
	}

	eventID = strings.TrimSpace(eventID)
	if eventID == "" {
		return fmt.Errorf("eventID cannot be empty")
	}

	imageBase64 = strings.TrimSpace(imageBase64)
	mimeType = strings.TrimSpace(mimeType)
	imageSHA256 = strings.TrimSpace(imageSHA256)

	// Optional transient payload support for large private evidence:
	// --transient '{"rawEvidence":"<base64-json>"}'
	// JSON schema: {"imageBase64":"...","mimeType":"image/jpeg","imageSHA256":"..."}
	if imageBase64 == "" {
		transientMap, err := ctx.GetStub().GetTransient()
		if err != nil {
			return fmt.Errorf("failed to read transient map: %v", err)
		}
		if raw, ok := transientMap["rawEvidence"]; ok && len(raw) > 0 {
			var transientPayload struct {
				ImageBase64 string `json:"imageBase64"`
				MimeType    string `json:"mimeType"`
				ImageSHA256 string `json:"imageSHA256"`
			}
			if err := json.Unmarshal(raw, &transientPayload); err != nil {
				return fmt.Errorf("invalid transient rawEvidence payload: %v", err)
			}
			imageBase64 = strings.TrimSpace(transientPayload.ImageBase64)
			if mimeType == "" {
				mimeType = strings.TrimSpace(transientPayload.MimeType)
			}
			if imageSHA256 == "" {
				imageSHA256 = strings.TrimSpace(transientPayload.ImageSHA256)
			}
		}
	}
	if imageBase64 == "" {
		return fmt.Errorf("imageBase64 cannot be empty")
	}

	decoded, err := base64.StdEncoding.DecodeString(imageBase64)
	if err != nil {
		return fmt.Errorf("imageBase64 is not valid base64: %v", err)
	}
	computed := sha256.Sum256(decoded)
	computedHex := hex.EncodeToString(computed[:])

	normalizedHash := strings.ToLower(imageSHA256)
	if normalizedHash == "" {
		normalizedHash = computedHex
	}
	if normalizedHash != computedHex {
		return fmt.Errorf("imageSHA256 mismatch")
	}

	privateRecord := RawEvidencePrivate{
		EventID:     eventID,
		ImageBase64: imageBase64,
		MimeType:    mimeType,
		ImageSHA256: normalizedHash,
		Timestamp:   time.Now().Unix(),
	}
	privateJSON, err := json.Marshal(privateRecord)
	if err != nil {
		return err
	}
	if err := ctx.GetStub().PutPrivateData(collectionRawEvidence, eventID, privateJSON); err != nil {
		return fmt.Errorf("failed to put private data: %v", err)
	}

	hashRecord := RawEvidenceHash{
		EventID:     eventID,
		ImageSHA256: normalizedHash,
		Timestamp:   privateRecord.Timestamp,
		Collection:  collectionRawEvidence,
	}
	hashJSON, err := json.Marshal(hashRecord)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(rawEvidenceHashKey(eventID), hashJSON)
}

// GetRawEvidencePrivate returns full private raw evidence (Org1+Org2 only).
func (s *EvidenceSmartContract) GetRawEvidencePrivate(ctx contractapi.TransactionContextInterface, eventID string) (*RawEvidencePrivate, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP); err != nil {
		return nil, err
	}

	data, err := ctx.GetStub().GetPrivateData(collectionRawEvidence, strings.TrimSpace(eventID))
	if err != nil {
		return nil, fmt.Errorf("failed to read private data: %v", err)
	}
	if data == nil {
		return nil, fmt.Errorf("private raw evidence %s does not exist", eventID)
	}

	var privateRecord RawEvidencePrivate
	if err := json.Unmarshal(data, &privateRecord); err != nil {
		return nil, err
	}
	return &privateRecord, nil
}

// GetRawEvidenceHash returns public hash metadata for one private raw evidence.
func (s *EvidenceSmartContract) GetRawEvidenceHash(ctx contractapi.TransactionContextInterface, eventID string) (*RawEvidenceHash, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return nil, err
	}

	hashJSON, err := ctx.GetStub().GetState(rawEvidenceHashKey(strings.TrimSpace(eventID)))
	if err != nil {
		return nil, fmt.Errorf("failed to read raw evidence hash: %v", err)
	}
	if hashJSON == nil {
		return nil, fmt.Errorf("raw evidence hash for %s does not exist", eventID)
	}

	var hashRecord RawEvidenceHash
	if err := json.Unmarshal(hashJSON, &hashRecord); err != nil {
		return nil, err
	}
	return &hashRecord, nil
}

// CreateRectificationOrder opens one rectification order (Org2 only).
func (s *EvidenceSmartContract) CreateRectificationOrder(
	ctx contractapi.TransactionContextInterface,
	orderID string,
	batchID string,
	assignedTo string,
	deadline int64,
	comment string,
) error {
	if _, err := s.requireMSP(ctx, org2MSP); err != nil {
		return err
	}

	orderID = strings.TrimSpace(orderID)
	batchID = strings.TrimSpace(batchID)
	if orderID == "" || batchID == "" {
		return fmt.Errorf("orderID and batchID cannot be empty")
	}

	batchBytes, err := ctx.GetStub().GetState(batchID)
	if err != nil {
		return err
	}
	if batchBytes == nil {
		return fmt.Errorf("batch %s does not exist", batchID)
	}

	exists, err := ctx.GetStub().GetState(rectificationKey(orderID))
	if err != nil {
		return err
	}
	if exists != nil {
		return fmt.Errorf("rectification order %s already exists", orderID)
	}

	now := time.Now().Unix()
	order := RectificationOrder{
		ID:          orderID,
		BatchID:     batchID,
		CreatedBy:   org2MSP,
		AssignedTo:  strings.TrimSpace(assignedTo),
		Status:      "OPEN",
		Deadline:    deadline,
		Attachments: []string{},
		CreatedAt:   now,
		UpdatedAt:   now,
		History: []RectificationHistoryEntry{
			{At: now, ByMSP: org2MSP, Action: "CREATE", Comment: strings.TrimSpace(comment)},
		},
	}

	orderJSON, err := json.Marshal(order)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(rectificationKey(orderID), orderJSON)
}

// SubmitRectification submits remediation artifacts (Org1 only).
func (s *EvidenceSmartContract) SubmitRectification(ctx contractapi.TransactionContextInterface, orderID string, attachmentURL string, comment string) error {
	if _, err := s.requireMSP(ctx, org1MSP); err != nil {
		return err
	}

	order, err := s.ReadRectificationOrder(ctx, orderID)
	if err != nil {
		return err
	}
	if order.Status != "OPEN" && order.Status != "REJECTED" {
		return fmt.Errorf("rectification order %s is not submittable in status %s", orderID, order.Status)
	}

	order.Status = "SUBMITTED"
	order.UpdatedAt = time.Now().Unix()
	if trimmed := strings.TrimSpace(attachmentURL); trimmed != "" {
		order.Attachments = append(order.Attachments, trimmed)
	}
	order.History = append(order.History, RectificationHistoryEntry{
		At:      order.UpdatedAt,
		ByMSP:   org1MSP,
		Action:  "SUBMIT",
		Comment: strings.TrimSpace(comment),
	})

	orderJSON, err := json.Marshal(order)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(rectificationKey(strings.TrimSpace(orderID)), orderJSON)
}

// ConfirmRectification confirms/rejects remediation submission (Org2 only).
func (s *EvidenceSmartContract) ConfirmRectification(ctx contractapi.TransactionContextInterface, orderID string, approved bool, comment string) error {
	if _, err := s.requireMSP(ctx, org2MSP); err != nil {
		return err
	}

	order, err := s.ReadRectificationOrder(ctx, orderID)
	if err != nil {
		return err
	}
	if order.Status != "SUBMITTED" {
		return fmt.Errorf("rectification order %s is not confirmable in status %s", orderID, order.Status)
	}

	order.UpdatedAt = time.Now().Unix()
	if approved {
		order.Status = "CONFIRMED"
	} else {
		order.Status = "REJECTED"
	}
	order.History = append(order.History, RectificationHistoryEntry{
		At:      order.UpdatedAt,
		ByMSP:   org2MSP,
		Action:  "CONFIRM",
		Comment: strings.TrimSpace(comment),
	})

	orderJSON, err := json.Marshal(order)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(rectificationKey(strings.TrimSpace(orderID)), orderJSON)
}

// ReadRectificationOrder returns one rectification order.
func (s *EvidenceSmartContract) ReadRectificationOrder(ctx contractapi.TransactionContextInterface, orderID string) (*RectificationOrder, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return nil, err
	}

	orderJSON, err := ctx.GetStub().GetState(rectificationKey(strings.TrimSpace(orderID)))
	if err != nil {
		return nil, err
	}
	if orderJSON == nil {
		return nil, fmt.Errorf("rectification order %s does not exist", orderID)
	}

	var order RectificationOrder
	if err := json.Unmarshal(orderJSON, &order); err != nil {
		return nil, err
	}
	return &order, nil
}

// ExportAuditTrail exports one complete audit object for a batch (Org1/2/3 allowed).
func (s *EvidenceSmartContract) ExportAuditTrail(ctx contractapi.TransactionContextInterface, batchID string) (*AuditTrail, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return nil, err
	}

	batch, err := s.ReadMerkleBatch(ctx, batchID)
	if err != nil {
		return nil, err
	}

	events := make([]*Evidence, 0, len(batch.EventIDs))
	for _, eventID := range batch.EventIDs {
		evidenceJSON, err := ctx.GetStub().GetState(eventID)
		if err != nil {
			return nil, err
		}
		if evidenceJSON == nil {
			continue
		}

		var evidence Evidence
		if err := json.Unmarshal(evidenceJSON, &evidence); err != nil {
			continue
		}
		events = append(events, &evidence)
	}

	rectifications := []*RectificationOrder{}
	iter, err := ctx.GetStub().GetStateByRange(rectificationPrefix, rectificationPrefix+"\uffff")
	if err != nil {
		return nil, err
	}
	defer iter.Close()

	for iter.HasNext() {
		item, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var order RectificationOrder
		if err := json.Unmarshal(item.Value, &order); err != nil {
			continue
		}
		if order.BatchID != batchID {
			continue
		}
		o := order
		rectifications = append(rectifications, &o)
	}

	sort.Slice(rectifications, func(i, j int) bool {
		return rectifications[i].UpdatedAt < rectifications[j].UpdatedAt
	})

	return &AuditTrail{
		Batch:          batch,
		Events:         events,
		Rectifications: rectifications,
	}, nil
}

// GetHistoryForKey returns all historical versions of one key.
func (s *EvidenceSmartContract) GetHistoryForKey(ctx contractapi.TransactionContextInterface, id string) ([]*KeyHistory, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return nil, err
	}

	resultsIterator, err := ctx.GetStub().GetHistoryForKey(id)
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var history []*KeyHistory
	for resultsIterator.HasNext() {
		modification, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		var ts int64
		if modification.Timestamp != nil {
			ts = modification.Timestamp.Seconds
		}

		value := ""
		if !modification.IsDelete {
			value = string(modification.Value)
		}

		history = append(history, &KeyHistory{
			TxID:      modification.TxId,
			Timestamp: ts,
			IsDelete:  modification.IsDelete,
			Value:     value,
		})
	}

	return history, nil
}

// QueryOverdueOrders returns all rectification orders whose deadline has passed and are still OPEN.
func (s *EvidenceSmartContract) QueryOverdueOrders(ctx contractapi.TransactionContextInterface) ([]*RectificationOrder, error) {
	if _, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP); err != nil {
		return nil, err
	}

	iter, err := ctx.GetStub().GetStateByRange(rectificationPrefix, rectificationPrefix+"\uffff")
	if err != nil {
		return nil, fmt.Errorf("failed to query rectification orders: %v", err)
	}
	defer iter.Close()

	now := time.Now().Unix()
	var overdue []*RectificationOrder
	for iter.HasNext() {
		item, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var order RectificationOrder
		if err := json.Unmarshal(item.Value, &order); err != nil {
			continue
		}
		if order.Status == "OPEN" && order.Deadline > 0 && now > order.Deadline {
			o := order
			overdue = append(overdue, &o)
		}
	}

	sort.Slice(overdue, func(i, j int) bool {
		return overdue[i].Deadline < overdue[j].Deadline
	})

	return overdue, nil
}

// ---------------------------------------------------------------------------
// Anchor – GOP-level Merkle root anchoring
// ---------------------------------------------------------------------------

func anchorKey(epochId string) string {
	return anchorPrefix + epochId
}

func anchorLastTsKey(gatewayId string) string {
	return anchorLastTsPrefix + gatewayId
}

// deriveGatewayId produces a short, deterministic gateway identifier from the
// caller's x509 identity (Subject+Issuer).  We SHA-256 the raw string and
// keep the first 8 bytes → 16 hex characters.
func deriveGatewayId(ctx contractapi.TransactionContextInterface) (string, error) {
	ci := ctx.GetClientIdentity()
	if ci == nil {
		return "", fmt.Errorf("client identity is unavailable")
	}
	rawId, err := ci.GetID()
	if err != nil {
		return "", fmt.Errorf("failed to get client ID: %v", err)
	}
	h := sha256.Sum256([]byte(rawId))
	return hex.EncodeToString(h[:8]), nil
}

// Anchor submits a new GOP-level Merkle root to the ledger.
// Parameters are passed as strings (Fabric convention).
func (s *EvidenceSmartContract) Anchor(
	ctx contractapi.TransactionContextInterface,
	epochId string,
	merkleRoot string,
	timestampStr string,
	deviceCountStr string,
) error {
	// --- access control ---
	_, err := s.requireMSP(ctx, org1MSP, org2MSP)
	if err != nil {
		return err
	}

	// --- derive gateway id from caller identity ---
	gatewayId, err := deriveGatewayId(ctx)
	if err != nil {
		return err
	}

	// --- basic validation ---
	epochId = strings.TrimSpace(epochId)
	if epochId == "" {
		return fmt.Errorf("epochId must not be empty")
	}

	merkleRoot = strings.TrimSpace(merkleRoot)
	if len(merkleRoot) != 64 {
		return fmt.Errorf("merkleRoot must be 64 hex characters, got %d", len(merkleRoot))
	}
	if _, err := hex.DecodeString(merkleRoot); err != nil {
		return fmt.Errorf("merkleRoot is not valid hex: %v", err)
	}

	ts, err := strconv.ParseInt(strings.TrimSpace(timestampStr), 10, 64)
	if err != nil {
		return fmt.Errorf("invalid timestamp: %v", err)
	}

	dc, err := strconv.Atoi(strings.TrimSpace(deviceCountStr))
	if err != nil || dc < 0 {
		return fmt.Errorf("invalid deviceCount: %v", err)
	}

	// --- duplicate check ---
	key := anchorKey(epochId)
	existing, err := ctx.GetStub().GetState(key)
	if err != nil {
		return fmt.Errorf("failed to read state: %v", err)
	}
	if existing != nil {
		return fmt.Errorf("anchor for epoch %s already exists", epochId)
	}

	// --- timestamp rollback check ---
	lastTsKey := anchorLastTsKey(gatewayId)
	lastTsBytes, err := ctx.GetStub().GetState(lastTsKey)
	if err != nil {
		return fmt.Errorf("failed to read last timestamp: %v", err)
	}
	if lastTsBytes != nil {
		var lastTs int64
		if err := json.Unmarshal(lastTsBytes, &lastTs); err == nil {
			if ts <= lastTs {
				return fmt.Errorf("timestamp rollback: provided %d <= last %d for gateway %s", ts, lastTs, gatewayId)
			}
		}
	}

	// --- persist anchor record ---
	record := AnchorRecord{
		EpochId:     epochId,
		MerkleRoot:  merkleRoot,
		Timestamp:   ts,
		DeviceCount: dc,
		GatewayId:   gatewayId,
	}
	recordJSON, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal anchor record: %v", err)
	}
	if err := ctx.GetStub().PutState(key, recordJSON); err != nil {
		return fmt.Errorf("failed to put anchor state: %v", err)
	}

	// --- update last timestamp for this gateway ---
	tsBytes, _ := json.Marshal(ts)
	if err := ctx.GetStub().PutState(lastTsKey, tsBytes); err != nil {
		return fmt.Errorf("failed to update last timestamp: %v", err)
	}

	// --- emit event ---
	if err := ctx.GetStub().SetEvent("AnchorEvent", recordJSON); err != nil {
		return fmt.Errorf("failed to set AnchorEvent: %v", err)
	}

	return nil
}

// QueryAnchor returns a single anchor record by epoch ID.
func (s *EvidenceSmartContract) QueryAnchor(
	ctx contractapi.TransactionContextInterface,
	epochId string,
) (*AnchorRecord, error) {
	_, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP)
	if err != nil {
		return nil, err
	}

	epochId = strings.TrimSpace(epochId)
	data, err := ctx.GetStub().GetState(anchorKey(epochId))
	if err != nil {
		return nil, fmt.Errorf("failed to read anchor: %v", err)
	}
	if data == nil {
		return nil, fmt.Errorf("anchor %s does not exist", epochId)
	}

	var record AnchorRecord
	if err := json.Unmarshal(data, &record); err != nil {
		return nil, fmt.Errorf("failed to unmarshal anchor: %v", err)
	}
	return &record, nil
}

// QueryAnchorsByRange returns anchors whose keys fall in [startKey, endKey).
// Callers typically pass prefixed keys, e.g.
//
//	QueryAnchorsByRange("anchor:epoch_gw01_", "anchor:epoch_gw01_\uffff")
func (s *EvidenceSmartContract) QueryAnchorsByRange(
	ctx contractapi.TransactionContextInterface,
	startKey string,
	endKey string,
) ([]*AnchorRecord, error) {
	_, err := s.requireMSP(ctx, org1MSP, org2MSP, org3MSP)
	if err != nil {
		return nil, err
	}

	iter, err := ctx.GetStub().GetStateByRange(startKey, endKey)
	if err != nil {
		return nil, fmt.Errorf("failed to get state by range: %v", err)
	}
	defer iter.Close()

	var anchors []*AnchorRecord
	for iter.HasNext() {
		kv, err := iter.Next()
		if err != nil {
			return nil, fmt.Errorf("iterator error: %v", err)
		}
		var record AnchorRecord
		if err := json.Unmarshal(kv.Value, &record); err != nil {
			continue // skip malformed entries
		}
		anchors = append(anchors, &record)
	}
	return anchors, nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&EvidenceSmartContract{})
	if err != nil {
		fmt.Printf("Error creating evidence chaincode: %s", err.Error())
		return
	}

	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting evidence chaincode: %s", err.Error())
	}
}
