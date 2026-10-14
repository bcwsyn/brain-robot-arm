#!/usr/bin/env python3
"""Preserve v1 and create corrected v2 labels from its raw rendered frames."""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np
import yaml

from render_cup_dataset import annotate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must not exist')
    source = json.loads((args.source/'manifest.json').read_text())
    shutil.copytree(args.source/'raw', args.output/'raw')
    for split in ('train', 'val', 'test'):
        for kind in ('images', 'labels'):
            (args.output/kind/split).mkdir(parents=True)
    rng = np.random.default_rng(20261014)
    images = []
    for group in source['groups']:
        annotate(args.output/'raw'/group['group'], args.output, group['split'], group['group'], rng, images)
    source.update(images=images, annotation_revision='v2: chroma fixture threshold includes dark neck; v1 preserved',
                  parent_manifest=str(args.source/'manifest.json'))
    (args.output/'manifest.json').write_text(json.dumps(source, indent=2)+'\n')
    (args.output/'data.yaml').write_text(yaml.safe_dump(dict(train='images/train', val='images/val',
        test='images/test', names={0: 'cup'}), sort_keys=False))
    print('Corrected dataset saved:', args.output, 'images=', len(images), flush=True)


if __name__ == '__main__':
    main()
