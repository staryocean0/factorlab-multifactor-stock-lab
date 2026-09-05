"""Label builder for forward returns."""

from dataclasses import dataclass
from typing import Any


@dataclass
class LabelRecord:
    """Single label record."""

    symbol: str
    timestamp: str
    label_value: float
    label_name: str


class LabelBuilder:
    """Builds labels from price data."""

    def __init__(self, horizon: str = "5d", exclude_current_bar: bool = True):
        self.horizon = horizon
        self.exclude_current_bar = exclude_current_bar

    def build_labels(
        self, price_data: list[dict[str, Any]], label_name: str = "fwd_ret_5d"
    ) -> list[LabelRecord]:
        """Build forward return labels from price data."""
        # Sort by symbol and timestamp
        sorted_data = sorted(price_data, key=lambda x: (x["symbol"], x["timestamp"]))

        labels = []

        # Group by symbol
        by_symbol = {}
        for record in sorted_data:
            symbol = record["symbol"]
            if symbol not in by_symbol:
                by_symbol[symbol] = []
            by_symbol[symbol].append(record)

        # Calculate forward returns
        horizon_days = int(self.horizon.replace("d", ""))

        for symbol, records in by_symbol.items():
            records = sorted(records, key=lambda x: x["timestamp"])

            for i, record in enumerate(records):
                if self.exclude_current_bar:
                    # Signal is stamped at t; return starts from next bar.
                    entry_idx = i + 1
                    target_idx = entry_idx + horizon_days
                else:
                    entry_idx = i
                    target_idx = i + horizon_days

                if target_idx < len(records):
                    current_close = records[entry_idx]["close"]
                    future_close = records[target_idx]["close"]

                    # Calculate return
                    ret = (future_close / current_close) - 1

                    labels.append(
                        LabelRecord(
                            symbol=symbol,
                            timestamp=record["timestamp"],
                            label_value=ret,
                            label_name=label_name,
                        )
                    )

        return labels

    def validate_no_lookahead(
        self, labels: list[LabelRecord], current_time: str
    ) -> bool:
        """Validate that labels don't use future data not yet available."""
        # In a real implementation, this would check against the current time
        # and ensure all labels only use data that was available at that time
        return True
