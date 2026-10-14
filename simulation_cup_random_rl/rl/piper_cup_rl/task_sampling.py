"""Seeded task sampling shared by Gazebo acceptance and RL environments."""
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class TaskRegion:
    # Conservative tall-cup region, within the executor's wider parameter gate.
    start_x: tuple = (.38, .42)
    start_y: tuple = (-.12, -.08)
    goal_x: tuple = (.42, .44)
    goal_y: tuple = (.10, .16)

    def validate_goal(self, xy):
        if len(xy) != 2 or not all(math.isfinite(v) for v in xy):
            raise ValueError('Goal must contain two finite world coordinates in metres')
        if not (self.goal_x[0] <= xy[0] <= self.goal_x[1]
                and self.goal_y[0] <= xy[1] <= self.goal_y[1]):
            raise ValueError('Goal outside the conservative tall-cup test region')

    def sample(self, rng):
        return dict(start_xy=[rng.uniform(*self.start_x), rng.uniform(*self.start_y)],
                    goal_xy=[rng.uniform(*self.goal_x), rng.uniform(*self.goal_y)])


def make_plan(seed, count, goal_xy=None):
    if not isinstance(count, int) or count < 1:
        raise ValueError('Task count must be a positive integer')
    region, rng = TaskRegion(), random.Random(seed)
    if goal_xy is not None:
        region.validate_goal(goal_xy)
    trials = []
    for i in range(count):
        task = region.sample(rng)
        if goal_xy is not None:
            task['goal_xy'] = list(goal_xy)
        trials.append(dict(trial=i+1, **task))
    return dict(schema_version=1, seed=seed, frame='world', units='m',
                bounds=region.__dict__, trials=trials,
                failure_policy='stop_at_first_failure_no_motion_retry')
