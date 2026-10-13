# Cup segmentation model

`cup_yolov8n_seg_v2.pt` is the recommended frozen single-class YOLOv8n segmentation model. Its `cup` class is **0**; the original COCO model uses **41**. Query the model's class names rather than assuming either index.

SHA-256: `8f7afc15dd047edabc3fc0459e539e11220b19adbcc28c2da955aa07043cbeef`.

Training used project-generated Gazebo stepped-cup images. Real-camera accuracy and force-controlled cup pick-and-place have not been validated. Full provenance and dependency license references are in `cup_model_provenance.json`; all training revisions are preserved in the stage archives.

推荐权重为单类别模型，cup 编号为 0。数据来自 Gazebo，尚未验证真实相机或完整水杯力控取放。请勿把该模型的合成测试指标视作实机成功率。来源、校验值和许可证引用见同目录 JSON。
