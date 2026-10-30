import asyncio
import importlib
import os


def test_funnel_counts_and_no_backwards_moves(tmp_path):
    os.environ["RAHAT_DB"] = str(tmp_path / "t.db")
    from rahat import store
    importlib.reload(store)

    async def scenario():
        # two people inside a 3 km zone around Guwahati, one outside
        await store.upsert_user(1, lat=26.18, lon=91.75, consent=True)
        await store.upsert_user(2, lat=26.19, lon=91.76, consent=True)
        await store.upsert_user(3, lat=25.61, lon=85.14, consent=True)
        await store.upsert_user(4, lat=26.18, lon=91.75, consent=False)
        inside = await store.users_within(26.18, 91.75, 3)
        assert sorted(u["chat_id"] for u in inside) == [1, 2]

        aid = await store.create_alert("Guwahati", "red", 26.18, 91.75, 3, "hi", "en", None)
        for u in inside:
            await store.set_delivery(aid, u["chat_id"], "sent")
        await store.set_delivery(aid, 1, "safe")
        await store.set_delivery(aid, 1, "heard")  # late "heard" must not undo "safe"
        await store.set_delivery(aid, 2, "help")
        return await store.funnel(aid)

    f = asyncio.run(scenario())
    assert (f["alerted"], f["heard"], f["safe"], f["help"]) == (2, 2, 1, 1)
