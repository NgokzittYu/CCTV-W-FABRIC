import os
import json
import csv
import logging
from pathlib import Path
from tqdm import tqdm

from services.gop_splitter import split_gops
from services.tri_state_verifier import TriStateVerifier

logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def evaluate_pair(src_path, var_path, verifier):
    orig_gops = split_gops(src_path)
    curr_gops = split_gops(var_path)
    
    gop_results = []
    
    min_len = min(len(orig_gops), len(curr_gops))
    
    for i in range(min_len):
        orig = orig_gops[i]
        curr = curr_gops[i]
        
        state, risk, details = verifier.verify(
            orig.sha256_hash, curr.sha256_hash, orig.vif, curr.vif
        )
        
        gop_results.append({
            "gop_id": i,
            "state": state,
            "risk": risk,
            "details": details
        })
        
    # Aggregate rule:
    # 1. Any TAMPERED -> TAMPERED
    # 2. All INTACT -> INTACT
    # 3. Else -> RE_ENCODED
    has_tampered = False
    all_intact = True
    if len(gop_results) == 0:
        all_intact = False
        
    for res in gop_results:
        # print(f"  -> {res}")
        if res["state"] == "TAMPERED":
            has_tampered = True
        if res["state"] != "INTACT":
            all_intact = False
            
    if has_tampered:
        final_class = "TAMPERED"
    elif all_intact:
        final_class = "INTACT"
    else:
        final_class = "RE_ENCODED"
        
    return final_class, gop_results

def main():
    # Force Multi-modal fusion VIF and sample 3 extra frames
    os.environ["VIF_MODE"] = "fusion"
    os.environ["VIF_SAMPLE_FRAMES"] = "3"
    
    manifest_path = Path("benchmarks/manifest.json")
    if not manifest_path.exists():
        logger.error("manifest.json not found")
        return
        
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
        
    verifier = TriStateVerifier(w_vis=0.50, w_tem=0.50, risk_threshold=0.20)
    
    out_dir = Path("benchmarks/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    for sample in tqdm(manifest, desc="Evaluating pairs"):
        pred_class, gop_res = evaluate_pair(sample["source_video"], sample["variant_path"], verifier)
        
        res_entry = {
            **sample,
            "predicted_class": pred_class,
            "gop_results": gop_res,
            "is_correct": pred_class == sample["expected_class"]
        }
        results.append(res_entry)
        
    # Save detailed JSON
    out_json = out_dir / "experiment_tri_state.json"
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    # Save Summary CSV
    csv_path = out_dir / "summary.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "sample_id", "expected_class", "predicted_class", "is_correct",
            "transform_type", "transform_params"
        ])
        for r in results:
            writer.writerow([
                r["sample_id"], r["expected_class"], r["predicted_class"], r["is_correct"],
                r["transform_type"], json.dumps(r["transform_params"])
            ])
            
    logger.info(f"\nExperiments completed! Results saved to {out_dir}")
    if len(results) > 0:
        correct = sum(1 for r in results if r["is_correct"])
        
        # ── 计算混淆矩阵和 4 项强制指标 ──
        # 三态: INTACT, RE_ENCODED, TAMPERED
        from collections import defaultdict
        matrix = defaultdict(lambda: defaultdict(int))
        for r in results:
            matrix[r["expected_class"]][r["predicted_class"]] += 1
            
        logger.info("\n=== [Phase 3] Benchmark Metrics ===")
        
        logger.info("\n1. Tri-state Confusion Matrix (Expected -> Predicted):")
        classes = ["INTACT", "RE_ENCODED", "TAMPERED"]
        
        # Header
        logger.info(f"{'':>12} | {'INTACT':>10} | {'RE_ENCODED':>10} | {'TAMPERED':>10}")
        logger.info("-" * 52)
        for exp_c in classes:
            row = [matrix[exp_c][pred_c] for pred_c in classes]
            logger.info(f"{exp_c:>12} | {row[0]:>10} | {row[1]:>10} | {row[2]:>10}")
            
        # Metrics
        # 1. Total Accuracy
        logger.info(f"\n* Overall Accuracy: {correct}/{len(results)} ({correct/len(results)*100:.1f}%)")
        
        # 2. RE_ENCODED -> TAMPERED (False Positive for tampering)
        re_total = sum(matrix["RE_ENCODED"].values())
        re_to_tamp = matrix["RE_ENCODED"]["TAMPERED"]
        re_fp_rate = (re_to_tamp / re_total * 100) if re_total > 0 else 0.0
        logger.info(f"* RE_ENCODED False Positive Rate (误判为被篡改): {re_to_tamp}/{re_total} ({re_fp_rate:.1f}%)")
        
        # 3. TAMPERED -> RE_ENCODED (False Negative for tampering)
        tamp_total = sum(matrix["TAMPERED"].values())
        # TAMPERED missed could be predicted as RE_ENCODED or INTACT
        tamp_missed = matrix["TAMPERED"]["RE_ENCODED"] + matrix["TAMPERED"]["INTACT"]
        tamp_fn_rate = (tamp_missed / tamp_total * 100) if tamp_total > 0 else 0.0
        logger.info(f"* TAMPERED False Negative Rate (漏判为合法转码或原档): {tamp_missed}/{tamp_total} ({tamp_fn_rate:.1f}%)")
        
        # 4. RE_ENCODED Retention Rate (合法转码保持率)
        re_correct = matrix["RE_ENCODED"]["RE_ENCODED"]
        re_retention = (re_correct / re_total * 100) if re_total > 0 else 0.0
        logger.info(f"* Legitimate Transcode Retention Rate (合法转码保持率): {re_correct}/{re_total} ({re_retention:.1f}%)")
        logger.info("===================================\n")

if __name__ == "__main__":
    main()
