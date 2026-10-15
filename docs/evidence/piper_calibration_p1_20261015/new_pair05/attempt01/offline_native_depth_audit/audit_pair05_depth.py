#!/usr/bin/env python3
"""Offline audit of SHA-verified archived frames; never opens a live device.

Reuses original color/registration selection. A fixed native footprint from
the first supported frame is tested against every later RAW uint16 frame,
without projection, thresholds, temporal fill, or replacement measurements.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

import cv2
import numpy as np


def digest(data):
    return hashlib.sha256(data).hexdigest()


def describe(values):
    values = np.asarray(values)
    return {'count': int(values.size), 'min': float(values.min()) if values.size else None,
            'median': float(np.median(values)) if values.size else None,
            'max': float(values.max()) if values.size else None}


def footprint_stats(depth, footprint):
    values = depth[footprint]
    return {'pixels': int(values.size), 'zero_pixels': int((values == 0).sum()),
            'zero_fraction': float((values == 0).mean()),
            'nonzero_mm': describe(values[values > 0])}


def factory_numbers(packet):
    return {'serial': packet['get_device_info']['info']['serial_number'],
            'params': packet['get_camera_params'],
            'color_info': packet['get_camera_info']['info'],
            'internal_camera_link_from_depth_optical_transform': packet['camera_link_from_depth_optical']['transform']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence', type=Path, required=True)
    ap.add_argument('--tools', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    assert not a.output.exists(), 'Refuse overwrite'
    sys.path.insert(0, str(a.tools))
    from review_depth_registration import calibration, read_config
    from review_pair_sampling import selected_pixels, bbox
    from export_calibration_bundle import verify_bundle

    manifest_path = a.evidence/'runtime_manifest.json'
    archive_path = a.evidence/'runtime_closed.tar.gz'
    archive_sha = digest(archive_path.read_bytes())
    manifest = json.loads(manifest_path.read_text())
    assert archive_sha == manifest['archive_sha256']
    expected = {x['path']: x for x in manifest['files']}
    portable = a.evidence/'portable'
    verify_bundle(portable, json.loads((portable/'manifest.json').read_text()))
    config = portable/'detector_config.yaml'
    params = read_config(config)
    camera = calibration(params)
    roots = [('preview_high', 'new_pair05_serialized_return.eaPC4t', 'A_preview'),
             ('preview_low', 'new_pair05_A_formal.gupm4v', 'A_preview'),
             ('formal_60', 'new_pair05_A_batch60.3MFdVm', 'observation/batch_01')]
    packets, groups = [], {}
    with tarfile.open(archive_path, 'r:gz') as archive:
        assert set(archive.getnames()) == set(expected)
        for name, item in expected.items():
            data = archive.extractfile(name).read()
            assert len(data) == item['bytes'] and digest(data) == item['sha256'], name

        def raw(name):
            return archive.extractfile(name).read()

        for label, root, capture in roots:
            rows_path = root+'/'+capture+'/observer.jsonl'
            rows = [json.loads(s) for s in raw(rows_path).decode().splitlines() if s]
            factory = json.loads(raw(root+'/A_factory.json'))
            log = raw(root+'/A_depth.log').decode(errors='replace')
            match = re.search(r'\[(\d+\.\d+)\].*SENSOR_DEPTH is started', log)
            started = float(match.group(1)) if match else None
            groups[label] = {'frames': len(rows), 'source_root': root,
                             'rows_sha256': digest(raw(rows_path)),
                             'factory_sha256': digest(raw(root+'/A_factory.json')),
                             'factory_numbers': factory_numbers(factory),
                             'depth_started_epoch': started,
                             'depth_modes_from_log': re.findall(r'Resolution :([^\n]+)', log),
                             'exposure_limit': 'No per-frame native depth exposure/emitter state recorded; RGB controls do not establish those values.'}
            for row in rows:
                images = {}
                for key in ['rgb', 'depth']:
                    recorded = row['images'][key]
                    name = str(PurePosixPath(root)/capture/'evidence'/Path(recorded['path']).name)
                    data = raw(name)
                    assert digest(data) == recorded['sha256']
                    images[key] = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
                    assert images[key] is not None
                assert images['depth'].dtype == np.uint16 and images['rgb'].dtype == np.uint8
                info = row['latest']['/camera/depth/camera_info']
                selected, projected, mask, contour = selected_pixels(images['rgb'], images['depth'], info, params, camera)
                assert contour is not None
                packets.append({'label': label, 'source_root': root, 'row': row,
                                'rgb': images['rgb'], 'depth': images['depth'],
                                'info': info, 'selected': selected, 'mask': mask,
                                'source_images': row['images']})

    reference = packets[0]
    footprint = reference['selected'].copy()
    assert int(footprint.sum()) >= 800
    # Diagnostic control ring only, not a table plane or extra cube samples.
    ring = ((cv2.dilate(footprint.astype(np.uint8), np.ones((61,61),np.uint8)) > 0)
            & (cv2.dilate(footprint.astype(np.uint8), np.ones((21,21),np.uint8)) == 0))
    ref_info = {k:v for k,v in reference['info'].items() if k not in ['stamp','stamp_ns']}
    ref_factory = groups['preview_high']['factory_numbers']
    frames = []
    for packet in packets:
        rgb, depth, row = packet['rgb'], packet['depth'], packet['row']
        assert depth.shape == reference['depth'].shape
        selected, mask = packet['selected'], packet['mask'] > 0
        ref_mask = reference['mask'] > 0
        common = ring & (depth > 0) & (reference['depth'] > 0)
        stats = footprint_stats(depth, footprint)
        yy, xx = np.where(mask)
        frame = {'group': packet['label'], 'snapshot': row['snapshot'],
                 'epoch': row['epoch'], 'time_since_depth_start_s': row['epoch']-groups[packet['label']]['depth_started_epoch'],
                 'stamps_ns': {k:str(v) for k,v in row['stamps_ns'].items()},
                 'actual_q_rad': row['q_rad'], 'rgb_size': list(rgb.shape[1::-1]),
                 'depth_size': list(depth.shape[1::-1]), 'raw_depth_dtype': str(depth.dtype),
                 'source_images': {k:{'archive_path':packet['source_root']+'/'+('observation/batch_01' if packet['label']=='formal_60' else 'A_preview')+'/evidence/'+Path(v['path']).name,'sha256':v['sha256']} for k,v in row['images'].items()},
                 'original_selected_points': int(selected.sum()),
                 'native_reference_footprint': stats,
                 'native_control_ring': footprint_stats(depth, ring),
                 'control_ring_common_pixels_abs_difference_mm': describe(np.abs(depth[common].astype(float)-reference['depth'][common])),
                 'color_mask_pixels': int(mask.sum()), 'color_mask_bbox': bbox(mask),
                 'color_mask_center_xy': [float(xx.mean()),float(yy.mean())],
                 'color_mask_iou_to_reference': float((mask & ref_mask).sum()/(mask | ref_mask).sum()),
                 'all_native_nonzero_pixels': int(np.count_nonzero(depth)),
                 'depth_info_numeric_equal_to_reference': {k:v for k,v in packet['info'].items() if k not in ['stamp','stamp_ns']} == ref_info,
                 'factory_numeric_equal_to_reference': groups[packet['label']]['factory_numbers'] == ref_factory,
                 'same_stamp_depth_Info': str(row['stamps_ns']['depth']) == str(row['stamps_ns']['depth_info'])}
        frames.append(frame)
    for label, group in groups.items():
        subset = [f for f in frames if f['group'] == label]
        group['selected_points'] = describe([f['original_selected_points'] for f in subset])
        group['fixed_native_footprint_zero_fraction'] = describe([f['native_reference_footprint']['zero_fraction'] for f in subset])
        group['color_mask_iou_to_reference'] = describe([f['color_mask_iou_to_reference'] for f in subset])
        group['color_mask_bbox_unique'] = sorted({tuple(f['color_mask_bbox']) for f in subset})
        group['control_ring_native_nonzero_fraction'] = describe([1-f['native_control_ring']['zero_fraction'] for f in subset])
        group['control_ring_common_abs_difference_median_mm'] = describe([f['control_ring_common_pixels_abs_difference_mm']['median'] for f in subset])
        group['same_footprint_nonzero_median_mm'] = describe([f['native_reference_footprint']['nonzero_mm']['median'] for f in subset if f['native_reference_footprint']['nonzero_mm']['median'] is not None])
    baseline = json.loads((a.evidence/'p0_report.json').read_text())['frames']
    formal = [f for f in frames if f['group']=='formal_60']
    assert len(formal)==len(baseline)
    assert all(x['snapshot']==y['snapshot'] and x['original_selected_points']==y['native_selected_points'] for x,y in zip(formal,baseline))
    report = {'schema':'piper_pair05_offline_native_depth_audit_v1',
              'offline_only':True, 'device_access':False, 'raw_modified':False,
              'production_or_quality_modified':False, 'archive_sha256':archive_sha,
              'archived_original_files_verified':len(expected),
              'reference':{'group':frames[0]['group'],'snapshot':frames[0]['snapshot'],
                           'native_bbox_xyxy':bbox(footprint),'native_pixels':int(footprint.sum()),
                           'control_ring_pixels':int(ring.sum()),
                           'definition':'Fixed native support from first frame under unchanged production D->C selection; all later zero tests use RAW native depth directly, no projection, threshold or fill.'},
              'groups':groups,'frames':frames,
              'checks':{'all_60_original_selected_counts_replayed_exactly':True,
                        'all_q_equal': bool(np.array_equal(np.array([f['actual_q_rad'] for f in frames]),np.tile(frames[0]['actual_q_rad'],(len(frames),1)))),
                        'all_depth_Info_equal_except_stamps':all(f['depth_info_numeric_equal_to_reference'] for f in frames),
                        'all_factory_numeric_equal':all(f['factory_numeric_equal_to_reference'] for f in frames),
                        'all_depth_Info_same_stamp':all(f['same_stamp_depth_Info'] for f in frames),
                        'source_archive_SHA_unchanged_after':digest(archive_path.read_bytes()) == archive_sha},
              'limits':['Native zeros locate the failure before robot TF/IK and projection selection, but do not identify its optical, device-processing or driver cause.',
                        'Reopening the depth stream coincides with the change; this is observational, not a controlled restart/laser-state experiment.',
                        'Color stability and joint stability do not independently prove the entire physical scene was unchanged.',
                        'No IR intensity, per-frame native depth exposure, emitter state or confidence map is present; do not infer laser off from ir image disabled log.',
                        'The three supported preview faces still fail the original table/top condition; they are not qualified calibration points.']}
    a.output.mkdir()
    (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    np.savez_compressed(a.output/'fixed_native_regions.npz',reference_footprint=footprint,control_ring=ring)
    representatives = [packets[0],packets[3],packets[6],packets[-1]]
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,4,figsize=(14,7),layout='constrained')
    x0,y0,x1,y1 = bbox(footprint)
    margin=18
    roi=(slice(max(0,y0-margin),min(reference['depth'].shape[0],y1+margin+1)),slice(max(0,x0-margin),min(reference['depth'].shape[1],x1+margin+1)))
    cm=plt.get_cmap('turbo').copy();cm.set_bad('black')
    for col,p in enumerate(representatives):
        axes[0,col].imshow(cv2.cvtColor(p['rgb'],cv2.COLOR_BGR2RGB))
        axes[0,col].set_title(p['label']+' #'+str(p['row']['snapshot']))
        axes[0,col].axis('off')
        cut=p['depth'][roi]
        im=axes[1,col].imshow(np.ma.masked_equal(cut,0),vmin=180,vmax=280,cmap=cm,interpolation='nearest')
        axes[1,col].contour(footprint[roi],levels=[.5],colors=['white'],linewidths=.8)
        axes[1,col].set_title('RAW native depth; black=0')
    fig.colorbar(im,ax=axes[1,:].tolist(),label='Raw depth [mm]')
    fig.suptitle('Same fixed native footprint; no depth filling or replacement measurements')
    fig.savefig(a.output/'native_hole_comparison.png',dpi=130)
    plt.close(fig)
    print(json.dumps({'checks':report['checks'],'groups':{k:{x:v[x] for x in ['frames','selected_points','fixed_native_footprint_zero_fraction','same_footprint_nonzero_median_mm','color_mask_iou_to_reference','control_ring_native_nonzero_fraction','control_ring_common_abs_difference_median_mm']} for k,v in groups.items()}},indent=2))


if __name__=='__main__':
    main()
