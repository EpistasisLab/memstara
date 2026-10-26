"""Public experiment units derived from immutable scheduler metadata."""

def identity(config, position):
    if type(position) is not int or position < 1:
        return {}
    plan = config.get('combination_plan')
    if isinstance(plan, dict):
        count, total = plan.get('combinations'), plan.get('total_loops')
        start = plan.get('start_index', 0)
        if (type(count) is not int or count < 1 or type(total) is not int
                or position > total or type(start) is not int or not 0 <= start < count):
            return {}
        offset = (position - 1) % count
        if plan.get('execution_order') == 'pipeline_replicates_first':
            repeats = plan.get('repetitions')
            if type(repeats) is not int or repeats < 1:
                return {}
            cycle_size = count * repeats
            offset = ((position - 1) // repeats) % count
            remainder = total % cycle_size
            planned = total // cycle_size * repeats + min(repeats, max(0, remainder - offset * repeats))
            return {'pipeline_number': (start + offset) % count + 1, 'pipeline_count': count,
                    'replicate_number': (position - 1) // cycle_size * repeats + (position - 1) % repeats + 1,
                    'replicate_count': planned}
        return {'pipeline_number': (start + offset) % count + 1, 'pipeline_count': count,
                'replicate_number': (position - 1) // count + 1,
                'replicate_count': total // count + int(offset < total % count)}
    total = config.get('waves')
    return {'pipeline_number': 1, 'pipeline_count': 1, 'replicate_number': position,
            'replicate_count': total if type(total) is int and total > 0 else None}
