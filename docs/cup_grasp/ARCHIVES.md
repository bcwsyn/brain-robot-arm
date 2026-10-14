# Stage 5 数据归档 / Data archives

全部第五步开发、失败、固定批次、GUI和发布目录水杯会话，以及阶段验证记录，保存在 `simulation_cup_grasp/validation/cup_grasp/archives/`。分段最大45 MiB；`manifest.json`记录每段及完整归档SHA-256，以及恢复后的每个文件SHA-256。

All stage 5 development, failed, frozen, GUI and publication cup sessions and validation records are preserved in split archives. Each part is at most 45 MiB. The manifest records part/archive checksums and every extracted file checksum.

在新工作区 / From the new workspace:

```bash
python3 scripts/restore_cup_grasp_archives.py --destination recovered_cup_grasp
```

目标目录必须不存在；脚本校验各段、整体归档、安全路径和所有恢复文件，不覆盖既有数据。会话位于 `recovered_cup_grasp/sessions/local/` 和 `sessions/publication/`，阶段验证位于 `recovered_cup_grasp/validation/`。

The destination must not exist. Restoration checks part/archive hashes, safe paths and every restored file, and refuses overwriting existing data. Historical absolute paths inside world/SDF/config logs are evidence; regenerate runtime worlds through the launch entry. Locked RGB-D/mask/calibration files are self-contained.

第四步训练与所有旧版本继续保留在旧 `simulation_cup/` 等目录。Stage 4 training archives and previous code versions remain in their original directories.
