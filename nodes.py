import gc
import logging
import time

caching = None
execution = None

# Import execution module
try:
    import execution
except ImportError:
    logging.error("[DynamicRAMCache] Failed to import execution module")
    logging.error("[DynamicRAMCache] This may be due to ComfyUI version update to 2025.10.31. Please check if module structure has changed.")
    
# Import caching module
try:
    from comfy_execution import caching
    # Check if RAMPressureCache class exists in the imported caching module
    if caching is not None and not hasattr(caching, 'RAMPressureCache'):
        logging.error("[DynamicRAMCache] RAMPressureCache class not found in caching module")
        logging.error("[DynamicRAMCache] This class may only exist in ComfyUI versions after 2025.10.31")
except ImportError:
    logging.error("[DynamicRAMCache] Failed to import caching module")
    logging.error("[DynamicRAMCache] This may be due to ComfyUI version update to 2025.10.31. Please check if module structure has changed.")

# Ensure both modules are successfully imported
if execution is None or caching is None:
    logging.error("[DynamicRAMCache] Critical module import failed, plugin may not work correctly")
    logging.error("[DynamicRAMCache] Plugin compatibility with ComfyUI 2025.10.31 needs to be verified. Module structure may have changed.")

class AlwaysEqualProxy(str):
    def __eq__(self, _):
        return True

    def __ne__(self, _):
        return False

any_type = AlwaysEqualProxy("*")

class DynamicRAMCacheControl:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "mode": (["CLASSIC (No Eviction)", "RAM_PRESSURE (Auto Purge)"], {"default": "RAM_PRESSURE (Auto Purge)"}),
                "cleanup_threshold": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 256.0, "step": 0.1, "tooltip": "Minimum free RAM to maintain (GB)"}),
            },
            "optional": {
                "any_input": (any_type, {}),
            }
        }

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("output_passthrough",)
    FUNCTION = "manage_cache"
    CATEGORY = "utils/dynamic_ramcache"

    def manage_cache(self, mode, cleanup_threshold, any_input=None):
        if caching is not None and execution is not None:
            self._execute_cache_logic(mode, cleanup_threshold)
        else:
            logging.warning("[DynamicRAMCache] Plugin disabled: Missing internal modules.")

        if any_input is not None:
            return (any_input,)
        else:
            try:
                from comfy_execution.graph import ExecutionBlocker
                return (ExecutionBlocker(None),)
            except ImportError:
                return (None,)

    def _execute_cache_logic(self, mode, cleanup_threshold):

        target_mode_ram = "RAM_PRESSURE" in mode

        executor = self._find_executor()
        
        if executor is None:
            logging.warning("[DynamicRAMCache] PromptExecutor not found.")
            return

        if not hasattr(executor, 'cache_args'):
            executor.cache_args = {}
        
        old_ram_arg = executor.cache_args.get('ram', 0)
        executor.cache_args['ram'] = cleanup_threshold

        cache_set = self._get_cache_set(executor)
        if cache_set is None:
            return

        current_cache = cache_set.outputs

        RAMPressureCacheClass = getattr(caching, 'RAMPressureCache', None)
        HierarchicalCacheClass = getattr(caching, 'HierarchicalCache', None)

        if not RAMPressureCacheClass:
            logging.error("[DynamicRAMCache] RAMPressureCache class not available in caching module")
            logging.error("[DynamicRAMCache] This class is required for RAM_PRESSURE mode and may only exist in ComfyUI versions after 2025.10.31")
            logging.error("[DynamicRAMCache] Please check your ComfyUI version or consider switching to CLASSIC mode")
            return
        
        if not HierarchicalCacheClass:
            logging.error("[DynamicRAMCache] HierarchicalCache class not available in caching module")
            return

        is_currently_ram = isinstance(current_cache, RAMPressureCacheClass)

        if target_mode_ram and not is_currently_ram:
            self._switch_to_ram_pressure(cache_set, current_cache, caching)
            logging.info(f"[DynamicRAMCache] Switched mode: CLASSIC -> RAM_PRESSURE (Headroom: {cleanup_threshold}GB)")
        
        elif not target_mode_ram and is_currently_ram:
            self._switch_to_classic(cache_set, current_cache, caching)
            logging.info(f"[DynamicRAMCache] Switched mode: RAM_PRESSURE -> CLASSIC")
        
        elif target_mode_ram and is_currently_ram:
            if old_ram_arg != cleanup_threshold:
                logging.info(f"[DynamicRAMCache] Updated RAM Headroom: {old_ram_arg}GB -> {cleanup_threshold}GB")

        if target_mode_ram and hasattr(cache_set.outputs, 'poll'):
            try:
                cache_set.outputs.poll(cleanup_threshold)
            except Exception:
                pass

    def _find_executor(self):
        for obj in gc.get_objects():
            if obj.__class__.__name__ == 'PromptExecutor':
                return obj
        return None

    def _get_cache_set(self, executor):
        if not hasattr(executor, 'caches'):
            logging.warning("[DynamicRAMCache] PromptExecutor has no 'caches' attribute.")
            return None
        
        cache_set = executor.caches

        if not hasattr(cache_set, 'outputs'):
            logging.warning("[DynamicRAMCache] CacheSet has no 'outputs' attribute.")
            return None
        return cache_set

    def _update_cache_set(self, cache_set, new_cache):

        cache_set.outputs = new_cache
        
        if hasattr(cache_set, 'all') and isinstance(cache_set.all, list):
            for i, item in enumerate(cache_set.all):
                if i == 0: 
                    cache_set.all[i] = new_cache

    def _switch_to_ram_pressure(self, cache_set, old_cache, caching_mod):
        key_class = getattr(old_cache, 'key_class', None)
        if not key_class:
            key_class = getattr(caching_mod, 'CacheKeySetInputSignature', None)

        new_cache = caching_mod.RAMPressureCache(key_class)
        self._migrate_cache_data(old_cache, new_cache)

        new_cache.timestamps = {}
        new_cache.used_generation = {}
        new_cache.children = {}
        new_cache.generation = 1
        new_cache.min_generation = 0

        now = time.time()
        for key in new_cache.cache:
            new_cache.timestamps[key] = now
            new_cache.used_generation[key] = 0 

        self._update_cache_set(cache_set, new_cache)

    def _switch_to_classic(self, cache_set, old_cache, caching_mod):
        key_class = getattr(old_cache, 'key_class', None)
        if not key_class:
            key_class = getattr(caching_mod, 'CacheKeySetInputSignature', None)

        new_cache = caching_mod.HierarchicalCache(key_class)
        self._migrate_cache_data(old_cache, new_cache)

        self._update_cache_set(cache_set, new_cache)

    def _migrate_cache_data(self, old_cache, new_cache):
        """迁移缓存核心数据"""
        # Fix for 'NullCache' object has no attribute 'cache'
        if hasattr(old_cache, 'cache'):
            new_cache.cache = old_cache.cache
        
        if hasattr(old_cache, 'subcaches'):
            new_cache.subcaches = old_cache.subcaches
            
        new_cache.dynprompt = getattr(old_cache, 'dynprompt', None)
        new_cache.cache_key_set = getattr(old_cache, 'cache_key_set', None)
        new_cache.initialized = getattr(old_cache, 'initialized', False)

class RAMCacheExtremeCleanup(DynamicRAMCacheControl):
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "purge_threshold": ("FLOAT", {"default": 256.0, "min": 0.1, "max": 256.0, "step": 0.1, "tooltip": "Minimum free RAM to maintain (GB)"}),
            },
            "optional": {
                "any_input": (any_type, {}),
            }
        }

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("output_passthrough",)
    FUNCTION = "extreme_cleanup"
    CATEGORY = "utils/dynamic_ramcache"

    def extreme_cleanup(self, purge_threshold, any_input=None):
        if caching is not None and execution is not None:
            executor = self._find_executor()
            if executor is None:
                logging.warning("[DynamicRAMCache] PromptExecutor not found.")
            else:
                if not hasattr(executor, 'cache_args'):
                    executor.cache_args = {}
                old_ram_arg = executor.cache_args.get('ram', 2.0)
                cache_set = self._get_cache_set(executor)
                if cache_set is not None:
                    RAMPressureCacheClass = getattr(caching, 'RAMPressureCache', None)
                    if RAMPressureCacheClass:
                        is_currently_ram = isinstance(cache_set.outputs, RAMPressureCacheClass)
                        old_mode = "RAM_PRESSURE (Auto Purge)" if is_currently_ram else "CLASSIC (No Eviction)"
                    else:
                        old_mode = "CLASSIC (No Eviction)"
                    self._execute_cache_logic("RAM_PRESSURE (Auto Purge)", purge_threshold)
                    self._execute_cache_logic(old_mode, old_ram_arg)
        else:
            logging.warning("[DynamicRAMCache] Plugin disabled: Missing internal modules.")

        if any_input is not None:
            return (any_input,)
        else:
            try:
                from comfy_execution.graph import ExecutionBlocker
                return (ExecutionBlocker(None),)
            except ImportError:
                return (None,)
