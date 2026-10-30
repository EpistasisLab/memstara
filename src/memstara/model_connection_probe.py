"""Isolated Motoro connection check; stdout contains fixed status codes only."""

import asyncio


async def check():
    from pydantic import BaseModel
    from memstara.env import load_env

    load_env()
    from memstara.config import Settings
    from memstara.operational import agent_profile
    from motoro import configure
    from motoro.schemas.agent import ModelConfig
    from motoro.services.llm_service import LLMService

    configure(Settings())

    class Reply(BaseModel):
        status: str

    profile = agent_profile("hypothesis")
    config = ModelConfig(**({"max_tokens": 1024, **profile}))
    async with asyncio.timeout(35):
        await LLMService().complete(
            config, [{"role": "user", "content": "Connection check. Return status: ok."}], Reply, max_retries=1
        )


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception as error:
        names = {type(error).__name__}
        cause = getattr(error, "__cause__", None)
        if cause:
            names.add(type(cause).__name__)
        code = (
            "auth"
            if names & {"AuthenticationError", "PermissionDeniedError"}
            else "model"
            if "NotFoundError" in names
            else "quota"
            if "RateLimitError" in names
            else "network"
            if names & {"APIConnectionError", "TimeoutError"}
            else "failed"
        )
        print(code)
        raise SystemExit(1) from None
    print("ok")
