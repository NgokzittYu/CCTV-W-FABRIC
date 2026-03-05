package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"math/big"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
	"github.com/hyperledger/fabric-protos-go/ledger/queryresult"
)

type mockStub struct {
	shim.ChaincodeStubInterface
	state        map[string][]byte
	privateState map[string]map[string][]byte
	transient    map[string][]byte
}

func newMockStub() *mockStub {
	return &mockStub{
		state:        map[string][]byte{},
		privateState: map[string]map[string][]byte{},
		transient:    map[string][]byte{},
	}
}

func cloneBytes(in []byte) []byte {
	if in == nil {
		return nil
	}
	out := make([]byte, len(in))
	copy(out, in)
	return out
}

func (m *mockStub) GetState(key string) ([]byte, error) {
	value, ok := m.state[key]
	if !ok {
		return nil, nil
	}
	return cloneBytes(value), nil
}

func (m *mockStub) PutState(key string, value []byte) error {
	if strings.TrimSpace(key) == "" {
		return fmt.Errorf("key cannot be empty")
	}
	m.state[key] = cloneBytes(value)
	return nil
}

func (m *mockStub) GetPrivateData(collection, key string) ([]byte, error) {
	coll, ok := m.privateState[collection]
	if !ok {
		return nil, nil
	}
	value, ok := coll[key]
	if !ok {
		return nil, nil
	}
	return cloneBytes(value), nil
}

func (m *mockStub) PutPrivateData(collection, key string, value []byte) error {
	if strings.TrimSpace(collection) == "" || strings.TrimSpace(key) == "" {
		return fmt.Errorf("collection/key cannot be empty")
	}
	if _, ok := m.privateState[collection]; !ok {
		m.privateState[collection] = map[string][]byte{}
	}
	m.privateState[collection][key] = cloneBytes(value)
	return nil
}

func (m *mockStub) GetTransient() (map[string][]byte, error) {
	out := map[string][]byte{}
	for k, v := range m.transient {
		out[k] = cloneBytes(v)
	}
	return out, nil
}

// mockStateIterator implements shim.StateQueryIteratorInterface for testing.
type mockStateIterator struct {
	items []*queryresult.KV
	index int
}

func (i *mockStateIterator) HasNext() bool { return i.index < len(i.items) }
func (i *mockStateIterator) Close() error  { return nil }
func (i *mockStateIterator) Next() (*queryresult.KV, error) {
	if !i.HasNext() {
		return nil, fmt.Errorf("no more items")
	}
	item := i.items[i.index]
	i.index++
	return item, nil
}

func (m *mockStub) GetStateByRange(startKey, endKey string) (shim.StateQueryIteratorInterface, error) {
	var keys []string
	for k := range m.state {
		if (startKey == "" || k >= startKey) && (endKey == "" || k < endKey) {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)
	items := make([]*queryresult.KV, 0, len(keys))
	for _, k := range keys {
		items = append(items, &queryresult.KV{Key: k, Value: cloneBytes(m.state[k])})
	}
	return &mockStateIterator{items: items}, nil
}

type fakeClientIdentity struct {
	mspID string
}

func (f *fakeClientIdentity) GetID() (string, error) {
	return "fake-id", nil
}

func (f *fakeClientIdentity) GetMSPID() (string, error) {
	return f.mspID, nil
}

func (f *fakeClientIdentity) GetAttributeValue(string) (string, bool, error) {
	return "", false, nil
}

func (f *fakeClientIdentity) AssertAttributeValue(string, string) error {
	return nil
}

func (f *fakeClientIdentity) GetX509Certificate() (*x509.Certificate, error) {
	return nil, nil
}

func newTestContext(stub *mockStub, mspID string) *contractapi.TransactionContext {
	ctx := new(contractapi.TransactionContext)
	ctx.SetStub(stub)
	ctx.SetClientIdentity(&fakeClientIdentity{mspID: mspID})
	return ctx
}

func mustGetEvidence(t *testing.T, stub *mockStub, id string) Evidence {
	t.Helper()
	raw, ok := stub.state[id]
	if !ok {
		t.Fatalf("expected state key %s", id)
	}
	var evidence Evidence
	if err := json.Unmarshal(raw, &evidence); err != nil {
		t.Fatalf("failed to decode evidence %s: %v", id, err)
	}
	return evidence
}

func mustGetBatch(t *testing.T, stub *mockStub, id string) MerkleBatch {
	t.Helper()
	raw, ok := stub.state[id]
	if !ok {
		t.Fatalf("expected state key %s", id)
	}
	var batch MerkleBatch
	if err := json.Unmarshal(raw, &batch); err != nil {
		t.Fatalf("failed to decode batch %s: %v", id, err)
	}
	return batch
}

func buildTwoLeafTree() (string, string, string, []MerkleProofStep, []MerkleProofStep) {
	sum1 := sha256.Sum256([]byte("leaf-a"))
	sum2 := sha256.Sum256([]byte("leaf-b"))
	leafA := hex.EncodeToString(sum1[:])
	leafB := hex.EncodeToString(sum2[:])

	left, _ := hex.DecodeString(leafA)
	right, _ := hex.DecodeString(leafB)
	rootSum := sha256.Sum256(append(left, right...))
	root := hex.EncodeToString(rootSum[:])

	proofA := []MerkleProofStep{{Position: "right", Hash: leafB}}
	proofB := []MerkleProofStep{{Position: "left", Hash: leafA}}
	return leafA, leafB, root, proofA, proofB
}

func buildSignedBatchMaterial(t *testing.T, batchID string, cameraID string, root string, windowStart int64, windowEnd int64, eventIDs []string, eventHashes []string) (string, string, string) {
	t.Helper()

	payloadHashHex, err := canonicalBatchPayloadHash(batchID, cameraID, root, windowStart, windowEnd, eventIDs, eventHashes)
	if err != nil {
		t.Fatalf("canonicalBatchPayloadHash failed: %v", err)
	}
	payloadHashBytes, err := hex.DecodeString(payloadHashHex)
	if err != nil {
		t.Fatalf("decode payload hash failed: %v", err)
	}

	privateKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate private key failed: %v", err)
	}
	sigDER, err := ecdsa.SignASN1(rand.Reader, privateKey, payloadHashBytes)
	if err != nil {
		t.Fatalf("sign payload failed: %v", err)
	}

	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(time.Now().UnixNano()),
		Subject: pkix.Name{
			CommonName:   fmt.Sprintf("device-%s@org1.example.com", cameraID),
			Organization: []string{"Org1"},
		},
		NotBefore:             time.Now().Add(-1 * time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature,
		BasicConstraintsValid: true,
		DNSNames:              []string{"org1.example.com", cameraID},
	}
	certDER, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &privateKey.PublicKey, privateKey)
	if err != nil {
		t.Fatalf("create certificate failed: %v", err)
	}
	certPEM := string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER}))

	return certPEM, base64.StdEncoding.EncodeToString(sigDER), payloadHashHex
}

func seedBatch(t *testing.T, contract *EvidenceSmartContract, ctx contractapi.TransactionContextInterface, batchID string) (string, string, string, []MerkleProofStep, []MerkleProofStep) {
	t.Helper()
	leafA, leafB, root, proofA, proofB := buildTwoLeafTree()
	eventIDs := []string{"event_a", "event_b"}
	eventHashes := []string{leafA, leafB}
	eventIDsJSON, _ := json.Marshal(eventIDs)
	eventHashesJSON, _ := json.Marshal(eventHashes)
	certPEM, signatureB64, payloadHashHex := buildSignedBatchMaterial(t, batchID, "cam_test", root, 1700000000, 1700000060, eventIDs, eventHashes)

	err := contract.CreateEvidenceBatch(
		ctx,
		batchID,
		"cam_test",
		root,
		1700000000,
		1700000060,
		string(eventIDsJSON),
		string(eventHashesJSON),
		certPEM,
		signatureB64,
		payloadHashHex,
	)
	if err != nil {
		t.Fatalf("CreateEvidenceBatch failed: %v", err)
	}
	return leafA, leafB, root, proofA, proofB
}

func TestCreateEvidence_OK(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctx := newTestContext(stub, org1MSP)

	err := contract.CreateEvidence(ctx, "event_001", "cam_1", "detection_car", 1, "hash001", "file://event_001.json")
	if err != nil {
		t.Fatalf("CreateEvidence returned error: %v", err)
	}

	evidence := mustGetEvidence(t, stub, "event_001")
	if evidence.ID != "event_001" {
		t.Fatalf("unexpected ID: %s", evidence.ID)
	}
	if evidence.EvidenceHash != "hash001" {
		t.Fatalf("unexpected hash: %s", evidence.EvidenceHash)
	}
}

func TestCreateEvidence_Duplicate(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctx := newTestContext(stub, org1MSP)

	err := contract.CreateEvidence(ctx, "event_dup", "cam_1", "detection_car", 1, "hash001", "file://event_dup.json")
	if err != nil {
		t.Fatalf("first CreateEvidence returned error: %v", err)
	}

	err = contract.CreateEvidence(ctx, "event_dup", "cam_1", "detection_car", 1, "hash001", "file://event_dup.json")
	if err == nil {
		t.Fatalf("expected duplicate error, got nil")
	}
}

func TestCreateEvidenceBatch_OK(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctx := newTestContext(stub, org1MSP)

	leafA, leafB, root, _, _ := seedBatch(t, contract, ctx, "batch_ok")

	batch := mustGetBatch(t, stub, "batch_ok")
	if batch.MerkleRoot != root {
		t.Fatalf("unexpected root: %s", batch.MerkleRoot)
	}
	if batch.EventCount != 2 {
		t.Fatalf("unexpected event count: %d", batch.EventCount)
	}
	if batch.DeviceCertSHA256 == "" || batch.PayloadHash == "" || batch.Signature == "" {
		t.Fatalf("expected signature metadata in batch")
	}

	memberA := mustGetEvidence(t, stub, "event_a")
	memberB := mustGetEvidence(t, stub, "event_b")
	if memberA.EvidenceHash != leafA {
		t.Fatalf("event_a leaf mismatch: %s", memberA.EvidenceHash)
	}
	if memberB.EvidenceHash != leafB {
		t.Fatalf("event_b leaf mismatch: %s", memberB.EvidenceHash)
	}
}

func TestCreateEvidenceBatch_InvalidSignature(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctx := newTestContext(stub, org1MSP)

	leafA, leafB, root, _, _ := buildTwoLeafTree()
	eventIDs := []string{"event_x", "event_y"}
	eventHashes := []string{leafA, leafB}
	eventIDsJSON, _ := json.Marshal(eventIDs)
	eventHashesJSON, _ := json.Marshal(eventHashes)
	certPEM, signatureB64, payloadHashHex := buildSignedBatchMaterial(t, "batch_invalid_sig", "cam_test", root, 1700000000, 1700000060, eventIDs, eventHashes)

	if signatureB64[len(signatureB64)-1] != 'A' {
		signatureB64 = signatureB64[:len(signatureB64)-1] + "A"
	} else {
		signatureB64 = signatureB64[:len(signatureB64)-1] + "B"
	}

	err := contract.CreateEvidenceBatch(
		ctx,
		"batch_invalid_sig",
		"cam_test",
		root,
		1700000000,
		1700000060,
		string(eventIDsJSON),
		string(eventHashesJSON),
		certPEM,
		signatureB64,
		payloadHashHex,
	)
	if err == nil {
		t.Fatalf("expected signature validation error")
	}
}

func TestACL_Org3CannotCreateEvidenceBatch(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctx := newTestContext(stub, org3MSP)

	leafA, leafB, root, _, _ := buildTwoLeafTree()
	eventIDs := []string{"event_x", "event_y"}
	eventHashes := []string{leafA, leafB}
	eventIDsJSON, _ := json.Marshal(eventIDs)
	eventHashesJSON, _ := json.Marshal(eventHashes)
	certPEM, signatureB64, payloadHashHex := buildSignedBatchMaterial(t, "batch_acl_forbidden", "cam_test", root, 1700000000, 1700000060, eventIDs, eventHashes)

	err := contract.CreateEvidenceBatch(
		ctx,
		"batch_acl_forbidden",
		"cam_test",
		root,
		1700000000,
		1700000060,
		string(eventIDsJSON),
		string(eventHashesJSON),
		certPEM,
		signatureB64,
		payloadHashHex,
	)
	if err == nil {
		t.Fatalf("expected ACL error for Org3")
	}
}

func TestVerifyEvent_OK(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctxOrg1 := newTestContext(stub, org1MSP)
	leafA, _, root, proofA, _ := seedBatch(t, contract, ctxOrg1, "batch_verify_ok")

	proofJSON, _ := json.Marshal(proofA)
	ctxOrg3 := newTestContext(stub, org3MSP)
	ok, err := contract.VerifyEvent(ctxOrg3, "batch_verify_ok", leafA, string(proofJSON), root)
	if err != nil {
		t.Fatalf("VerifyEvent returned error: %v", err)
	}
	if !ok {
		t.Fatalf("expected VerifyEvent to return true")
	}
}

func TestPutRawEvidencePrivate_Org1Org2Only(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()

	img := []byte("raw-image-content")
	imgB64 := base64.StdEncoding.EncodeToString(img)
	sum := sha256.Sum256(img)
	imgHash := hex.EncodeToString(sum[:])

	ctxOrg1 := newTestContext(stub, org1MSP)
	err := contract.PutRawEvidencePrivate(ctxOrg1, "event_private_1", imgB64, "image/jpeg", imgHash)
	if err != nil {
		t.Fatalf("Org1 PutRawEvidencePrivate should succeed: %v", err)
	}

	ctxOrg3 := newTestContext(stub, org3MSP)
	err = contract.PutRawEvidencePrivate(ctxOrg3, "event_private_2", imgB64, "image/jpeg", imgHash)
	if err == nil {
		t.Fatalf("Org3 PutRawEvidencePrivate should be denied")
	}

	hashMeta, err := contract.GetRawEvidenceHash(ctxOrg3, "event_private_1")
	if err != nil {
		t.Fatalf("Org3 GetRawEvidenceHash should succeed: %v", err)
	}
	if hashMeta.ImageSHA256 != imgHash {
		t.Fatalf("unexpected image hash metadata: %s", hashMeta.ImageSHA256)
	}

	_, err = contract.GetRawEvidencePrivate(ctxOrg3, "event_private_1")
	if err == nil {
		t.Fatalf("Org3 GetRawEvidencePrivate should be denied")
	}
}

func TestPutRawEvidencePrivate_TransientPayload(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctxOrg1 := newTestContext(stub, org1MSP)

	img := []byte("raw-image-transient")
	imgB64 := base64.StdEncoding.EncodeToString(img)
	sum := sha256.Sum256(img)
	imgHash := hex.EncodeToString(sum[:])

	transientPayload, _ := json.Marshal(map[string]string{
		"imageBase64": imgB64,
		"mimeType":    "image/jpeg",
		"imageSHA256": imgHash,
	})
	stub.transient["rawEvidence"] = transientPayload

	err := contract.PutRawEvidencePrivate(ctxOrg1, "event_private_transient", "", "", "")
	if err != nil {
		t.Fatalf("PutRawEvidencePrivate transient path should succeed: %v", err)
	}

	hashMeta, err := contract.GetRawEvidenceHash(ctxOrg1, "event_private_transient")
	if err != nil {
		t.Fatalf("GetRawEvidenceHash should succeed: %v", err)
	}
	if hashMeta.ImageSHA256 != imgHash {
		t.Fatalf("unexpected image hash metadata: %s", hashMeta.ImageSHA256)
	}
}

func TestRectificationWorkflow_StateTransition(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctxOrg1 := newTestContext(stub, org1MSP)
	seedBatch(t, contract, ctxOrg1, "batch_rectify")

	ctxOrg2 := newTestContext(stub, org2MSP)
	err := contract.CreateRectificationOrder(ctxOrg2, "order_1", "batch_rectify", "team_a", 1700010000, "create order")
	if err != nil {
		t.Fatalf("CreateRectificationOrder failed: %v", err)
	}

	err = contract.SubmitRectification(ctxOrg1, "order_1", "https://example.com/proof.jpg", "submitted")
	if err != nil {
		t.Fatalf("SubmitRectification failed: %v", err)
	}

	err = contract.ConfirmRectification(ctxOrg2, "order_1", true, "approved")
	if err != nil {
		t.Fatalf("ConfirmRectification failed: %v", err)
	}

	ctxOrg3 := newTestContext(stub, org3MSP)
	order, err := contract.ReadRectificationOrder(ctxOrg3, "order_1")
	if err != nil {
		t.Fatalf("ReadRectificationOrder failed: %v", err)
	}
	if order.Status != "CONFIRMED" {
		t.Fatalf("unexpected rectification status: %s", order.Status)
	}
}

func TestQueryOverdueOrders(t *testing.T) {
	contract := new(EvidenceSmartContract)
	stub := newMockStub()
	ctxOrg1 := newTestContext(stub, org1MSP)
	seedBatch(t, contract, ctxOrg1, "batch_overdue")

	ctxOrg2 := newTestContext(stub, org2MSP)

	// order_overdue: deadline in the past, OPEN → should appear
	pastDeadline := time.Now().Unix() - 3600
	err := contract.CreateRectificationOrder(ctxOrg2, "order_overdue", "batch_overdue", "team_a", pastDeadline, "past deadline")
	if err != nil {
		t.Fatalf("CreateRectificationOrder failed: %v", err)
	}

	// order_future: deadline in the future, OPEN → should NOT appear
	futureDeadline := time.Now().Unix() + 86400
	err = contract.CreateRectificationOrder(ctxOrg2, "order_future", "batch_overdue", "team_a", futureDeadline, "future deadline")
	if err != nil {
		t.Fatalf("CreateRectificationOrder failed: %v", err)
	}

	// order_confirmed: deadline in the past but CONFIRMED → should NOT appear
	err = contract.CreateRectificationOrder(ctxOrg2, "order_confirmed", "batch_overdue", "team_a", pastDeadline, "confirmed order")
	if err != nil {
		t.Fatalf("CreateRectificationOrder failed: %v", err)
	}
	err = contract.SubmitRectification(ctxOrg1, "order_confirmed", "https://example.com/proof.jpg", "submit")
	if err != nil {
		t.Fatalf("SubmitRectification failed: %v", err)
	}
	err = contract.ConfirmRectification(ctxOrg2, "order_confirmed", true, "approved")
	if err != nil {
		t.Fatalf("ConfirmRectification failed: %v", err)
	}

	ctxOrg3 := newTestContext(stub, org3MSP)
	overdue, err := contract.QueryOverdueOrders(ctxOrg3)
	if err != nil {
		t.Fatalf("QueryOverdueOrders failed: %v", err)
	}
	if len(overdue) != 1 {
		t.Fatalf("expected 1 overdue order, got %d", len(overdue))
	}
	if overdue[0].ID != "order_overdue" {
		t.Fatalf("expected order_overdue, got %s", overdue[0].ID)
	}
}
