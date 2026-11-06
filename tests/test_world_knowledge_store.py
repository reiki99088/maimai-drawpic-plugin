"""世界知识词条库：匹配、过期、锁定字段、参考图与损坏文件保护。"""

from datetime import timedelta
import json
import pytest

from test_review_regressions import module


def store_module():
    return module("infrastructure.storage.world_knowledge")


def test_short_ascii_names_match_on_word_boundaries() -> None:
    wk = store_module()
    assert wk.mention_position("T1 夺冠了", "T1") == 0
    assert wk.mention_position("t1赢了", "T1") == 0
    assert wk.mention_position("T10 也来了", "T1") == -1
    assert wk.mention_position("AT1 小队", "T1") == -1
    assert wk.mention_position("今天画芙宁娜", "芙 宁娜") >= 0
    assert wk.mention_position("一个字", "字") == -1


def test_auto_entries_expire_by_kind_and_keep_locked_fields(tmp_path) -> None:
    wk = store_module()
    store = wk.WorldKnowledgeStore(tmp_path)
    now = wk._now()
    event = store.upsert_auto({"name": "S16 总决赛", "kind": "esports_event", "facts": ["T1 3:1 获胜"]}, now=now)
    character = store.upsert_auto({"name": "芙宁娜", "kind": "game_character", "look": "白蓝礼服高礼帽"}, now=now)
    assert not wk.is_expired(event, now + timedelta(days=2))
    assert wk.is_expired(event, now + timedelta(days=4))
    assert not wk.is_expired(character, now + timedelta(days=60))

    edited = store.save_manual(character["id"], {"look": "蓝白异色瞳，高礼帽"})
    assert edited["locked_fields"] == ["look"]
    refreshed = store.upsert_auto(
        {"name": "芙宁娜", "kind": "game_character", "look": "错误外观", "franchise": "原神",
         "sources": [{"title": "wiki", "url": "https://wiki.invalid/a?token=secret"}]},
        now=now,
    )
    assert refreshed["look"] == "蓝白异色瞳，高礼帽"
    assert refreshed["franchise"] == "原神"
    assert refreshed["sources"] == [{"title": "wiki", "url": "https://wiki.invalid/a", "published_at": ""}]

    unlocked = store.save_manual(character["id"], {"locked_fields": []})
    assert unlocked["locked_fields"] == []
    missing = store.upsert_auto({"name": "不存在的东西", "kind": "product", "found": False}, now=now)
    assert missing["status"] == "not_found" and not wk.is_usable(missing)
    assert wk.is_expired(missing, now + timedelta(days=wk.NEGATIVE_TTL_DAYS, seconds=1))

    # 重新加载后数据一致，且文件是可读 UTF-8 JSON。
    reloaded = wk.WorldKnowledgeStore(tmp_path)
    assert [entry["name"] for entry in reloaded.list()] == ["S16 总决赛", "芙宁娜", "不存在的东西"]
    payload = json.loads((tmp_path / "world_knowledge" / "entries.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1 and "芙宁娜" in json.dumps(payload, ensure_ascii=False)


def test_manual_entries_never_expire_and_disabled_entries_stay_untouched(tmp_path) -> None:
    wk = store_module()
    store = wk.WorldKnowledgeStore(tmp_path)
    manual = store.save_manual(None, {"name": "T1", "kind": "esports_team", "aliases": ["SKT", "T1"],
                                      "look": "红黑队服"})
    assert manual["status"] == "manual" and manual["aliases"] == ["SKT"]
    assert not wk.is_expired(manual)
    assert [entry["name"] for entry in store.mentioned("SKT 今天赢了")] == ["T1"]
    assert store.mentioned("T10 今天赢了") == []
    with pytest.raises(ValueError, match="重复"):
        store.save_manual(None, {"name": "skt", "kind": "esports_team"})

    store.save_manual(manual["id"], {"disabled": True})
    untouched = store.upsert_auto({"name": "T1", "kind": "esports_team", "look": "新外观"})
    assert untouched["disabled"] and untouched["look"] == "红黑队服"
    assert store.mentioned("T1") == []


def test_reference_images_prefer_manual_and_clean_files(tmp_path) -> None:
    wk = store_module()
    store = wk.WorldKnowledgeStore(tmp_path)
    entry = store.upsert_auto({"name": "芙宁娜", "kind": "game_character", "look": "高礼帽"})
    auto_one = store.add_image(entry["id"], b"auto-1", manual=False, page_url="https://wiki.invalid/p?x=1")
    assert auto_one["page_url"] == "https://wiki.invalid/p"
    auto_two = store.add_image(entry["id"], b"auto-2", manual=False)
    assert not store.image_path(auto_one["file"]).exists()
    manual_one = store.add_image(entry["id"], b"manual-1", manual=True)
    manual_two = store.add_image(entry["id"], b"manual-2", manual=True)
    refs = store.get(entry["id"])["refs"]
    assert [ref["file"] for ref in refs] == [manual_two["file"], manual_one["file"]]
    assert not store.image_path(auto_two["file"]).exists()
    assert store.add_image(entry["id"], b"auto-3", manual=False) is None
    assert store.read_image(entry["id"], manual_one["file"]) == b"manual-1"
    assert store.read_image(entry["id"], "../entries.json") is None

    assert store.drop_image(entry["id"], manual_one["file"])
    assert not store.image_path(manual_one["file"]).exists()
    assert store.delete(entry["id"])
    assert not store.image_path(manual_two["file"]).exists()
    with pytest.raises(ValueError, match="格式"):
        store.add_image("w_missing", b"x", manual=True, suffix=".svg")


def test_full_library_prunes_least_recently_used_auto_entries(tmp_path, monkeypatch) -> None:
    wk = store_module()
    monkeypatch.setattr(wk, "MAX_ENTRIES", 3)
    store = wk.WorldKnowledgeStore(tmp_path)
    keep = store.save_manual(None, {"name": "手工", "kind": "other", "look": "x"})
    old = store.upsert_auto({"name": "旧词条", "kind": "other", "look": "x"})
    store.add_image(old["id"], b"old-image", manual=False)
    image = store.get(old["id"])["refs"][0]["file"]
    fresh = store.upsert_auto({"name": "新词条", "kind": "other", "look": "x"})
    store.touch_used([fresh["id"]])
    store.upsert_auto({"name": "第四条", "kind": "other", "look": "x"})
    names = {entry["name"] for entry in store.list()}
    assert names == {"手工", "新词条", "第四条"}
    assert keep["id"] in {entry["id"] for entry in store.list()}
    assert not store.image_path(image).exists()


def test_corrupted_library_is_preserved_and_refused(tmp_path) -> None:
    wk = store_module()
    path = tmp_path / "world_knowledge" / "entries.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    store = wk.WorldKnowledgeStore(tmp_path)
    with pytest.raises(wk.WorldKnowledgeStoreError, match="保留原件"):
        store.list()
    with pytest.raises(wk.WorldKnowledgeStoreError):
        store.upsert_auto({"name": "T1", "kind": "esports_team"})
    assert path.read_text(encoding="utf-8") == "{not json"
