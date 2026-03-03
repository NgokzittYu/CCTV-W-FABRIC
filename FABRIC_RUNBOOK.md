# YOLO Event -> Fabric (MVP)

This guide uses:
- `projects/cv-simple/detect.py` to generate `evidences/event_*.json`
- `projects/cv-simple/anchor_to_fabric.py` to submit those events to Fabric
- `fabric-samples/test-network` + `asset-transfer-basic/chaincode-go`

## 1) Start Fabric network and deploy basic chaincode

```bash
cd ~/projects/fabric-samples/test-network
./network.sh down
./network.sh up createChannel -c mychannel -ca
./network.sh deployCC -ccn basic -ccp ../asset-transfer-basic/chaincode-go -ccl go
```

## 2) Generate YOLO evidence JSON

```bash
cd ~/projects/cv-simple
python3 detect.py
```

If the live stream is unstable, run with reconnect-friendly options:

```bash
cd ~/projects/cv-simple
python3 detect.py --save-every 10 --reconnect-every 20 --reconnect-sleep 1 --retry-sleep 0.2
```

For night CCTV scenes (small, far objects), lower threshold and increase image size:

```bash
cd ~/projects/cv-simple
python3 detect.py --conf 0.15 --imgsz 1280 --save-every 5 --save-frame --max-frames 200
```

## 3) Anchor evidence JSON to Fabric

Dry-run first (no chaincode invoke):

```bash
cd ~/projects/cv-simple
python3 anchor_to_fabric.py --dry-run --limit 5
```

Actual invoke:

```bash
cd ~/projects/cv-simple
python3 anchor_to_fabric.py --limit 20
```

## 4) Query one anchored record from Fabric

```bash
cd ~/projects/fabric-samples
export PATH=$PWD/bin:$PATH
export FABRIC_CFG_PATH=$PWD/config
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_ADDRESS=localhost:7051
export CORE_PEER_TLS_ROOTCERT_FILE=$PWD/test-network/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=$PWD/test-network/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp

peer chaincode query -C mychannel -n basic -c '{"function":"ReadAsset","Args":["event_0000"]}'
```

## Data mapping used by `anchor_to_fabric.py`

Fabric basic chaincode schema is fixed (`CreateAsset(id,color,size,owner,appraisedValue)`).
So this MVP maps fields as:

- `id` = `event_id`
- `color` = most frequent detection class (e.g. `person`, `car`)
- `size` = number of objects detected in that frame event
- `owner` = `camera_id` (default `cctv-kctmc-01`)
- `appraisedValue` = `int(avg_confidence * 1000)`

For production, create a custom chaincode schema for CV events.
