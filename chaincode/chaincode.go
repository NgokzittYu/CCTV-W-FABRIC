package main

import (
	"encoding/json"
	"fmt"
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
