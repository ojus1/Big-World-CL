"""Versioned experiment contracts. These objects stay in the trusted runner."""
from dataclasses import asdict, dataclass
import hashlib
import json

SEED_SKILL = '''# Work process

Read the current employee request and source files. Determine which published
requirements apply to this task and date. Compute the requested output from the
records, check completeness and consistency, and create the requested artifact.
Verify substantive work as well as submission requirements before committing.
Treat remembered guidance as revisable when current evidence changes.
'''


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class ExperimentConfig:
    algorithm: str = 'no_learning'
    seed: int = 101
    days: int = 24
    split: str = 'dev'
    state_mode: str = 'skill_transfer'
    decision_every: int = 4
    update_every: int = 4
    update_days: tuple[int, ...] | None = None
    feedback_delay: int = 1
    max_iterations: int = 16
    max_output_tokens: int = 4096
    max_work_sessions: int = 144
    max_run_seconds: int = 14400
    max_learning_calls: int = 2880
    max_learning_tokens: int = 36000000
    train_cases: int = 2
    val_cases: int = 2
    edit_budget: int = 4
    skillopt_rollouts_k: int = 1
    enterprise_count: int = 2
    consumer_count: int = 3
    max_learning_calls_per_epoch: int | None = None
    max_learning_tokens_per_epoch: int | None = None
    max_learning_seconds_per_epoch: int | None = None
    max_actor_interviews: int | None = None
    focal_employee: str | None = None
    schema_version: int = 1

    def __post_init__(self):
        if self.algorithm not in ('no_learning', 'skillopt'):
            raise ValueError('algorithm must be no_learning or skillopt')
        if self.split not in ('dev', 'test') or self.state_mode not in ('skill_transfer', 'full_deployment'):
            raise ValueError('Unknown scenario split or state mode')
        for key in ('days','decision_every','update_every','feedback_delay','max_iterations',
                    'max_output_tokens','max_work_sessions','max_run_seconds','max_learning_calls',
                    'max_learning_tokens','train_cases','val_cases','edit_budget','skillopt_rollouts_k',
                    'enterprise_count','consumer_count'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(key + ' must be a positive integer')
        if self.enterprise_count < 2 or self.consumer_count < self.enterprise_count:
            raise ValueError('At least two enterprises and one consumer per enterprise are required')
        for key in ('max_learning_calls_per_epoch', 'max_learning_tokens_per_epoch',
                    'max_learning_seconds_per_epoch', 'max_actor_interviews'):
            value = getattr(self, key)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(key + ' must be None or a positive integer')
        if type(self.seed) is not int or not 0 <= self.seed < 1_000_000:
            raise ValueError('seed must be an integer in [0,1000000)')
        if self.days < 8:
            raise ValueError('At least eight days are required for separated change/exception/reversal phases')
        if self.update_days is not None:
            if (not isinstance(self.update_days, (list, tuple)) or not self.update_days
                    or any(type(day) is not int or not 0 <= day < self.days - 1 for day in self.update_days)
                    or list(self.update_days) != sorted(set(self.update_days))):
                raise ValueError('update_days must be sorted distinct action days with future work remaining')
            object.__setattr__(self, 'update_days', tuple(self.update_days))

    def public(self):
        result = asdict(self)
        if result['update_days'] is not None:
            result['update_days'] = list(result['update_days'])
        return result

    @property
    def fingerprint(self):
        return digest(self.public())


def scenario(config):
    # Disjoint seeded population/data namespaces; frozen mechanism contract.
    namespace = 0 if config.split == 'dev' else 1_000_000
    seed = namespace + config.seed
    offset = seed % 2
    change = max(1, config.days // 4) + offset
    exception = max(change + 1, config.days // 2)
    reversal = min(config.days - 1, max(exception + 1, 3 * config.days // 4))
    return {'seed': seed, 'split': config.split, 'days': config.days,
            'population': {'firms': config.enterprise_count, 'employees': config.enterprise_count * 3,
                           'consumers': config.consumer_count, 'agencies': 1},
            'max_actor_interviews': config.max_actor_interviews,
            'change_day': change, 'exception_window': [exception, reversal],
            'reversal_day': reversal, 'settlement_delay': 2,
            'shock_schedule': [{'day': change, 'corridor': 'disrupted', 'supply_delay': 2},
                               {'day': reversal, 'corridor': 'open', 'supply_delay': 0}],
            'demand': 'One exogenous work obligation per employee per day; native consumer orders are additional.'}


def regime_at(spec, day):
    if day >= spec['reversal_day']:
        return 'reversal'
    if spec['exception_window'][0] <= day < spec['exception_window'][1]:
        return 'exception'
    if day >= spec['change_day']:
        return 'changed'
    return 'base'


def experience_split(source_task_id):
    # Retries remain in one pool, regardless of date or success. Different
    # employee roles must not fall into fixed split buckets.
    return 'val' if int(digest(source_task_id)[:8], 16) % 3 == 1 else 'train'


def select_experiences(records, employee, now, train_count, val_count):
    # Latest eligible observation per underlying obligation; retries must not
    # inflate sample size or occupy both training and validation pools.
    unique = {}
    for r in records:
        if (r['employee'] == employee and r['available_day'] <= now
                and r.get('feedback_available_day', r['available_day']) <= now
                and r['split'] in ('train', 'val')):
            unique[r['source_session']] = r
    eligible = list(unique.values())
    result = []
    for split, count in (('train', train_count), ('val', val_count)):
        result.extend([r for r in eligible if r['split'] == split][-count:])
    return result
