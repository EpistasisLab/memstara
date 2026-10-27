"""CSV column shape metadata; never compute imputation statistics before splitting."""
import math
import re

class ColumnTypes:
    def __init__(self):
        self.values = {}
        self.text = set()
        self.missing = set()
        self.numeric_ranges = {}

    def observe(self, column, value, is_missing):
        if is_missing:
            self.missing.add(column)
            return
        try:
            normalized = float(value)
            if not math.isfinite(normalized):
                return
            bounds = self.numeric_ranges.setdefault(column, [normalized, normalized, True])
            bounds[0], bounds[1] = min(bounds[0], normalized), max(bounds[1], normalized)
            bounds[2] = bounds[2] and normalized.is_integer()
        except ValueError:
            self.text.add(column)
            normalized = value
        seen = self.values.setdefault(column, set())
        if len(seen) < 3:
            seen.add(normalized)

    def metadata(self, columns):
        kinds = {}
        suggestions = {}
        for column in columns:
            observed = self.values.get(column, set())
            kinds[column] = ('categorical' if column in self.text or 0 < len(observed) <= 2
                             else 'numeric' if observed else 'empty')
            name = re.sub(r'[^a-z0-9]+', '_', column.lower()).strip('_')
            bounds = self.numeric_ranges.get(column)
            if column not in self.text and bounds and ((name == 'age_years' and 0 <= bounds[0] <= bounds[1] <= 130)
                             or (name.endswith('_count') and bounds[2] and bounds[0] >= 0)):
                suggestions[column] = 'continuous'
            elif kinds[column] == 'categorical':
                suggestions[column] = 'categorical'
            elif (
                bounds
                and bounds[2]
                and (name == "stage" or name.endswith("_stage"))
                and 0 <= bounds[0] <= bounds[1] <= 10
            ):
                suggestions[column] = 'categorical'
        return {
            "column_kinds": kinds,
            "suggested_predictor_types": suggestions,
            # Only numeric type-confirmation examples; never return free text or rows.
            "column_examples": {
                c: sorted(self.values.get(c, set())) for c in columns if c in self.missing and kinds[c] == "numeric"
            },
            "type_confirmation_columns": [
                c for c in columns if c in self.missing and kinds[c] == "numeric" and c not in suggestions
            ],
        }
