"""工作台世界知识页：词条增改删、锁定、手工参考图、重新检索，以及删自动图后不再自动取图。"""

from hashlib import sha256
from types import SimpleNamespace
import asyncio
import json

from test_workspace import image_bytes, make_plugin  # noqa: F401 - pytest fixture
from test_world_knowledge_service import FakeFinder, jpeg, make_service


def call(coro):
    return asyncio.run(coro)


async def loaded(make_plugin, online=False):
    plugin = make_plugin()
    await plugin.on_load()
    if not online:  # SDK 2.23 的上下文总带 web 能力；这里模拟宿主未开联网检索
        plugin._world_service._online = lambda: False
    return plugin


def save(plugin, **fields):
    return plugin.workspace_knowledge_save(json.dumps(fields, ensure_ascii=False))


def test_manual_entry_save_lock_unlock_disable_and_delete(make_plugin):
    async def run():
        plugin = await loaded(make_plugin)
        try:
            created = (await save(plugin, name="T1", kind="esports_team", franchise="LCK", aliases=["SKT"],
                                  look="红黑队服，白色 T1 字标"))["entry"]
            assert created["status"] == "manual" and created["kind_label"] == "电竞战队"
            assert {"look", "aliases", "franchise"} <= set(created["locked_fields"])
            listed = await plugin.workspace_knowledge_list()
            assert listed["total"] == 1 and listed["items"][0]["id"] == created["id"]
            assert listed["enabled"] is False and listed["online"] is (getattr(plugin.ctx, "web", None) is not None)
            assert {"value": "esports_team", "label": "电竞战队"} in listed["kinds"]
            assert (await plugin.workspace_knowledge_list(search="skt"))["total"] == 1
            assert (await plugin.workspace_knowledge_list(search="原神"))["total"] == 0

            unlocked = (await save(plugin, id=created["id"], locked_fields=[]))["entry"]
            assert unlocked["locked_fields"] == []
            edited = (await save(plugin, id=created["id"], look="红黑队服", locked_fields=[]))["entry"]
            assert edited["locked_fields"] == ["look"]
            disabled = (await save(plugin, id=created["id"], disabled=True))["entry"]
            assert disabled["disabled"] is True and disabled["locked_fields"] == ["look"]
            refused = await plugin.workspace_knowledge_refresh(created["id"])
            assert "禁用" in refused["__workspace_error__"]

            assert "未知字段" in (await save(plugin, name="x", kind="other", refs=[]))["__workspace_error__"]
            assert "文字列表" in (await save(plugin, name="x", kind="other", aliases="a,b"))["__workspace_error__"]
            assert "重复" in (await save(plugin, name="SKT", kind="esports_team"))["__workspace_error__"]
            assert "ID" in (await plugin.workspace_knowledge_delete("../x"))["__workspace_error__"]

            assert await plugin.workspace_knowledge_delete(created["id"]) == {"deleted": True}
            assert (await plugin.workspace_knowledge_list())["total"] == 0
        finally:
            await plugin.on_unload()

    call(run())


def test_uploaded_image_becomes_manual_reference_and_auto_drop_disables_auto_images(make_plugin):
    async def run():
        plugin = await loaded(make_plugin)
        try:
            entry = (await save(plugin, name="芙宁娜", kind="game_character"))["entry"]
            raw = image_bytes()
            upload = plugin.ctx.paths.data_dir / "uploads" / ("a" * 64 + ".png")
            upload.parent.mkdir(parents=True, exist_ok=True)
            upload.write_bytes(raw)
            claimed = {"path": str(upload), "sha256": sha256(raw).hexdigest(), "upload_id": "a" * 64}

            async def claim_upload(upload_id):
                assert upload_id == "token"
                return claimed

            plugin.ctx.webui = SimpleNamespace(claim_upload=claim_upload)
            result = (await plugin.workspace_knowledge_image("token", entry["id"]))["entry"]
            assert len(result["refs"]) == 1 and result["refs"][0]["manual"] is True
            assert result["refs"][0]["preview"].startswith("data:image/webp;base64,")
            assert "path" not in json.dumps(result) and not upload.exists()

            manual = result["refs"][0]["file"]
            dropped = (await plugin.workspace_knowledge_image_drop(entry["id"], manual))["entry"]
            assert dropped["refs"] == [] and dropped["auto_image"] is True

            store = plugin._world_store
            auto = store.add_image(entry["id"], jpeg(), manual=False, source="mediawiki", size=(640, 400))
            dropped = (await plugin.workspace_knowledge_image_drop(entry["id"], auto["file"]))["entry"]
            assert dropped["auto_image"] is False
            assert "不存在" in (await plugin.workspace_knowledge_image_drop(entry["id"], auto["file"]))[
                "__workspace_error__"]
            reopened = (await save(plugin, id=entry["id"], auto_image=True))["entry"]
            assert reopened["auto_image"] is True and reopened["locked_fields"] == dropped["locked_fields"]
        finally:
            await plugin.on_unload()

    call(run())


def test_refresh_marks_expired_and_reports_when_offline(make_plugin):
    async def run():
        plugin = await loaded(make_plugin)
        try:
            entry = (await save(plugin, name="T1", kind="esports_team"))["entry"]
            result = await plugin.workspace_knowledge_refresh(entry["id"])
            assert result["started"] is False and "下次用到时" in result["message"]
            assert plugin._world_store.get(entry["id"])["expires_at"] == ""
        finally:
            await plugin.on_unload()

    call(run())


def test_service_refresh_entry_researches_and_fetches_image(tmp_path):
    async def run():
        service, ctx, store = make_service(tmp_path)
        entry = store.upsert_auto({"name": "芙宁娜", "kind": "game_character", "franchise": "原神", "found": False})
        assert service.refresh_entry(entry) is True
        await asyncio.gather(*service._background)
        refreshed = store.get(entry["id"])
        assert refreshed["status"] == "ok" and refreshed["look"] == "白蓝礼服，高礼帽，异色瞳"
        assert len(refreshed["refs"]) == 1 and ctx.web.queries == ["芙宁娜"]

        offline, _ctx, offline_store = make_service(tmp_path / "offline", web=False)
        assert offline.refresh_entry(offline_store.upsert_auto({"name": "T1", "kind": "esports_team"})) is False

    call(run())


def test_prepare_skips_auto_image_after_user_dropped_one(tmp_path):
    async def run():
        finder = FakeFinder()
        service, _ctx, store = make_service(tmp_path, finder=finder)
        await service.prepare("画芙宁娜在海边", max_images=2)
        entry = store.find("芙宁娜")
        assert finder.calls == 1 and len(entry["refs"]) == 1
        assert store.drop_image(entry["id"], entry["refs"][0]["file"])
        service._image_tried.clear()
        store.expire(entry["id"])
        result = await service.prepare("画芙宁娜在海边", max_images=2)
        assert finder.calls == 1 and result.images == []
        assert store.get(entry["id"])["auto_image"] is False

    call(run())
