"""Shared FastAPI dependencies — singletons for config, scan manager, etc."""

import os
from functools import lru_cache

from ..core.config import ConfigLoader
from ..orchestration.events import EventBroadcaster
from ..orchestration.scan_manager import ScanManager
from ..storage.store import PolicyStore


@lru_cache()
def get_config() -> ConfigLoader:
    config_dir = os.environ.get("OCP_CONFIG_DIR", "config")
    config = ConfigLoader(config_dir=config_dir)
    config.load()
    return config


@lru_cache()
def get_broadcaster() -> EventBroadcaster:
    return EventBroadcaster()


@lru_cache()
def get_policy_store() -> PolicyStore:
    data_dir = os.environ.get("OCP_DATA_DIR", "data")
    return PolicyStore(data_dir=data_dir)


@lru_cache()
def get_scan_manager() -> ScanManager:
    config = get_config()
    broadcaster = get_broadcaster()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    data_dir = os.environ.get("OCP_DATA_DIR", "data")
    return ScanManager(
        config=config,
        broadcaster=broadcaster,
        api_key=api_key,
        data_dir=data_dir,
    )
