"""世界知识取图来源：离线模拟 Data Dragon、MediaWiki 与网搜候选，不访问网络。"""

from io import BytesIO
from typing import Dict, List
import asyncio
import json
import pytest
from PIL import Image

from test_review_regressions import module


def picture(size=(800, 600), mode="RGB") -> bytes:
    output = BytesIO()
    Image.new(mode, size, (200, 120, 140, 128) if mode == "RGBA" else "#c8788c").save(output, "PNG")
    return output.getvalue()


def make_finder(tmp_path, pages: Dict[str, str], images: Dict[str, bytes]):
    sources = module("infrastructure.media.world_sources")
    downloads = module("infrastructure.media.downloads")
    calls: List[str] = []

    async def fetch_text(url, **kwargs):
        calls.append(url)
        assert kwargs["headers"]["User-Agent"].startswith("MaiMaiDrawpic/")
        for prefix, body in pages.items():
            if url.startswith(prefix):
                return body, url
        raise downloads.PublicFetchError("资料抓取失败：HTTP 404")

    async def download(url, **kwargs):
        calls.append(url)
        assert kwargs["base_url"] == "https://reference.invalid"
        if url not in images:
            raise module("domain.errors").ProviderDownloadError("图片结果传输中断，未重新提交生成请求")
        return images[url]

    proxy = module("infrastructure.http").HttpProxySettings.disabled()
    finder = sources.WorldImageFinder(
        proxy_settings=proxy, cache_dir=tmp_path, fetch_text=fetch_text, download=download,
    )
    return finder, calls


def test_url_filters_drop_vector_animated_and_site_defaults() -> None:
    sources = module("infrastructure.media.world_sources")
    ok = sources.acceptable_image_url
    assert ok("https://img.invalid/furina.png", "game_character")
    assert not ok("https://img.invalid/thumb/a/ab/Furina.svg/1024px-Furina.svg.png", "game_character")
    assert not ok("https://img.invalid/anim.gif", "game_character")
    assert not ok("https://img.invalid/Site-community-image.png", "game_character")
    assert not ok("https://img.invalid/T1_logo.png", "game_character")
    assert ok("https://img.invalid/T1_logo.png", "esports_team")
    assert not ok("https://img.invalid/favicon.png", "esports_team")
    assert not ok("ftp://img.invalid/a.png", "brand")


def test_mediawiki_page_detection() -> None:
    api = module("infrastructure.media.world_sources").mediawiki_api
    assert api("https://zh.wikipedia.org/wiki/T1_(%E7%94%B5%E7%AB%9E)") == ("https://zh.wikipedia.org/w/api.php", "T1 (电竞)")
    assert api("https://genshin-impact.fandom.com/wiki/Furina") == ("https://genshin-impact.fandom.com/api.php", "Furina")
    assert api("https://genshin-impact.fandom.com/zh/wiki/芙宁娜") == ("https://genshin-impact.fandom.com/zh/api.php", "芙宁娜")
    # 没装 PageImages 或只给旧图的站点不再查。
    assert api("https://wiki.biligame.com/ys/芙宁娜") is None
    assert api("https://liquipedia.net/leagueoflegends/T1") is None
    assert api("https://leagueoflegends.fandom.com/wiki/T1") is None
    assert api("https://lol.fandom.com/wiki/Faker") is None
    assert api("https://zh.moegirl.org.cn/芙宁娜") == ("https://zh.moegirl.org.cn/api.php", "芙宁娜")
    assert api("https://zh.wikipedia.org/wiki/Special:Search") is None
    assert api("http://zh.wikipedia.org/wiki/T1") is None
    assert api("https://news.invalid/article/1") is None


def test_ddragon_champion_is_found_and_cached(tmp_path) -> None:
    ddragon = "https://ddragon.leagueoflegends.com"
    champions = {"data": {"Aatrox": {"id": "Aatrox", "name": "暗裔剑魔", "title": "亚托克斯"}}}
    english = {"data": {"Aatrox": {"id": "Aatrox", "name": "Aatrox", "title": "the Darkin Blade"}}}
    image_url = f"{ddragon}/cdn/img/champion/loading/Aatrox_0.jpg"
    pages = {
        f"{ddragon}/api/versions.json": json.dumps(["15.1.1", "15.0.1"]),
        f"{ddragon}/cdn/15.1.1/data/zh_CN/champion.json": json.dumps(champions, ensure_ascii=False),
        f"{ddragon}/cdn/15.1.1/data/en_US/champion.json": json.dumps(english),
    }

    async def run() -> None:
        finder, calls = make_finder(tmp_path, pages, {image_url: picture((308, 560))})
        image, reasons = await finder.find(
            name="亚托克斯", aliases=["剑魔"], kind="game_character", franchise="英雄联盟", pages=[],
        )
        assert image is not None and image.source == "ddragon" and reasons == []
        assert image.data[:2] == b"\xff\xd8" and image.size == (308, 560)
        calls.clear()
        again, _ = await finder.find(name="Aatrox", aliases=[], kind="game_character", franchise="LoL", pages=[])
        assert again is not None
        assert calls == [image_url]

    asyncio.run(run())


def test_mediawiki_fallback_on_bad_candidates_and_no_og_image(tmp_path) -> None:
    wiki_page = "https://genshin-impact.fandom.com/wiki/Furina"
    news_page = "https://news.invalid/furina"
    wiki_thumb = "https://static.invalid/Furina.png"
    wiki_original = "https://static.invalid/Furina_full.png"
    pages = {
        "https://genshin-impact.fandom.com/api.php?": json.dumps({"query": {"pages": [
            {"title": "Furina", "thumbnail": {"source": wiki_thumb}},
            {"title": "Furina", "original": {"source": wiki_original}},
        ]}}),
        news_page: '<html><head><meta content="/cover.jpg" property="og:image"></head></html>',
    }

    async def run() -> None:
        finder, calls = make_finder(
            tmp_path, pages, {wiki_thumb: picture((100, 100)), wiki_original: picture(mode="RGBA")},
        )
        image, reasons = await finder.find(
            name="芙宁娜", aliases=[], kind="game_character", franchise="原神", pages=[news_page, wiki_page],
        )
        assert image is not None and image.source == "mediawiki" and image.page_url == wiki_page
        assert len(reasons) == 1 and "太小" in reasons[0]
        assert any("prop=pageimages" in call and "titles=Furina" in call for call in calls)
        assert not any(call.startswith("https://news.invalid") for call in calls)

    asyncio.run(run())


def test_search_candidates_filter_hosts_sizes_and_duplicates() -> None:
    sources = module("infrastructure.media.world_sources")
    SearchImage = module("infrastructure.providers.image_search").SearchImage

    def item(url, width=None, height=None):
        return SearchImage(url=url, page_url="", thumbnail_url="", width=width, height=height, text="", provider="brave")

    images = [
        item("https://i.pinimg.com/a.jpg"),
        item("https://img.invalid/small.jpg", 200, 300),
        item("https://img.invalid/strip.jpg", 3000, 600),
        item("https://img.invalid/T1_logo.png"),
        item("https://img.invalid/ok-1.jpg", 1200, 800),
        item("https://img.invalid/ok-1.jpg", 1200, 800),
        item("https://img.invalid/ok-2.png"),
        item("https://img.invalid/ok-3.png"),
    ]
    kept = sources.search_candidates(images, "game_character", 2)
    assert [image.url for image in kept] == ["https://img.invalid/ok-1.jpg", "https://img.invalid/ok-2.png"]
    team = sources.search_candidates(images, "esports_team", 8)
    assert "https://img.invalid/T1_logo.png" in [image.url for image in team]


def test_preview_shrinks_and_rewords_errors(tmp_path) -> None:
    async def run() -> None:
        downloads = module("infrastructure.media.downloads")
        finder, _ = make_finder(tmp_path, {}, {"https://img.invalid/big.png": picture((1600, 900))})
        data = await finder.preview("https://img.invalid/big.png")
        with Image.open(BytesIO(data)) as image:
            assert image.format == "JPEG" and max(image.size) == 384
        with pytest.raises(downloads.PublicFetchError) as caught:
            await finder.preview("https://img.invalid/missing.png?sig=secret")
        assert "生成" not in str(caught.value) and "secret" not in str(caught.value)

    asyncio.run(run())


def test_download_errors_are_reworded_without_generation_wording(tmp_path) -> None:
    async def run() -> None:
        sources = module("infrastructure.media.world_sources")
        finder, _ = make_finder(tmp_path, {}, {})
        with pytest.raises(module("infrastructure.media.downloads").PublicFetchError) as caught:
            await finder.fetch(sources.ImageCandidate("https://img.invalid/a.png?sig=secret", "", "mediawiki"))
        message = str(caught.value)
        assert "生成" not in message and "secret" not in message
        image, reasons = await finder.find(name="x", aliases=[], kind="other", franchise="", pages=[])
        assert image is None and reasons == ["没有找到候选参考图"]

    asyncio.run(run())


def test_reference_normalization_limits() -> None:
    images = module("infrastructure.media.images")
    data, size = images.normalize_reference_image(picture((3000, 2000)))
    assert size == (1536, 1024) and data[:2] == b"\xff\xd8"
    with pytest.raises(ValueError, match="长宽比"):
        images.normalize_reference_image(picture((2000, 400)))
    with pytest.raises(ValueError, match="太小"):
        images.normalize_reference_image(picture((200, 300)))
