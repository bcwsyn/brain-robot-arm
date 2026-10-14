#!/usr/bin/env python3
"""Evaluate a frozen cup model and mask-derived RGB-D sizing on held-out captures."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS/'src/brain_robot_pick_place/scripts'))
from cup_perception import estimate_masked_cup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be new')
    os.environ.setdefault('YOLO_CONFIG_DIR', str(WS/'artifacts/yolo/config'))
    from ultralytics import YOLO
    model = YOLO(str(args.model))
    cup_ids = [index for index, name in model.names.items() if name == 'cup']
    if len(cup_ids) != 1 or model.task != 'segment':
        parser.error('a cup instance-segmentation model is required')
    metadata = json.loads((args.capture/'capture.json').read_text())
    args.output.mkdir(parents=True)
    records = []
    for label, view in metadata['views'].items():
        bgr = cv2.imread(str(args.capture/'images'/f'{label}.png'))
        rgbd = np.load(args.capture/f'{label}.npz')
        started = time.monotonic()
        result = model.predict(bgr, conf=.25, classes=cup_ids, imgsz=320,
            device='cpu', retina_masks=True, verbose=False)[0]
        inference_s = time.monotonic()-started
        result.save(filename=str(args.output/f'{label}.jpg'))
        record = dict(view=label, cup_instances=len(result.boxes), inference_s=inference_s)
        if len(result.boxes) == 1 and result.masks is not None:
            mask = result.masks.data[0].cpu().numpy() > .5
            truth = (bgr[:, :, 2] > 20) & (bgr[:, :, 2] > 1.5*bgr[:, :, 1].astype(float)) & (bgr[:, :, 2] > 1.5*bgr[:, :, 0].astype(float))
            record['mask_iou'] = float((mask & truth).sum()/max(1, (mask | truth).sum()))
            np.savez_compressed(args.output/f'{label}_predicted_mask.npz', mask=mask)
            yaw, pitch = view['yaw'], view['pitch']
            forward = np.array([math.cos(yaw)*math.cos(pitch), math.sin(yaw)*math.cos(pitch), -math.sin(pitch)])
            right = np.array([math.sin(yaw), -math.cos(yaw), 0.])
            rotation = np.column_stack((right, np.cross(forward, right), forward))
            try:
                estimate = estimate_masked_cup(rgbd['depth_m'], mask, rgbd['k'], rotation, view['camera_xyz'])
                record['geometry'] = estimate
                # Truth is used only here for reporting, after inference/fit.
                record['body_diameter_error_m'] = estimate['diameter_m']-.075
                record['height_error_m'] = estimate['observed_height_m']-.200
            except ValueError as error:
                record['geometry_rejected'] = str(error)
        records.append(record)
    report = dict(model=str(args.model), model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
        scope='five synthetic held-out views of the user specimen; no real-camera claim',
        diameter_truth_is_not_an_estimator_input=True, records=records,
        successful_sizing=sum('geometry' in r for r in records))
    (args.output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0 if report['successful_sizing'] == len(records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
