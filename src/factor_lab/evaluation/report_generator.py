"""Report generator for evaluation results."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from factor_lab.evaluation.engine import EvaluationResult


class ReportGenerator:
    """Generates evaluation reports."""

    def __init__(self, template_dir: Path | None = None):
        self.template_dir = template_dir

    def generate_html_report(
        self,
        result: EvaluationResult,
        run_id: str,
        factor_name: str,
        protocol_version: str,
        output_path: Path,
    ) -> Path:
        """Generate HTML evaluation report."""
        generated_at = datetime.now().isoformat()

        html = f"""
        <html>
        <head>
            <title>Factor Evaluation Report - {factor_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                h1 {{ color: #333; }}
                .metric {{ margin: 20px 0; padding: 10px; background: #f5f5f5; }}
                .metric-label {{ font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>Factor Evaluation Report</h1>
            <div class="metric">
                <p><span class="metric-label">Run ID:</span> {run_id}</p>
                <p><span class="metric-label">Factor:</span> {factor_name}</p>
                <p><span class="metric-label">Protocol:</span> {protocol_version}</p>
                <p><span class="metric-label">Generated:</span> {generated_at}</p>
                <p><span class="metric-label">IC Mean:</span> {result.ic_mean:.4f}</p>
                <p>
                    <span class="metric-label">Rank IC Mean:</span>
                    {result.rank_ic_mean:.4f}
                </p>
                <p><span class="metric-label">Score:</span> {result.score:.4f}</p>
            </div>
        </body>
        </html>
        """

        _ = output_path.write_text(html, encoding="utf-8")
        return output_path

    def _add_metric_row(
        self,
        rows: list[dict[str, object]],
        metric: str,
        value: object,
    ) -> None:
        if not isinstance(value, (int, float)):
            return
        rows.append({"metric": metric, "value": float(value)})

    def generate_metrics_table(self, result: EvaluationResult) -> dict[str, object]:
        """Generate schema-compatible metrics table for storage."""
        rows: list[dict[str, object]] = []

        self._add_metric_row(rows, "ic.mean", result.ic_mean)
        self._add_metric_row(rows, "ic.std", result.ic_std)
        self._add_metric_row(rows, "ic.ir", result.ic_ir)
        self._add_metric_row(rows, "rank_ic.mean", result.rank_ic_mean)
        self._add_metric_row(rows, "rank_ic.std", result.rank_ic_std)
        self._add_metric_row(rows, "rank_ic.ir", result.rank_ic_ir)
        self._add_metric_row(rows, "turnover.mean", result.turnover_mean)
        self._add_metric_row(rows, "score", result.score)
        self._add_metric_row(rows, "coverage.ratio", result.coverage_ratio)
        self._add_metric_row(
            rows,
            "coverage.observation_count",
            result.observation_count,
        )
        self._add_metric_row(rows, "coverage.period_count", result.period_count)

        for quantile in sorted(result.quantile_returns):
            self._add_metric_row(
                rows,
                f"quantile_returns.q{quantile}",
                result.quantile_returns[quantile],
            )

        for metric, value in sorted(result.decay_curve.items()):
            self._add_metric_row(rows, f"decay_curve.{metric}", value)

        for metric, value in sorted(result.segment_stability.items()):
            self._add_metric_row(rows, f"segment_stability.{metric}", value)

        return {
            "schema_version": "1.0",
            "columns": ["metric", "value"],
            "rows": rows,
        }

    def generate_report_payload(
        self,
        *,
        result: EvaluationResult,
        run_id: str,
        factor_name: str,
        protocol_version: str,
        dataset_version: str,
        label_spec_version: str,
        preprocess_spec_version: str,
        candidate_count_context: Mapping[str, object],
        governance_notes: list[str],
        oos_summary: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Generate structured report payload."""
        generated_at = datetime.now().isoformat()
        metric_summary = result.to_dict()
        return {
            "run_id": run_id,
            "factor_name": factor_name,
            "protocol_version": protocol_version,
            "dataset_version": dataset_version,
            "label_spec_version": label_spec_version,
            "preprocess_spec_version": preprocess_spec_version,
            "generated_at": generated_at,
            "metric_summary": metric_summary,
            "metrics_table": self.generate_metrics_table(result),
            "candidate_count_context": candidate_count_context,
            "governance_notes": governance_notes,
            "oos_summary": oos_summary,
        }
