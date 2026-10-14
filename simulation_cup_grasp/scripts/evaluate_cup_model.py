#!/usr/bin/env python3
"""Offline cup instance-segmentation inspection; never starts ROS or motion.

Outputs predictions and timing, not accuracy: labelled independent project
images are required before precision/recall or detection reliability is claimed.
"""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    workspace = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model', type=Path,
                        default=workspace / 'artifacts/yolo/yolov8n-seg.pt')
    parser.add_argument('--confidence', type=float, default=.25)
    args = parser.parse_args()
    if not 0 < args.confidence < 1:
        parser.error('--confidence must be between zero and one')
    if not args.model.is_file():
        parser.error('Download and verify the official model before running this script')
    files = [args.images] if args.images.is_file() else sorted(
        p for p in args.images.rglob('*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg'))
    if not files:
        parser.error('No input images')
    os.environ.setdefault('YOLO_CONFIG_DIR', str(workspace / 'artifacts/yolo/config'))
    Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True, exist_ok=True)
    from ultralytics import YOLO
    model = YOLO(str(args.model))
    cup_ids = [index for index, name in model.names.items() if name == 'cup']
    if model.task != 'segment' or len(cup_ids) != 1:
        parser.error('Expected instance segmentation with one class named cup')
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for index, path in enumerate(files):
        start = time.monotonic()
        result = model.predict(str(path), device='cpu', conf=args.confidence,
                               classes=cup_ids, verbose=False)[0]
        cups = []
        for box in result.boxes:
            cups.append(dict(label='cup', confidence=float(box.conf[0]),
                             xyxy=box.xyxy[0].cpu().tolist()))
        elapsed = time.monotonic()-start
        overlay = f'{index:04d}-{path.stem}.jpg'
        result.save(filename=str(args.output / overlay))
        if result.masks is not None:
            import numpy as np
            np.savez_compressed(args.output / f'{index:04d}-masks.npz',
                                masks=result.masks.data.cpu().numpy(),
                                original_image_shape=result.orig_shape)
        rows.append(dict(image=str(path), elapsed_s=elapsed, cup_instances=cups, overlay=overlay))
    report = dict(model=str(args.model), target_class='cup', class_id=cup_ids[0], confidence=args.confidence,
                  task='instance_segmentation', images=len(rows), predictions=rows,
                  accuracy_evaluated=False,
                  limitation='Predictions alone do not measure accuracy or prove 3-D graspability.')
    (args.output / 'predictions.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(images=len(rows), cup_detections=sum(len(r['cup_instances']) for r in rows),
                          output=str(args.output), accuracy_evaluated=False), indent=2))


if __name__ == '__main__':
    main()
