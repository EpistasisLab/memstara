"""CSV column shape metadata; never compute imputation statistics before splitting."""
import math

class ColumnTypes:
    def __init__(self):
        self.values = {}
        self.text = set()
        self.missing = set()

    def observe(self, column, value, is_missing):
        if is_missing:
            self.missing.add(column)
            return
        try:
            normalized = float(value)
            if not math.isfinite(normalized):
                return
        except ValueError:
            self.text.add(column)
            normalized = value
        seen = self.values.setdefault(column, set())
        if len(seen) < 3:
            seen.add(normalized)

    def metadata(self, columns):
        kinds = {}
        for column in columns:
            observed = self.values.get(column, set())
            kinds[column] = ('categorical' if column in self.text or 0 < len(observed) <= 2
                             else 'numeric' if observed else 'empty')
        return {
            'column_kinds': kinds,
            'type_confirmation_columns': [c for c in columns if c in self.missing and kinds[c] == 'numeric'],
        }
