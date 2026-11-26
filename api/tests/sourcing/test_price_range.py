"""a4: món có giá về tay vượt giá bán tối đa của đề không được nằm trên cùng (chạy thật 26/11: 361–443k vs đề 30–150k)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.enums import SourcePlatform
from app.integrations.sources import SourceItem
from app.modules.sourcing import service
from app.modules.sourcing.ai_io import RankItemOut
from app.modules.sourcing.models import SourcingBrief


def _item(ext: str, price: str, currency: str) -> SourceItem:
    return SourceItem(platform=SourcePlatform.RAKUTEN, external_id=ext, url=f"https://x/{ext}", title=ext,
                      price_amount=Decimal(price), currency=currency)  # fmt: skip


async def test_over_range_candidates_are_penalised_and_flagged(db) -> None:
    rates = await service.fx_rates(db)
    brief = SourcingBrief(id=uuid.uuid4(), title="Phụ kiện tóc bé gái", price_max_vnd=150_000)
    pricey, cheap = _item("pricey", "1280", "JPY"), _item("cheap", "1.99", "CNY")
    ranked = {
        service._ref(pricey): RankItemOut(ref="a", title_vi="Bộ 10 kẹp tóc", keep=True, score=75, reason="Đáng xem vì đẹp."),
        service._ref(cheap): RankItemOut(ref="b", title_vi="Hộp 100 chun", keep=True, score=70, reason="Đáng xem vì rẻ."),
    }  # fmt: skip
    out = service.build_results(brief, [pricey, cheap], ranked, rates, origin=service.CandidateOrigin.BRIEF_SCAN)
    assert [c["title_vi"] for c in out] == ["Hộp 100 chun", "Bộ 10 kẹp tóc"]
    top, low = out
    assert top["ai_score"] == 70 and "price_flag" not in top["raw"]
    assert low["ai_score"] == 75 - service.OVER_PRICE_PENALTY
    assert "vượt giá bán tối đa" in low["rank_reason"] and low["raw"]["price_flag"]["price_max_vnd"] == 150_000


def test_price_over_range() -> None:
    assert service.price_over_range(361_000, 150_000)
    assert service.price_over_range(149_000, 150_000) is None
    assert service.price_over_range(None, 150_000) is None and service.price_over_range(361_000, None) is None
