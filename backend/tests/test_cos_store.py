"""COS 存储封装测试（question-images 任务 3.3）：Mock qcloud_cos，不触真实 COS。"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.cos_store import CosImageStore, build_object_key


def _settings(**over) -> Settings:
    base = dict(
        cos_secret_id="id",
        cos_secret_key="key",
        cos_bucket="quiz-img-1250000000",
        cos_region="ap-guangzhou",
    )
    base.update(over)
    return Settings(**base)


class _FakeCosClient:
    instances: list["_FakeCosClient"] = []

    def __init__(self, config):
        self.config = config
        self.put_calls: list[dict] = []
        self.raise_on_put = False
        _FakeCosClient.instances.append(self)

    def put_object(self, **kwargs):
        if self.raise_on_put:
            raise RuntimeError("COS 服务异常")
        self.put_calls.append(kwargs)

    def get_object_url(self, *, Bucket, Key):
        return f"https://{Bucket}.cos.ap-guangzhou.myqcloud.com/{Key}"


@pytest.fixture(autouse=True)
def _patch_cos(monkeypatch):
    _FakeCosClient.instances = []
    monkeypatch.setattr("qcloud_cos.CosConfig", lambda **kw: kw)
    monkeypatch.setattr("qcloud_cos.CosS3Client", _FakeCosClient)


def test_is_available_四项齐全为真():
    assert CosImageStore(_settings()).is_available is True


def test_is_available_缺凭据为假():
    assert CosImageStore(_settings(cos_bucket="")).is_available is False


def test_upload_凭据缺失返回None():
    store = CosImageStore(_settings(cos_secret_id=""))
    assert store.upload(b"data", "quiz-images/1/x.png") is None
    assert _FakeCosClient.instances == []  # 未构建客户端


def test_upload_空字节返回None():
    store = CosImageStore(_settings())
    assert store.upload(b"", "quiz-images/1/x.png") is None


def test_upload_成功返回永久URL():
    store = CosImageStore(_settings())
    url = store.upload(b"\x89PNG", "quiz-images/1/202609/abc.png")
    assert url == (
        "https://quiz-img-1250000000.cos.ap-guangzhou.myqcloud.com/"
        "quiz-images/1/202609/abc.png"
    )
    client = _FakeCosClient.instances[0]
    assert client.put_calls[0]["Bucket"] == "quiz-img-1250000000"
    assert client.put_calls[0]["Key"] == "quiz-images/1/202609/abc.png"
    assert client.put_calls[0]["Body"] == b"\x89PNG"


def test_upload_异常降级返回None(monkeypatch):
    store = CosImageStore(_settings())

    class _Boom(_FakeCosClient):
        def put_object(self, **kwargs):
            raise RuntimeError("网络中断")

    monkeypatch.setattr("qcloud_cos.CosS3Client", _Boom)
    assert store.upload(b"data", "quiz-images/1/x.png") is None


def test_build_object_key_结构():
    key = build_object_key(7, "png")
    assert key.startswith("quiz-images/7/")
    assert key.endswith(".png")
    # 含年月分段与唯一文件名
    parts = key.split("/")
    assert len(parts) == 4
    assert len(parts[2]) == 6 and parts[2].isdigit()
    assert parts[3] != "x.png"


def test_build_object_key_唯一():
    assert build_object_key(1) != build_object_key(1)
