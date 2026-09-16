"""Predeclared fresh-task confirmation after the upstream proposal gate."""
import math


def plan(ids, repeats):
    return [(phase, task_id, sample) for sample in range(repeats)
            for task_id in ids for phase in ('confirmation_baseline', 'confirmation_candidate')]


def evaluate(rows, ids, repeats, min_gain, seed, proposed):
    if [(r['phase'], r['id'], r['sample_id']) for r in rows] != plan(ids, repeats):
        raise ValueError('Incomplete or reordered confirmation')
    comparisons = []
    for before, after in zip(rows[::2], rows[1::2]):
        if before['skill_sha256'] != seed or after['skill_sha256'] != proposed:
            raise ValueError('Confirmation compared different skill bytes')
        for r in (before, after):
            if type(r['hard']) not in (int, float) or r['hard'] not in (0., 1.) or type(r['soft']) not in (int, float) or not math.isfinite(r['soft']) or not 0 <= r['soft'] <= 1:
                raise ValueError('Invalid confirmation score')
        a, b = .5 * (before['hard'] + before['soft']), .5 * (after['hard'] + after['soft'])
        comparisons.append({'id': before['id'], 'sample_id': before['sample_id'],
                            'baseline': a, 'candidate': b, 'gain': b - a})
    gains = [sum(r['gain'] for r in comparisons if r['sample_id'] == i) / len(ids) for i in range(repeats)]
    return {'passed': all(r['gain'] >= 0 for r in comparisons) and all(g >= min_gain for g in gains),
            'comparisons': comparisons, 'repeat_mean_gains': gains,
            'scope': 'Fresh replay confirmation on separate validation families; not a statistical significance test.'}
