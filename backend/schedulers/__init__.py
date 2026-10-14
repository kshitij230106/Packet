"""Scheduler package registry and factory.
"""

from typing import Dict, Type
from backend.models import SimulationConfig
from backend.schedulers.base import BaseScheduler
from backend.schedulers.fcfs import FCFSScheduler
from backend.schedulers.strict_priority import StrictPriorityScheduler
from backend.schedulers.wfq import WFQScheduler

SCHEDULER_REGISTRY: Dict[str, Type[BaseScheduler]] = {
    "fcfs": FCFSScheduler,
    "strict_priority": StrictPriorityScheduler,
    "wfq": WFQScheduler,
}


def create_scheduler(scheduler_type: str, config: SimulationConfig) -> BaseScheduler:
    """Instantiate a scheduler based on type identifier."""
    key = scheduler_type.lower()
    if key not in SCHEDULER_REGISTRY:
        raise ValueError(
            f"Unknown scheduler type '{scheduler_type}'. Available: {list(SCHEDULER_REGISTRY.keys())}"
        )
    return SCHEDULER_REGISTRY[key](config)
