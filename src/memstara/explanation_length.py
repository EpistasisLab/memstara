"""Per-execution Explanation narrative length; never edits contributed skills."""
DEFAULT_WORDS = 250
MAX_WORDS = 10000


def validate(value):
    if type(value) is not int or not 1 <= value <= MAX_WORDS:
        raise ValueError('Explanation report length must be a whole number from 1 to 10000 words')
    return value


def frozen_words(args, previous=None):
    # Old checkpoints retain their original unrestricted prompt.
    if previous is not None:
        value = previous.get('explanation_words')
        return None if value is None else validate(value)
    return validate(getattr(args, 'explanation_words', DEFAULT_WORDS))


def instruction(words):
    if words is None:
        return ''
    words = validate(words)
    return (f'\n\nExplanation report length: aim for approximately {words} words in the '
            'final human-readable Explanation narrative for this execution. This is a '
            'writing target, not an exact-count requirement. Prioritize the main findings, '
            'uncertainty and limitations. Preserve required tool calls, structured records '
            'and evidence references; this target does not limit their size. '
            'Do not truncate sentences to meet the target.\n')
