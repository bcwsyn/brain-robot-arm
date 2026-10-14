#!/usr/bin/env python3
"""Inspect recomputed cup RGB-D results; no ROS, Gazebo or actuator commands."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np


class CupReplayViewer:
    def __init__(self, root, capture, results, autoplay=False):
        self.root, self.capture, self.results = root, capture, results
        self.report = json.loads((results / 'results.json').read_text())
        self.records = self.report['records']
        if not self.records:
            raise ValueError('No view records in results.json')
        self.index, self.playing = 0, autoplay
        self.visited, self.snapshots = [], []
        self.closed = False
        self.cache = {}
        self.panel_width = min(420, max(220, (root.winfo_screenwidth() - 100) // 3))
        root.title('Cup RGB-D replay | 水杯视觉回放（只读）')
        root.resizable(False, False)
        ttk.Label(root, text='水杯识别与估径 / Cup segmentation and sizing',
                  font=('TkDefaultFont', 16)).pack(pady=(12, 4))
        ttk.Label(root, text='保存的 Gazebo RGB-D，重新推理；预张开为建议值，尚未执行夹持。\n'
                  'Recorded RGB-D, fresh inference. Suggested opening only; no cup motion or force loop.',
                  justify='center').pack(pady=(0, 8))
        self.image_label = ttk.Label(root)
        self.image_label.pack(padx=12)
        controls = ttk.Frame(root)
        controls.pack(pady=10)
        ttk.Button(controls, text='← 上一视角 / Previous',
                   command=lambda: self.select(self.index - 1)).pack(side='left', padx=3)
        for index, record in enumerate(self.records):
            ttk.Button(controls, text=f'{index + 1}: {record["view"]}',
                       command=lambda i=index: self.select(i)).pack(side='left', padx=3)
            root.bind(str(index + 1), lambda event, i=index: self.select(i))
        ttk.Button(controls, text='下一视角 / Next →',
                   command=lambda: self.select(self.index + 1)).pack(side='left', padx=3)
        self.play_button = ttk.Button(controls, command=self.toggle)
        self.play_button.pack(side='left', padx=3)
        ttk.Button(controls, text='保存图 / Save', command=self.save).pack(side='left', padx=3)
        ttk.Button(controls, text='Q 退出 / Quit', command=self.close).pack(side='left', padx=3)
        self.notice = tk.StringVar(value='1–5 / ← → 切换 | Space 播放/暂停 | Q / Esc 退出')
        ttk.Label(root, textvariable=self.notice).pack(pady=(0, 10))
        root.bind('<Left>', lambda event: self.select(self.index - 1))
        root.bind('<Right>', lambda event: self.select(self.index + 1))
        root.bind('<space>', lambda event: self.toggle())
        root.bind('<Escape>', lambda event: self.close())
        root.bind('q', lambda event: self.close())
        root.bind('Q', lambda event: self.close())
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.select(0)
        self.update_play_button()
        root.after(2000, self.tick)

    def compose(self, record):
        label = record['view']
        original = cv2.imread(str(self.capture / 'images' / f'{label}.png'))
        overlay = cv2.imread(str(self.results / f'{label}.jpg'))
        if original is None or overlay is None:
            raise ValueError(f'Missing source/overlay image for {label}')
        with np.load(self.capture / f'{label}.npz') as rgbd:
            depth = rgbd['depth_m']
        valid = np.isfinite(depth) & (depth > 0)
        colors = np.zeros((*depth.shape, 3), dtype=np.uint8)
        depth_caption = 'No valid depth'
        if valid.any():
            lo, hi = np.percentile(depth[valid], [2, 98])
            normalized = np.zeros(depth.shape, dtype=np.uint8)
            normalized[valid] = (255 * np.clip((depth[valid] - lo) / max(hi - lo, 1e-6), 0, 1)).astype(np.uint8)
            colors = cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)
            colors[~valid] = 0
            depth_caption = f'Depth: blue near / red far ({lo:.2f}..{hi:.2f} m)'
        geometry = record.get('geometry')
        if geometry:
            pixel = tuple(round(value) for value in geometry['pixel'])
            for image in (original, overlay):
                cv2.drawMarker(image, pixel, (0, 255, 255), cv2.MARKER_CROSS, 24, 2)
        height = round(original.shape[0] * self.panel_width / original.shape[1])
        canvas = np.full((height + 155, self.panel_width * 3, 3), 28, dtype=np.uint8)
        titles = ('Recorded RGB', 'YOLO mask + suggested grasp point', 'Registered depth (display range per view)')
        for index, (image, title) in enumerate(zip((original, overlay, colors), titles)):
            x = index * self.panel_width
            canvas[30:30 + height, x:x + self.panel_width] = cv2.resize(image, (self.panel_width, height))
            cv2.putText(canvas, title, (x + 8, 21), cv2.FONT_HERSHEY_SIMPLEX, .47, (230, 230, 230), 1, cv2.LINE_AA)
        y = height + 54
        if geometry:
            lines = [
                f'{label} | VALID | Diameter: {geometry["diameter_m"] * 1000:.2f} mm'
                f' | Suggested opening: {geometry["preopening_m"] * 1000:.2f} mm',
                f'Observed height: {geometry["observed_height_m"] * 1000:.2f} mm'
                f' | Grasp height: {geometry["grasp_height_m"] * 1000:.2f} mm'
                f' | Uncertainty parameter: {geometry["sigma_m"] * 1000:.2f} mm',
                f'Yellow cross = suggested body grasp point. {depth_caption}',
                'READ-ONLY replay. No executed jaw opening, arm motion or live force feedback.',
            ]
        else:
            lines = [f'{label} | REJECTED | {record.get("geometry_rejected", "No unique cup mask")}',
                     depth_caption, 'READ-ONLY replay. No actuator commands.']
        for index, line in enumerate(lines):
            cv2.putText(canvas, line, (10, y + index * 25), cv2.FONT_HERSHEY_SIMPLEX,
                        .52, (190, 240, 210) if geometry else (150, 150, 255), 1, cv2.LINE_AA)
        return canvas

    def select(self, index):
        self.index = index % len(self.records)
        record = self.records[self.index]
        label = record['view']
        if label not in self.cache:
            self.cache[label] = self.compose(record)
        self.canvas = self.cache[label]
        png = cv2.imencode('.png', self.canvas)[1].tobytes()
        self.photo = tk.PhotoImage(data=png)
        self.image_label.configure(image=self.photo)
        if label not in self.visited:
            self.visited.append(label)

    def update_play_button(self):
        self.play_button.configure(text='暂停 / Pause' if self.playing else '播放 / Play')

    def toggle(self):
        self.playing = not self.playing
        self.update_play_button()

    def tick(self):
        if not self.closed:
            if self.playing:
                self.select(self.index + 1)
            self.root.after(2000, self.tick)

    def save(self):
        destination = self.results.parent / 'screenshots'
        destination.mkdir(exist_ok=True)
        filename = f'{self.records[self.index]["view"]}-{time.time_ns()}.png'
        path = destination / filename
        if not cv2.imwrite(str(path), self.canvas):
            raise OSError(f'Could not save {path}')
        self.snapshots.append(str(path))
        self.notice.set(f'已保存 / Saved: {path.name}')
        print(f'Saved visual: {path}', flush=True)

    def close(self):
        if self.closed:
            return
        self.closed = True
        receipt = dict(closed_at=datetime.now(timezone.utc).isoformat(),
                       visited_views=self.visited, screenshots=self.snapshots,
                       model_sha256=self.report['model_sha256'],
                       mode='read-only recorded RGB-D with recomputed YOLO/geometry',
                       actuator_commands=False)
        (self.results.parent / 'viewer_session.json').write_text(json.dumps(receipt, indent=2) + '\n')
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--autoplay', action='store_true')
    parser.add_argument('--auto-close-seconds', type=float, help='Optional bounded desktop demonstration')
    args = parser.parse_args()
    if args.auto_close_seconds is not None and args.auto_close_seconds <= 0:
        parser.error('--auto-close-seconds must be positive')
    root = tk.Tk()
    viewer = CupReplayViewer(root, args.capture.resolve(), args.results.resolve(), args.autoplay)
    if args.auto_close_seconds is not None:
        root.after(round(args.auto_close_seconds * 1000), viewer.close)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        viewer.close()
        return 130
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
