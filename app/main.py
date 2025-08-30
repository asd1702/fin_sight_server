from fastapi import FastAPI, BackgroundTasks
from prometheus_fastapi_instrumentator import Instrumentator
from app.api import articles, health
from app.core.monitoring import log_system_metrics
import asyncio

app = FastAPI(
    title="FinSight API Server",
    description="금융 뉴스 수집 및 분석 시스템",
    version="1.0.0"
)

instrumentator = Instrumentator()
instrumentator.instrument(app)
instrumentator.expose(app, endpoint="/metrics")

# 백그라운드에서 시스템 메트릭 주기적 수집
async def periodic_system_monitoring():
    while True:
        # DEBUG 레벨로 변경하여 기본적으로는 출력하지 않음
        import logging
        if logging.getLogger().level <= logging.DEBUG:
            log_system_metrics()
        await asyncio.sleep(300)  # 5분마다 실행으로 변경

@app.on_event("startup")
async def startup_event():
    # 백그라운드 태스크 시작
    asyncio.create_task(periodic_system_monitoring())

app.include_router(articles.router)
app.include_router(health.router)


@app.get("/")
def read_root():
    return {"message": "FinSight API Server is running."}