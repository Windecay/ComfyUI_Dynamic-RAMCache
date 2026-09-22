import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class CacheType:
    CLASSIC = 0
    RAM_PRESSURE = 3


class HierarchicalCache:
    def __init__(self, key_class=None, **kwargs):
        self.key_class = key_class
        self.cache = {"retained": object()}


class RAMPressureCache(HierarchicalCache):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.releases = []

    def ram_release(self, headroom, **kwargs):
        self.releases.append((headroom, kwargs))
        return 0


class ExecutorBase:
    def __init__(self, mode):
        self.cache_type = mode
        self.cache_args = {"ram": 2, "ram_inactive": 1}
        cache = RAMPressureCache() if mode == CacheType.RAM_PRESSURE else HierarchicalCache()
        self.caches = types.SimpleNamespace(outputs=cache, all=[cache])


class SplitExecutor(ExecutorBase):
    async def execute_async(self, action):
        await self._execute_async(action)

    async def _execute_async(self, action):
        ram_inactive_headroom = self.cache_args["ram_inactive"]
        ram_release_callback = self.caches.outputs.ram_release if self.cache_type == CacheType.RAM_PRESSURE else None
        action()
        if self.cache_type == CacheType.RAM_PRESSURE:
            ram_release_callback(ram_inactive_headroom)


class InlineExecutor(ExecutorBase):
    async def execute_async(self, action):
        ram_inactive_headroom = self.cache_args["ram_inactive"]
        ram_release_callback = self.caches.outputs.ram_release if self.cache_type == CacheType.RAM_PRESSURE else None
        action()
        if self.cache_type == CacheType.RAM_PRESSURE:
            ram_release_callback(ram_inactive_headroom)


class LegacyExecutor(ExecutorBase):
    async def execute_async(self, action):
        action()


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.execution = types.ModuleType("execution")
        self.execution.CacheType = CacheType
        self.execution.PromptExecutor = SplitExecutor
        cache_module = types.ModuleType("comfy_execution.caching")
        cache_module.RAMPressureCache = RAMPressureCache
        cache_module.HierarchicalCache = HierarchicalCache
        cache_module.CacheKeySetInputSignature = object
        package = types.ModuleType("comfy_execution")
        package.caching = cache_module
        filename = Path(__file__).resolve().parents[1] / "nodes.py"
        spec = importlib.util.spec_from_file_location("dynamic_ramcache_test_nodes", filename)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            "execution": self.execution,
            "comfy_execution": package,
            "comfy_execution.caching": cache_module,
        }):
            spec.loader.exec_module(self.module)

    def controller(self, executor, extreme=False):
        self.execution.PromptExecutor = type(executor)
        cls = self.module.RAMCacheExtremeCleanup if extreme else self.module.DynamicRAMCacheControl
        node = cls()
        node._find_executor = lambda: executor
        return node

    def test_prompt_local_modes_across_two_prompts(self):
        for executor_class in (SplitExecutor, InlineExecutor):
            for start_mode in (CacheType.CLASSIC, CacheType.RAM_PRESSURE):
                with self.subTest(executor=executor_class.__name__, mode=start_mode):
                    executor = executor_class(start_mode)
                    node = self.controller(executor)
                    original_cache = executor.caches.outputs
                    retained = original_cache.cache["retained"]
                    passthrough = object()

                    def action():
                        for mode in ("RAM_PRESSURE (Auto Purge)", "CLASSIC (No Eviction)", "RAM_PRESSURE (Auto Purge)"):
                            result = node.manage_cache(mode, 2, 1, passthrough)
                            self.assertIs(result[0], passthrough)
                            self.assertEqual(executor.cache_type, start_mode)
                            self.assertIs(executor.caches.outputs.cache["retained"], retained)
                            self.assertIs(executor.caches.all[0], executor.caches.outputs)

                    for _ in range(2):
                        asyncio.run(executor.execute_async(action))
                    self.assertTrue(executor.caches.outputs.releases)
                    if start_mode == CacheType.RAM_PRESSURE:
                        self.assertIs(executor.caches.outputs, original_cache)

    def test_legacy_executor_still_switches_both_modes(self):
        executor = LegacyExecutor(CacheType.CLASSIC)
        node = self.controller(executor)
        node.manage_cache("RAM_PRESSURE (Auto Purge)", 2, any_input=1)
        self.assertEqual(executor.cache_type, CacheType.RAM_PRESSURE)
        node.manage_cache("CLASSIC (No Eviction)", 2, any_input=1)
        self.assertEqual(executor.cache_type, CacheType.CLASSIC)
        self.assertIsInstance(executor.caches.outputs, HierarchicalCache)
        self.assertNotIsInstance(executor.caches.outputs, RAMPressureCache)

    def test_classic_prompt_can_request_ram_without_none_callback(self):
        executor = SplitExecutor(CacheType.CLASSIC)
        node = self.controller(executor)
        asyncio.run(executor.execute_async(
            lambda: node.manage_cache("RAM_PRESSURE (Auto Purge)", 2, any_input=1)
        ))
        self.assertEqual(executor.cache_type, CacheType.CLASSIC)

    def test_split_method_detects_inactive_arg_without_existing_key(self):
        executor = SplitExecutor(CacheType.CLASSIC)
        executor.cache_args.pop("ram_inactive")
        node = self.controller(executor)
        self.assertTrue(node._supports_inactive_cache_arg(executor))
        node.manage_cache("RAM_PRESSURE (Auto Purge)", 2, 3, any_input=1)
        self.assertEqual(executor.cache_args["ram_inactive"], 3)

    def test_unknown_source_keeps_mode_unchanged(self):
        executor = SplitExecutor(CacheType.CLASSIC)
        node = self.controller(executor)
        for error in (OSError, TypeError, ValueError):
            with self.subTest(error=error), patch.object(self.module.inspect, "getsource", side_effect=error):
                self.assertTrue(node._uses_prompt_local_ram_release_callback())
                node.manage_cache("RAM_PRESSURE (Auto Purge)", 2, any_input=1)
                self.assertEqual(executor.cache_type, CacheType.CLASSIC)

    def test_absent_async_methods_are_conservative(self):
        self.execution.PromptExecutor = ExecutorBase
        node = self.module.DynamicRAMCacheControl()
        self.assertTrue(node._uses_prompt_local_ram_release_callback())

    def test_unreadable_inner_method_remains_conservative(self):
        executor = SplitExecutor(CacheType.CLASSIC)
        node = self.controller(executor)
        with patch.object(self.module.inspect, "getsource", side_effect=[
            "async def execute_async(self): await self._execute_async()",
            OSError("source unavailable"),
        ]):
            self.assertTrue(node._uses_prompt_local_ram_release_callback())

    def test_extreme_cleanup_restores_thresholds_without_invalid_callback(self):
        for mode in (CacheType.CLASSIC, CacheType.RAM_PRESSURE):
            with self.subTest(mode=mode):
                executor = SplitExecutor(mode)
                original_args = dict(executor.cache_args)
                node = self.controller(executor, extreme=True)
                asyncio.run(executor.execute_async(lambda: node.extreme_cleanup(256, any_input=1)))
                self.assertEqual(executor.cache_type, mode)
                self.assertEqual(executor.cache_args["ram"], original_args["ram"])
                self.assertEqual(executor.cache_args["ram_inactive"], original_args["ram_inactive"])


if __name__ == "__main__":
    unittest.main()
