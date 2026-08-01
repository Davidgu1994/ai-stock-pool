import unittest
from datetime import datetime, timezone

from discovery_engine import (
    Signal,
    attribution_for,
    candidate_scores,
    map_a_shares,
    recommendation,
    source_rows_from_pool,
)


def make_signal(index: int, *, direct: bool) -> Signal:
    return Signal(
        signal_id=f"signal-{index}",
        date=datetime.now(timezone.utc).date().isoformat(),
        source_type="news",
        source_name="Test News",
        source_url=f"https://example.com/{index}",
        title="AMD inference update",
        summary="Direct company evidence" if direct else "Theme-only evidence",
        theme="AI inference serving and networking",
        tickers_mentioned="AMD" if direct else "",
        mapped_tickers="AMD",
        mapped_a_shares="",
        evidence_strength=70,
        confidence=70,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class DiscoveryEngineTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "pool_by_ticker": {},
            "source_by_ticker": {},
            "company_to_ticker": {},
        }
        self.papers = [{"paper_signal_score": 100, "arxiv_id": f"paper-{index}"} for index in range(4)]
        self.quote = {"changePercent": 0}

    def test_deploy_snapshot_reconstructs_a_share_sources(self):
        pool = [
            {
                "ticker": "300001.SZ",
                "company": "示例公司",
                "market": "A股",
                "source": "NVDA; AMD",
                "status": "观察",
                "sector": "AI服务器",
                "role": "服务器部件",
                "key_focus": "订单验证",
            }
        ]
        _us_rows, a_rows = source_rows_from_pool(pool)
        self.assertEqual(a_rows[0]["source_us"], "NVDA; AMD")
        mapped = map_a_shares("", ["AI inference serving and networking"], ["AMD"], {"a_rows": a_rows})
        self.assertEqual(mapped, ["300001.SZ"])

    def test_direct_news_can_reach_propose_add_with_company_proof(self):
        signals = [make_signal(index, direct=True) for index in range(4)]
        scores, _notes = candidate_scores("AMD", signals, self.papers, self.quote, self.context)
        total = sum(scores.values())
        attribution, _score = attribution_for("AMD", signals, {})
        self.assertEqual(total, 80)
        self.assertEqual(
            recommendation("AMD", total, "not_in_pool", signals, self.papers, attribution, scores["financial_confirmation_score"]),
            "propose_add",
        )

    def test_theme_only_mapping_cannot_be_promoted(self):
        signals = [make_signal(index, direct=False) for index in range(4)]
        scores, notes = candidate_scores("AMD", signals, self.papers, self.quote, self.context)
        total = sum(scores.values())
        attribution, _score = attribution_for("AMD", signals, {})
        self.assertLessEqual(total, 100)
        self.assertIn("仅为主题代理，缺少公司级直接归因", notes)
        self.assertNotEqual(
            recommendation("AMD", total, "not_in_pool", signals, self.papers, attribution, scores["financial_confirmation_score"]),
            "propose_add",
        )


if __name__ == "__main__":
    unittest.main()
