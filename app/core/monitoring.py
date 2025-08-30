import time
import psutil
import tracemalloc
from functools import wraps
from typing import Dict, Any

try:
    from logs.logging_config import get_logger
except ImportError:
    from ...logs.logging_config import get_logger

try:
    from prometheus_client import Counter, Histogram, Gauge
except ImportError:
    # prometheus_client가 없으면 더미 클래스 사용
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def inc(self): pass
    
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def observe(self, value): pass
    
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def set(self, value): pass

logger = get_logger(__name__)

# Prometheus 커스텀 메트릭 정의
FUNCTION_DURATION = Histogram(
    'function_duration_seconds',
    'Function execution time in seconds',
    ['function_name', 'module']
)

MEMORY_USAGE = Gauge(
    'memory_usage_percent',
    'Memory usage percentage',
    ['function_name']
)

FUNCTION_CALLS = Counter(
    'function_calls_total',
    'Total function calls',
    ['function_name', 'status']
)

def monitor_performance(include_memory=True, include_tracemalloc=False):
    """
    함수 성능을 모니터링하는 데코레이터
    
    Args:
        include_memory: 메모리 사용량 모니터링 여부
        include_tracemalloc: 상세 메모리 추적 여부 (개발용)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            module_name = func.__module__.split('.')[-1]
            
            # 시작 시간 및 메모리 측정
            start_time = time.time()
            memory_before = psutil.virtual_memory().percent if include_memory else 0
            
            # 상세 메모리 추적 시작 (개발 환경용)
            if include_tracemalloc:
                tracemalloc.start()
            
            try:
                # 함수 실행
                result = func(*args, **kwargs)
                
                # 성공 메트릭
                FUNCTION_CALLS.labels(function_name=func_name, status='success').inc()
                
                return result
                
            except Exception as e:
                # 실패 메트릭
                FUNCTION_CALLS.labels(function_name=func_name, status='error').inc()
                logger.error(f"{func_name} 실행 중 오류: {e}", exc_info=True)
                raise
                
            finally:
                # 성능 메트릭 수집
                duration = time.time() - start_time
                memory_after = psutil.virtual_memory().percent if include_memory else 0
                memory_diff = memory_after - memory_before
                
                # Prometheus 메트릭 업데이트
                FUNCTION_DURATION.labels(function_name=func_name, module=module_name).observe(duration)
                if include_memory:
                    MEMORY_USAGE.labels(function_name=func_name).set(memory_after)
                
                # 로그 출력
                log_level = 'warning' if duration > 5.0 else 'info'
                getattr(logger, log_level)(
                    f"성능 모니터링 - {func_name}: "
                    f"실행시간={duration:.2f}초, "
                    f"메모리변화={memory_diff:+.1f}%, "
                    f"현재메모리={memory_after:.1f}%"
                )
                
                # 상세 메모리 추적 결과 (개발용)
                if include_tracemalloc:
                    current, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    logger.debug(f"{func_name} 메모리 추적: 현재={current/1024/1024:.1f}MB, 피크={peak/1024/1024:.1f}MB")
        
        return wrapper
    return decorator

def get_system_metrics() -> Dict[str, Any]:
    """
    시스템 전체 메트릭 수집
    """
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    
    import os
    home_path = os.path.expanduser("~")
    try:
        disk = psutil.disk_usage(home_path)
    except:
        disk = psutil.disk_usage('/')
    
    return {
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'memory_available_gb': memory.available / (1024**3),
        'disk_percent': (disk.used / disk.total) * 100,
        'disk_free_gb': disk.free / (1024**3),
        'disk_total_gb': disk.total / (1024**3)  # 전체 용량도 추가
    }

def log_system_metrics():
    """
    주기적으로 시스템 메트릭을 로그로 출력 (DEBUG 레벨로 변경)
    """
    metrics = get_system_metrics()
    logger.debug(
        f"시스템 상태 - "
        f"CPU: {metrics['cpu_percent']:.1f}%, "
        f"메모리: {metrics['memory_percent']:.1f}% "
        f"(여유: {metrics['memory_available_gb']:.1f}GB), "
        f"디스크: {metrics['disk_percent']:.1f}% "
        f"(전체: {metrics['disk_total_gb']:.1f}GB, 여유: {metrics['disk_free_gb']:.1f}GB)"
    )
    
    # 경고 임계값 체크 (이것만 INFO 레벨로 유지)
    if metrics['cpu_percent'] > 80:
        logger.warning(f"CPU 사용량 높음: {metrics['cpu_percent']:.1f}%")
    if metrics['memory_percent'] > 85:
        logger.warning(f"메모리 사용량 높음: {metrics['memory_percent']:.1f}%")
    if metrics['disk_percent'] > 90:
        logger.warning(f"디스크 사용량 높음: {metrics['disk_percent']:.1f}%")
