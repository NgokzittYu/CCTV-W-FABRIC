import os
import json
import logging
import subprocess
import shutil
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def run_cmd(cmd):
    # logging.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logging.error(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
        raise RuntimeError("FFmpeg command failed")

def generate_dummy_video(output_path, duration=30, size="1920x1080", fps=30):
    logging.info(f"Generating dummy source video: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={size}:rate={fps}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        str(output_path)
    ]
    run_cmd(cmd)

def generate_reencoded(src_path, out_dir, manifest, sample_id_prefix):
    logging.info("Generating RE_ENCODED dataset...")
    crf_vals = [18, 23, 28, 32, 35]
    resolutions = {"1080p": "1920x1080", "720p": "1280x720", "480p": "854x480"}
    codecs = {"H.264": "libx264", "H.265": "libx265"}

    idx = 1
    for crf in crf_vals:
        for res_name, res_val in resolutions.items():
            for codec_name, codec_val in codecs.items():
                variant_name = f"reenc_{res_name}_{codec_name.replace('.', '')}_crf{crf}.mp4"
                variant_path = out_dir / variant_name
                
                cmd = [
                    "ffmpeg", "-y", "-i", str(src_path),
                    "-vf", f"scale={res_val}",
                    "-c:v", codec_val,
                    "-crf", str(crf),
                    "-preset", "fast",
                    str(variant_path)
                ]
                run_cmd(cmd)
                
                sample_id = f"{sample_id_prefix}_{idx:03d}"
                manifest.append({
                    "sample_id": sample_id,
                    "source_video": str(src_path),
                    "variant_path": str(variant_path),
                    "expected_class": "RE_ENCODED",
                    "transform_type": "transcode",
                    "transform_params": {
                        "crf_value": crf,
                        "resolution": res_name,
                        "codec": codec_name
                    },
                    "attack_position": None,
                    "attack_length": None,
                    "replacement_source_type": None
                })
                idx += 1

def generate_tampered(src_path, out_dir, manifest, sample_id_prefix):
    logging.info("Generating TAMPERED dataset...")
    import cv2
    
    k_vals = [1, 2, 3, 5, 8, 12, 15]
    
    # Read source video
    cap = cv2.VideoCapture(str(src_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Store all frames for easy manipulation
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    
    distance_frames = int(min(10 * fps, total_frames // 2)) # At least 10s away
    
    idx = 1
    for k in k_vals:
        if len(frames) < distance_frames + k:
            continue
            
        # Target to tamper: middle of the video
        target_start = total_frames // 2
        
        # Source to replace from: beginning of the video (Homogeneous >= 10s away)
        source_start = min(10, total_frames // 4) 
        
        variant_name = f"tamper_homo_k{k}.mp4"
        variant_path = out_dir / variant_name
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(variant_path), fourcc, fps, (width, height))
        
        for i in range(total_frames):
            if target_start <= i < target_start + k:
                # Replace frame
                replace_idx = source_start + (i - target_start)
                out.write(frames[replace_idx])
            else:
                out.write(frames[i])
        
        out.release()
        
        # Post-process with FFmpeg to ensure standard encoding, avoiding mp4v codec warning
        final_variant_path = out_dir / f"final_{variant_name}"
        run_cmd(["ffmpeg", "-y", "-i", str(variant_path), "-c:v", "libx264", "-crf", "23", "-preset", "fast", str(final_variant_path)])
        os.remove(variant_path)
        os.rename(final_variant_path, variant_path)
        
        sample_id = f"{sample_id_prefix}_{idx:03d}"
        manifest.append({
            "sample_id": sample_id,
            "source_video": str(src_path),
            "variant_path": str(variant_path),
            "expected_class": "TAMPERED",
            "transform_type": "frame_replace",
            "transform_params": {
                "k_frames": k
            },
            "attack_position": target_start,
            "attack_length": k,
            "replacement_source_type": "homogeneous"
        })
        idx += 1

def main():
    bench_dir = Path("benchmarks")
    data_dir = bench_dir / "datasets"
    legit_dir = data_dir / "legitimate"
    tampered_dir = data_dir / "tampered"
    
    # Create directories
    legit_dir.mkdir(parents=True, exist_ok=True)
    tampered_dir.mkdir(parents=True, exist_ok=True)
    
    src_video = bench_dir / "sample_videos" / "cam1.mp4"
    if not src_video.exists():
        generate_dummy_video(src_video)
        
    manifest = []
    
    # 1. INTACT
    logging.info("Generating INTACT dataset...")
    intact_path = legit_dir / "intact_cam1.mp4"
    shutil.copy2(src_video, intact_path)
    manifest.append({
        "sample_id": "pair_intact_001",
        "source_video": str(src_video),
        "variant_path": str(intact_path),
        "expected_class": "INTACT",
        "transform_type": "none",
        "transform_params": {},
        "attack_position": None,
        "attack_length": None,
        "replacement_source_type": None
    })
    
    # 2. RE_ENCODED
    generate_reencoded(src_video, legit_dir, manifest, "pair_reenc")
    
    # 3. TAMPERED
    generate_tampered(src_video, tampered_dir, manifest, "pair_tamper")
    
    # Save manifest
    manifest_path = Path("benchmarks/manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
        
    logging.info(f"Dataset generation complete. Manifest saved to {manifest_path}")
    logging.info(f"Total samples: {len(manifest)}")

if __name__ == "__main__":
    main()
