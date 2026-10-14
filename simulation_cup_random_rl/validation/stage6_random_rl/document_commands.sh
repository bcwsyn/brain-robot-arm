bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --random-goal

bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --goal-xy 0.43 0.14

bash scripts/setup_cup_rl_env.sh
bash scripts/run_cup_rl.sh --steps 5000 --seed 20261015 --output artifacts/cup_rl/my_smoke
.venv-rl/bin/python -s scripts/evaluate_cup_rl.py --run artifacts/cup_rl/my_smoke \
  --episodes 20 --seed 2026101600 --output validation/my_policy_evaluation

.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/stage6_random_rl/env_canonical --episode 1
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/stage6_random_rl/policy_frozen20 --episode 1

bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --random-goal
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --goal-xy 0.43 0.14

bash scripts/setup_cup_rl_env.sh
bash scripts/run_cup_rl.sh --steps 5000 --seed 20261015 --output artifacts/cup_rl/my_smoke
.venv-rl/bin/python -s scripts/evaluate_cup_rl.py --run artifacts/cup_rl/my_smoke \
  --episodes 20 --seed 2026101600 --output validation/my_policy_evaluation

.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/stage6_random_rl/env_canonical --episode 1
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/stage6_random_rl/policy_frozen20 --episode 1

git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation_cup_random_rl

bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --random-goal

bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --goal-xy 0.43 0.14

bash scripts/run_cup_grasp_sim.sh --headless --seed 2026101510 --batch-trials 20 --random-goal

python3 scripts/analyze_random_cup_session.py log/visual_sim/cup-实际时间戳 \
  --output validation/my_random_baseline.json

bash scripts/setup_cup_rl_env.sh

source /opt/ros/humble/setup.bash
source install/setup.bash
.venv-rl/bin/python -s scripts/build_cup_rl_model.py

.venv-rl/bin/python -s -m pytest -q rl/tests
.venv-rl/bin/python -s scripts/verify_cup_rl_env.py \
  --output validation/my_rl_environment --episodes 3 --seed 100
bash scripts/run_cup_rl.sh --steps 5000 --seed 20261015 \
  --output artifacts/cup_rl/my_smoke

bash scripts/run_cup_rl.sh --steps 200000 --seed 20261015 \
  --output artifacts/cup_rl/my_long_run --randomize-dynamics

.venv-rl/bin/python -s scripts/evaluate_cup_rl.py \
  --run artifacts/cup_rl/my_smoke --episodes 20 --seed 2026101600 \
  --output validation/my_policy_evaluation

bash scripts/run_cup_rl.sh --steps 3000 --seed 20261015 \
  --resume artifacts/cup_rl/my_smoke --output artifacts/cup_rl/my_resumed

.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/my_rl_environment --episode 1
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/my_policy_evaluation --episode 1

MUJOCO_GL=egl .venv-rl/bin/python -s scripts/replay_cup_rl.py \
  validation/my_rl_environment --episode 1 --video validation/scripted_replay.mp4
MUJOCO_GL=egl .venv-rl/bin/python -s scripts/replay_cup_rl.py \
  validation/my_rl_environment --episode 1 --wrist --video validation/wrist_replay.mp4

git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation_cup_random_rl

bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --random-goal

bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --goal-xy 0.43 0.14

bash scripts/run_cup_grasp_sim.sh --headless --seed 2026101510 --batch-trials 20 --random-goal

python3 scripts/analyze_random_cup_session.py log/visual_sim/cup-ACTUAL-TIMESTAMP \
  --output validation/my_random_baseline.json

bash scripts/setup_cup_rl_env.sh

source /opt/ros/humble/setup.bash
source install/setup.bash
.venv-rl/bin/python -s scripts/build_cup_rl_model.py

.venv-rl/bin/python -s -m pytest -q rl/tests
.venv-rl/bin/python -s scripts/verify_cup_rl_env.py \
  --output validation/my_rl_environment --episodes 3 --seed 100
bash scripts/run_cup_rl.sh --steps 5000 --seed 20261015 \
  --output artifacts/cup_rl/my_smoke

bash scripts/run_cup_rl.sh --steps 200000 --seed 20261015 \
  --output artifacts/cup_rl/my_long_run --randomize-dynamics

.venv-rl/bin/python -s scripts/evaluate_cup_rl.py \
  --run artifacts/cup_rl/my_smoke --episodes 20 --seed 2026101600 \
  --output validation/my_policy_evaluation

bash scripts/run_cup_rl.sh --steps 3000 --seed 20261015 \
  --resume artifacts/cup_rl/my_smoke --output artifacts/cup_rl/my_resumed

.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/my_rl_environment --episode 1
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/my_policy_evaluation --episode 1

MUJOCO_GL=egl .venv-rl/bin/python -s scripts/replay_cup_rl.py \
  validation/my_rl_environment --episode 1 --video validation/scripted_replay.mp4
MUJOCO_GL=egl .venv-rl/bin/python -s scripts/replay_cup_rl.py \
  validation/my_rl_environment --episode 1 --wrist --video validation/wrist_replay.mp4
