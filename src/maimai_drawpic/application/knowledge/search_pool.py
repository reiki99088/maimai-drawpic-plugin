"""网搜取图的服务轮换：按配置顺序或轮流起点挑服务，失败的服务按错误类型冷却一段时间。

冷却与轮流位置跨配置刷新保留；某个服务的密钥、地址或模型改了，就清掉它的冷却，改完配置立即可用。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Sequence
import hashlib

MAX_PROVIDERS_PER_ENTRY = 2
COOLDOWN_SECONDS = {
    "auth": 6 * 3600,     # 密钥无效、没开通：等用户改配置
    "quota": 30 * 60,     # 限流或额度用完
    "request": 30 * 60,   # 请求被拒（如模型不支持图片搜索），短时间重试也一样
    "server": 5 * 60,
    "network": 5 * 60,
    "parse": 5 * 60,
}


def client_fingerprint(client: Any) -> str:
    """只用于判断配置有没有变；不保存密钥本身。"""
    parts = (client.name, client.api_key, getattr(client, "base_url", ""), getattr(client, "model", ""))
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


class ImageSearchPool:
    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._clients: Dict[str, Any] = {}
        self._order: List[str] = []
        self._strategy = "ordered"
        self._cooldown_until: Dict[str, float] = {}
        self._fingerprints: Dict[str, str] = {}
        self._cursor = 0

    def configure(self, clients: Mapping[str, Any], order: Sequence[str], strategy: str) -> None:
        for name, client in clients.items():
            fingerprint = client_fingerprint(client)
            if self._fingerprints.get(name) != fingerprint:
                self._cooldown_until.pop(name, None)
            self._fingerprints[name] = fingerprint
        for name in set(self._fingerprints) - set(clients):
            self._fingerprints.pop(name, None)
            self._cooldown_until.pop(name, None)
        self._clients = dict(clients)
        self._order = [name for name in order if name in self._clients]
        self._strategy = strategy

    @property
    def configured(self) -> bool:
        return bool(self._order)

    def sequence(self) -> List[Any]:
        """本次要试的服务（最多 2 个）；round_robin 每次调用把起点后移一位。"""
        now = self._clock()
        names = [name for name in self._order if self._cooldown_until.get(name, 0.0) <= now]
        if self._strategy == "round_robin" and names:
            start = self._cursor % len(names)
            self._cursor += 1
            names = names[start:] + names[:start]
        return [self._clients[name] for name in names[:MAX_PROVIDERS_PER_ENTRY]]

    def failed(self, name: str, kind: str) -> None:
        self._cooldown_until[name] = self._clock() + COOLDOWN_SECONDS.get(kind, COOLDOWN_SECONDS["network"])

    def succeeded(self, name: str) -> None:
        self._cooldown_until.pop(name, None)

    def cooling(self) -> List[str]:
        now = self._clock()
        return [name for name in self._order if self._cooldown_until.get(name, 0.0) > now]
