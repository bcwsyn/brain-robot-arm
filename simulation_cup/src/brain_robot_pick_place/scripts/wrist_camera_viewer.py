#!/usr/bin/env python3

import tkinter as tk

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


IMAGE_TOPIC = '/wrist_camera/wrist_camera/image_raw'
IMAGE_QOS = QoSProfile(
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)


class WristCameraViewer(Node):
    def __init__(self, root):
        super().__init__('wrist_camera_viewer')
        self.root = root
        self.photo = None
        self.image_item = None
        self.overlay_items = []
        self.received_first_image = False

        self.root.title('PiPER wrist camera')
        self.status = tk.Label(
            self.root,
            text=f'等待相机图像：{IMAGE_TOPIC}',
            anchor='w',
        )
        self.status.pack(fill='x')
        self.canvas = tk.Canvas(
            self.root,
            width=640,
            height=480,
            background='#202020',
            highlightthickness=0,
        )
        self.canvas.pack()

        self.subscription = self.create_subscription(
            Image,
            IMAGE_TOPIC,
            self.on_image,
            IMAGE_QOS,
        )
        self.get_logger().info(
            f'Waiting for simulated wrist camera on {IMAGE_TOPIC} ...')

    @staticmethod
    def image_bytes(message):
        if message.encoding not in ('rgb8', 'bgr8'):
            raise ValueError(f'unsupported encoding: {message.encoding}')

        packed_row_bytes = message.width * 3
        source = bytes(message.data)
        if message.step == packed_row_bytes:
            packed = source
        else:
            packed = b''.join(
                source[row * message.step:row * message.step + packed_row_bytes]
                for row in range(message.height)
            )

        if message.encoding == 'rgb8':
            return packed

        converted = bytearray(packed)
        converted[0::3] = packed[2::3]
        converted[2::3] = packed[0::3]
        return bytes(converted)

    def on_image(self, message):
        try:
            rgb = self.image_bytes(message)
        except ValueError as error:
            self.get_logger().error(str(error), throttle_duration_sec=2.0)
            return

        ppm = (
            f'P6\n{message.width} {message.height}\n255\n'.encode('ascii') + rgb
        )
        # Tkinter can consume the binary PPM payload directly.  Encoding it as
        # Base64 while forcing the PPM decoder makes some Tk 8.6 builds reject
        # the first frame and stops the GUI's ROS polling callback.
        self.photo = tk.PhotoImage(data=ppm, format='PPM')

        self.canvas.configure(width=message.width, height=message.height)
        if self.image_item is None:
            self.image_item = self.canvas.create_image(
                0, 0, anchor='nw', image=self.photo)
        else:
            self.canvas.itemconfigure(self.image_item, image=self.photo)

        for item in self.overlay_items:
            self.canvas.delete(item)
        self.overlay_items.clear()

        center_x = message.width // 2
        center_y = message.height // 2
        cross_size = 22
        self.overlay_items.extend([
            self.canvas.create_line(
                center_x - cross_size,
                center_y,
                center_x + cross_size,
                center_y,
                fill='#00ff00',
                width=2,
            ),
            self.canvas.create_line(
                center_x,
                center_y - cross_size,
                center_x,
                center_y + cross_size,
                fill='#00ff00',
                width=2,
            ),
            self.canvas.create_text(
                center_x + 14,
                center_y - 14,
                text='目标中心',
                fill='#00ff00',
                anchor='sw',
            ),
        ])
        self.status.configure(
            text=(
                f'{message.width}×{message.height}  {message.encoding}  '
                f'中心=({center_x}, {center_y})'
            )
        )

        if not self.received_first_image:
            self.received_first_image = True
            self.get_logger().info(
                f'Receiving wrist camera images: '
                f'{message.width}x{message.height} {message.encoding}')


def main(args=None):
    rclpy.init(args=args)
    root = tk.Tk()
    node = WristCameraViewer(root)

    def poll_ros():
        if not rclpy.ok():
            root.destroy()
            return
        try:
            rclpy.spin_once(node, timeout_sec=0.0)
        except Exception as error:  # Keep the window alive and show the cause.
            node.get_logger().error(f'Image display failed: {error}')
            node.status.configure(text=f'图像显示失败：{error}')
        finally:
            if rclpy.ok():
                root.after(5, poll_ros)

    def close_window():
        if rclpy.ok():
            rclpy.shutdown()
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', close_window)
    root.after(0, poll_ros)
    try:
        root.mainloop()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
