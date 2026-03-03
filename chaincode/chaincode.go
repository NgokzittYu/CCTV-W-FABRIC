package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// EvidenceSmartContract provides functions for managing an Evidence
type EvidenceSmartContract struct {
	contractapi.Contract
}

// Evidence describes basic details of what makes up a simple evidence asset
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

// KeyHistory represents one historical modification for a key.
type KeyHistory struct {
	TxID      string `json:"txId"`
	Timestamp int64  `json:"timestamp"`
	IsDelete  bool   `json:"isDelete"`
	Value     string `json:"value"`
}

// InitLedger adds a base set of evidences to the ledger
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
func (s *EvidenceSmartContract) CreateEvidence(ctx contractapi.TransactionContextInterface, id string, cameraId string, eventType string, objectCount int, evidenceHash string, rawDataUrl string) error {
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
		CameraID:     cameraId,
		EventType:    eventType,
		ObjectCount:  objectCount,
		EvidenceHash: evidenceHash,
		RawDataURL:   rawDataUrl,
		Location:     "default_location", // Simplified for now
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
	cameraId string,
	eventType string,
	objectCount int,
	evidenceHash string,
	rawDataUrl string,
	eventIDsJSON string,
) error {
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

	seen := map[string]bool{}
	normalizedEventIDs := make([]string, 0, len(eventIDs))
	for _, raw := range eventIDs {
		eventID := strings.TrimSpace(raw)
		if eventID == "" {
			return fmt.Errorf("eventID cannot be empty")
		}
		if seen[eventID] {
			return fmt.Errorf("duplicate eventID in batch: %s", eventID)
		}
		seen[eventID] = true
		normalizedEventIDs = append(normalizedEventIDs, eventID)
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

	now := time.Now().Unix()
	if objectCount <= 0 {
		objectCount = len(normalizedEventIDs)
	}

	batchEvidence := Evidence{
		ID:           batchID,
		Timestamp:    now,
		CameraID:     cameraId,
		EventType:    eventType,
		ObjectCount:  objectCount,
		EvidenceHash: evidenceHash,
		RawDataURL:   rawDataUrl,
		Location:     "default_location",
	}
	batchJSON, err := json.Marshal(batchEvidence)
	if err != nil {
		return err
	}
	if err := ctx.GetStub().PutState(batchID, batchJSON); err != nil {
		return fmt.Errorf("failed to put batch %s: %v", batchID, err)
	}

	for idx, eventID := range normalizedEventIDs {
		eventEvidence := Evidence{
			ID:           eventID,
			Timestamp:    now,
			CameraID:     cameraId,
			EventType:    "batch_member",
			ObjectCount:  1,
			EvidenceHash: evidenceHash,
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

// EvidenceExists returns true when asset with given ID exists in world state
func (s *EvidenceSmartContract) EvidenceExists(ctx contractapi.TransactionContextInterface, id string) (bool, error) {
	evidenceJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return false, fmt.Errorf("failed to read from world state: %v", err)
	}

	return evidenceJSON != nil, nil
}

// GetAllEvidences returns all evidences found in world state
func (s *EvidenceSmartContract) GetAllEvidences(ctx contractapi.TransactionContextInterface) ([]*Evidence, error) {
	// range query with empty string for startKey and endKey does an open-ended query of all assets in the chaincode namespace.
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

		var evidence Evidence
		err = json.Unmarshal(queryResponse.Value, &evidence)
		if err != nil {
			return nil, err
		}
		evidences = append(evidences, &evidence)
	}

	return evidences, nil
}

// VerifyEvidence checks if the provided hash matches the stored hash for a given evidence ID
func (s *EvidenceSmartContract) VerifyEvidence(ctx contractapi.TransactionContextInterface, id string, hashToVerify string) (bool, error) {
	evidence, err := s.ReadEvidence(ctx, id)
	if err != nil {
		return false, err
	}

	return evidence.EvidenceHash == hashToVerify, nil
}

// GetHistoryForKey returns all historical versions of one key.
func (s *EvidenceSmartContract) GetHistoryForKey(ctx contractapi.TransactionContextInterface, id string) ([]*KeyHistory, error) {
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
