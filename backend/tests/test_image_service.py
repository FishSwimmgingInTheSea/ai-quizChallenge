"""配图服务编排与降级测试（question-images 任务 4.2）：Fake 生成器/存储/配额。"""

from __future__ import annotations

from app.core.config import Settings
from app.models.quiz import Option, Question
from app.services import image_service as mod
from app.services.image_service import ImageService


def _settings(**over) -> Settings:
    base = dict(
        image_gen_enabled=True,
        dashscope_api_key="sk-test",
        cos_secret_id="id",
        cos_secret_key="key",
        cos_bucket="b-123",
        cos_region="ap-guangzhou",
        image_daily_limit=20,
    )
    base.update(over)
    return Settings(**base)


def _question() -> Question:
    return Question(
        id="q1",
        type="single",
        stem="苹果对应的英文单词是？",
        options=[Option(key="A", text="apple"), Option(key="B", text="banana")],
        answer=["A"],
        explanation="apple。",
        knowledge_point="英语单词",
        difficulty="easy",
    )


class FakeGenerator:
    def __init__(self, data: bytes | None = b"img"):
        self.data = data
        self.calls = 0

    async def generate(self, prompt: str) -> bytes | None:
        self.calls += 1
        return self.data


class FakeStore:
    def __init__(self, *, available=True, url="https://cos/x.png"):
        self._available = available
        self._url = url
        self.uploads = 0

    @property
    def is_available(self) -> bool:
        return self._available

    def upload(self, data: bytes, key: str) -> str | None:
        self.uploads += 1
        return self._url if self._available else None


class FakeUsage:
    def __init__(self, *, quota=True, consume=True):
        self._quota = quota
        self._consume = consume
        self.consume_calls = 0

    def has_quota(self, user_id, *, day=None) -> bool:
        return self._quota

    def try_consume(self, user_id, *, day=None) -> bool:
        self.consume_calls += 1
        return self._consume


def _service(settings=None, generator=None, store=None, usage=None) -> ImageService:
    return ImageService(
        settings or _settings(),
        generator=generator or FakeGenerator(),
        store=store if store is not None else FakeStore(),
        usage=usage or FakeUsage(),
    )


# ---------- plan：任务级门禁 ----------


def test_plan_总开关关闭():
    plan = _service(_settings(image_gen_enabled=False)).plan(1)
    assert plan.enabled is False
    assert plan.notice == ""


def test_plan_匿名给登录提示():
    plan = _service().plan(None)
    assert plan.enabled is False
    assert plan.notice == mod.LOGIN_NOTICE


def test_plan_缺百炼密钥():
    plan = _service(_settings(dashscope_api_key="")).plan(1)
    assert plan.enabled is False


def test_plan_缺COS凭据():
    plan = _service(store=FakeStore(available=False)).plan(1)
    assert plan.enabled is False


def test_plan_正常启用():
    plan = _service().plan(1)
    assert plan.enabled is True
    assert plan.notice == ""


# ---------- generate_for_question：单题路径 ----------


async def test_generate_成功返回永久URL并消费配额():
    usage = FakeUsage()
    store = FakeStore(url="https://cos/ok.png")
    svc = _service(store=store, usage=usage)
    url, notice = await svc.generate_for_question(_question(), user_id=1)
    assert url == "https://cos/ok.png"
    assert notice is None
    assert usage.consume_calls == 1


async def test_generate_额度用尽返回配额提示且不生图():
    gen = FakeGenerator()
    svc = _service(generator=gen, usage=FakeUsage(quota=False))
    url, notice = await svc.generate_for_question(_question(), user_id=1)
    assert url is None
    assert notice == mod.QUOTA_NOTICE
    assert gen.calls == 0


async def test_generate_生图失败不带图不消费配额():
    usage = FakeUsage()
    svc = _service(generator=FakeGenerator(data=None), usage=usage)
    url, notice = await svc.generate_for_question(_question(), user_id=1)
    assert url is None
    assert notice is None
    assert usage.consume_calls == 0


async def test_generate_上传失败不带图不消费配额():
    usage = FakeUsage()
    svc = _service(store=FakeStore(available=False), usage=usage)
    url, notice = await svc.generate_for_question(_question(), user_id=1)
    assert url is None
    assert notice is None
    assert usage.consume_calls == 0


async def test_generate_并发额度耗尽丢弃图片():
    svc = _service(usage=FakeUsage(quota=True, consume=False))
    url, notice = await svc.generate_for_question(_question(), user_id=1)
    assert url is None
    assert notice == mod.QUOTA_NOTICE
