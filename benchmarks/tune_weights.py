import json
import itertools
from pathlib import Path

def main():
    result_path = Path("benchmarks/results/experiment_tri_state.json")
    if not result_path.exists():
        print(f"找不到结果文件 {result_path}")
        return
        
    with open(result_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"Loaded {len(data)} samples for tuning...")

    # Define grids
    # Weights sum to 1.0. We iterate in steps of 0.05
    w_vals = [round(x * 0.05, 2) for x in range(21)]
    thresholds = [round(x * 0.01, 2) for x in range(10, 41)] # 0.10 to 0.40

    best_configs = [] # List of (accuracy, w_vis, w_sem, w_tem, thresh)

    # Pre-parse results for faster iteration
    parsed_samples = []
    for sample in data:
        expected = sample["expected_class"]
        gops = []
        for gop in sample["gop_results"]:
            if gop["state"] == "INTACT":
                # Matches SHA256 exactly
                gops.append({"is_intact": True})
            elif "d_vis" in gop["details"]:
                # 回滚：适应干净的双模态协议 (64-Hex / 256-bit)
                gops.append({
                    "is_intact": False,
                    "d_global": gop["details"].get("d_vis", 0),
                    "d_local_max": gop["details"].get("d_vis_local_max", 0),
                    "d_local_top2": gop["details"].get("d_vis_local_top2", 0),
                    "d_tem": gop["details"].get("d_tem", 0)
                })
            else:
                # missing VIF or other fallback -> TAMPERED
                gops.append({"is_intact": False, "fallback_tampered": True})
        parsed_samples.append((expected, gops))

    total = len(parsed_samples)

    prior_w_vis = 0.50
    prior_w_tem = 0.50
    prior_thresh = 0.35
    
    def eval_ablation(mode, alpha, w_vis, w_tem, thresh):
        res = {"correct": 0, "fp": 0, "fn": 0, "tp": 0, "tn_re": 0, "matrix": {}}
        for exp in ["INTACT", "RE_ENCODED", "TAMPERED"]:
            res["matrix"][exp] = {"INTACT": 0, "RE_ENCODED": 0, "TAMPERED": 0}
            
        for expected, gops in parsed_samples:
            has_tamp = False
            all_intact = True
            
            if len(gops) == 0:
                all_intact = False
                
            for g in gops:
                if g["is_intact"]:
                    continue
                all_intact = False
                if g.get("fallback_tampered", False):
                    has_tamp = True
                    continue
                
                d_global = g.get("d_global", 0.0)
                if mode == "baseline":
                    d_local = 0.0
                elif mode == "max":
                    d_local = g.get("d_local_max", 0.0)
                elif mode == "top2":
                    d_local = g.get("d_local_top2", 0.0)
                else:
                    d_local = 0.0
                    
                d_vis_final = alpha * d_global + (1.0 - alpha) * d_local
                risk = w_vis * d_vis_final + w_tem * g.get("d_tem", 0.0)
                
                if risk >= thresh:
                    has_tamp = True
                    
            if has_tamp:
                pred = "TAMPERED"
            elif all_intact:
                pred = "INTACT"
            else:
                pred = "RE_ENCODED"
                
            res["matrix"][expected][pred] += 1
            if pred == expected:
                res["correct"] += 1
            if expected == "RE_ENCODED" and pred == "TAMPERED":
                res["fp"] += 1
            if expected == "TAMPERED" and pred != "TAMPERED":
                res["fn"] += 1
            if expected == "TAMPERED" and pred == "TAMPERED":
                res["tp"] += 1
            if expected == "RE_ENCODED" and pred == "RE_ENCODED":
                res["tn_re"] += 1
                
        # Calculate macro-F1
        f1s = []
        for c in ["INTACT", "RE_ENCODED", "TAMPERED"]:
            tp = res["matrix"][c][c]
            fp_c = sum(res["matrix"][other][c] for other in ["INTACT", "RE_ENCODED", "TAMPERED"] if other != c)
            fn_c = sum(res["matrix"][c][other] for other in ["INTACT", "RE_ENCODED", "TAMPERED"] if other != c)
            prec = tp / (tp + fp_c) if (tp + fp_c) > 0 else 0
            rec = tp / (tp + fn_c) if (tp + fn_c) > 0 else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
            f1s.append(f1)
        res["macro_f1"] = sum(f1s) / 3.0
            
        return res

    def print_ablation(title, mode, alpha):
        res = eval_ablation(mode, alpha, prior_w_vis, prior_w_tem, prior_thresh)
        re_total = sum(res['matrix']["RE_ENCODED"].values())
        tamp_total = sum(res['matrix']["TAMPERED"].values())
        print(f"\n{title} (alpha={alpha:.2f})")
        print(f"  Macro-F1 Score: {res['macro_f1']:.4f}")
        print(f"  TAMP False Negative Rate: {res['fn']}/{tamp_total} ({(res['fn']/max(1, tamp_total))*100:.1f}%)")
        print(f"  RE_ENCODED Retention Rate: {res['tn_re']}/{re_total} ({(res['tn_re']/max(1, re_total))*100:.1f}%)")
        print(f"  RE_ENCODED False Positive R: {res['fp']}/{re_total} ({(res['fp']/max(1, re_total))*100:.1f}%)")

    print(f"\n=== ABLATION STUDY (Tolerant Mode w_vis=0.5, w_tem=0.5, thresh=0.35) ===")
    print_ablation("[Baseline] 宽容态全局视觉基线 (Tolerant Mode)", "baseline", 1.0)
    print_ablation("[Legacy Variant] 局部 (Max) 废弃分支", "max", 0.5)
    print_ablation("[Legacy Variant] 局部 (Top2_Mean) 废弃分支", "top2", 0.5)

    # ── 双轨评测: 调优上界 ──
    best_configs = [] # List of (accuracy, w_vis, w_tem, thresh)

    # We'll use the safe top2 setting for tuning.
    for w_vis in w_vals:
        w_tem = round(1.0 - w_vis, 2)
        if w_tem < 0 or w_tem > 1.0:
            continue
            
        for thresh in thresholds:
            res = eval_ablation("top2", 0.5, w_vis, w_tem, thresh)
            correct = res["correct"]
            best_configs.append((correct, w_vis, w_tem, thresh, res))

    # Sort and unique
    best_configs.sort(key=lambda x: x[0], reverse=True)
    
    print("\n=== TUNING UPPER BOUNDS (Top Configurations for Top2_Mean alpha=0.5) ===")
    printed_acc = set()
    count = 0
    for cfg in best_configs:
        acc, w_vis, w_tem, thresh, res = cfg
        if acc not in printed_acc or count < 5:
            printed_acc.add(acc)
            count += 1
            print(f"Accuracy: {acc}/{total} ({(acc/total)*100:.1f}%) | w_vis={w_vis:.2f}, w_tem={w_tem:.2f}, threshold={thresh:.2f}")
            print(f"    -> RE_FP: {res['fp']} | TAMP_FN: {res['fn']} | RE_Retain: {res['tn_re']}")
            if count >= 10:
                break

if __name__ == "__main__":
    main()
