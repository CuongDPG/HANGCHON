"""Dữ liệu mẫu chạy được và chạy lại không sinh trùng."""

from sqlalchemy import func, select

from app.modules.catalog.models import Drop, DropStatus, FindRequest, Product, ProductStatus
from app.modules.catalog.seed import seed_demo


async def test_seed_demo_is_idempotent(db, client):
    first = await seed_demo(db)
    await db.commit()
    assert first["products"] == 7 and first["drops"] == 3 and first["finds"] == 5
    again = await seed_demo(db)
    await db.commit()
    assert again["products"] == 0 and again["drops"] == 0 and again["finds"] == 0 and again["reviews"] == 0
    assert (await db.execute(select(func.count()).where(Product.status == ProductStatus.PUBLISHED))).scalar_one() == 7
    statuses = set((await db.execute(select(Drop.status))).scalars())
    assert {DropStatus.OPEN, DropStatus.SCHEDULED, DropStatus.FULFILLING} <= statuses
    assert (await db.execute(select(func.count()).select_from(FindRequest))).scalar_one() == 5

    shelf = (await client.get("/api/store/catalog/shelf")).json()
    assert shelf["total"] == 7
    card = next(i for i in shelf["items"] if i["name"] == "Bình giữ nhiệt 480 ml")
    assert card["seal"] == {"chosen": 1, "total": 24}
    assert card["proof"] == "Thử 3 tuần · Nhật"
    assert card["image"]["src"] and card["drop"]["label"] == "Đợt 12"
    drops = (await client.get("/api/store/catalog/drops")).json()
    assert drops["arrived"][0]["rating_avg"] and drops["arrived"][0]["order_count"] == 5
