#!/usr/bin/env python3
"""Fine-tune a local YOLOv8 segmentation model; preserve complete run outputs."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=Path('artifacts/yolo/yolov8n-seg.pt'))
    parser.add_argument('--epochs', type=int, default=20)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be a new directory')
    os.environ.setdefault('YOLO_CONFIG_DIR', str(Path('artifacts/yolo/config').resolve()))
    Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True, exist_ok=True)
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(6)
    model = YOLO(str(args.model))
    result = model.train(data=str(args.data.resolve()), project=str(args.output.parent.resolve()),
        name=args.output.name, epochs=args.epochs, imgsz=320, batch=8, device='cpu', workers=0,
        seed=20261014, deterministic=True, optimizer='AdamW', lr0=.001, patience=8,
        mosaic=.5, close_mosaic=5, degrees=10, translate=.1, scale=.3,
        flipud=0, fliplr=.5, plots=True, save=True, save_period=5, exist_ok=False)
    (args.output/'training_metrics.json').write_text(json.dumps(result.results_dict, indent=2)+'\n')
    best = YOLO(str(args.output/'weights/best.pt'))
    test = best.val(data=str(args.data.resolve()), split='test', imgsz=320, device='cpu', workers=0,
        project=str(args.output.resolve()), name='test', plots=True)
    (args.output/'test_metrics.json').write_text(json.dumps(test.results_dict, indent=2)+'\n')


if __name__ == '__main__':
    main()
