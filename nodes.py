import gc
import inspect
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
                "cleanup_threshold": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 256.0, "step": 0.1, "tooltip": "Active cache free RAM threshold (GB)"}),
            },
            "optional": {
                "inactive_threshold": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 256.0, "step": 0.1, "tooltip": "Inactive cache / pinned memory threshold (GB). 0 keeps ComfyUI's current value."}),
                "any_input": (any_type, {}),
            }
        }

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("output_passthrough",)
    FUNCTION = "manage_cache"
    CATEGORY = "utils/dynamic_ramcache"

    def manage_cache(self, mode, cleanup_threshold, inactive_threshold=0.0, any_input=None):
        if caching is not None and execution is not None:
            self._execute_cache_logic(mode, cleanup_threshold, inactive_threshold)
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

    def _execute_cache_logic(self, mode, cleanup_threshold, inactive_threshold=0.0):

        target_mode_ram = "RAM_PRESSURE" in mode

        executor = self._find_executor()
        
        if executor is None:
            logging.warning("[DynamicRAMCache] PromptExecutor not found.")
            return

        old_ram_arg, old_ram_inactive_arg, active_headroom, inactive_headroom, supports_inactive = self._update_cache_args(
            executor,
            cleanup_threshold,
            inactive_threshold,
        )

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
            if self._can_set_executor_ram_type(executor):
                self._set_executor_cache_type(executor, target_mode_ram)
                logging.info(self._format_headroom_log("[DynamicRAMCache] Switched mode: CLASSIC -> RAM_PRESSURE", active_headroom, inactive_headroom, supports_inactive))
            else:
                logging.warning(self._format_headroom_log("[DynamicRAMCache] RAM_PRESSURE cache active, executor mode kept as CLASSIC to avoid a prompt-local None callback", active_headroom, inactive_headroom, supports_inactive))

        elif not target_mode_ram and is_currently_ram:
            if self._should_keep_ram_mode(executor):
                logging.warning(self._format_headroom_log("[DynamicRAMCache] CLASSIC requested, RAM_PRESSURE kept active to avoid a prompt-local callback mismatch", active_headroom, inactive_headroom, supports_inactive))
            else:
                self._switch_to_classic(cache_set, current_cache, caching)
                self._set_executor_cache_type(executor, target_mode_ram)
                logging.info(f"[DynamicRAMCache] Switched mode: RAM_PRESSURE -> CLASSIC")

        elif target_mode_ram and is_currently_ram:
            if self._can_set_executor_ram_type(executor):
                self._set_executor_cache_type(executor, target_mode_ram)
            else:
                logging.warning(self._format_headroom_log("[DynamicRAMCache] RAM_PRESSURE cache active, executor mode kept as CLASSIC to avoid a prompt-local None callback", active_headroom, inactive_headroom, supports_inactive))
            if old_ram_arg != active_headroom or old_ram_inactive_arg != inactive_headroom:
                logging.info(self._format_headroom_update_log(old_ram_arg, old_ram_inactive_arg, active_headroom, inactive_headroom, supports_inactive))

        if target_mode_ram:
            self._release_ram_cache(cache_set.outputs, active_headroom, inactive_headroom, supports_inactive)

    def _read_threshold(self, value, default_value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = default_value
        return value

    def _update_cache_args(self, executor, cleanup_threshold, inactive_threshold):
        if not hasattr(executor, 'cache_args') or executor.cache_args is None:
            executor.cache_args = {}

        cache_args = executor.cache_args
        supports_inactive = self._supports_inactive_cache_arg(executor)
        active_headroom = self._read_threshold(cleanup_threshold, 2.0)
        old_ram_arg = self._read_threshold(cache_args.get('ram'), active_headroom)

        if supports_inactive:
            old_ram_inactive_arg = self._read_threshold(cache_args.get('ram_inactive'), old_ram_arg)
            inactive_value = self._read_threshold(inactive_threshold, 0.0)
            if inactive_value > 0:
                inactive_headroom = inactive_value
            elif old_ram_inactive_arg > 0:
                inactive_headroom = old_ram_inactive_arg
            else:
                inactive_headroom = active_headroom
            cache_args['ram_inactive'] = inactive_headroom
        else:
            old_ram_inactive_arg = None
            inactive_headroom = None
            cache_args.pop('ram_inactive', None)

        cache_args.setdefault('lru', 0)
        cache_args['ram'] = active_headroom
        return old_ram_arg, old_ram_inactive_arg, active_headroom, inactive_headroom, supports_inactive

    def _supports_inactive_cache_arg(self, executor):
        cache_args = getattr(executor, 'cache_args', None)
        if isinstance(cache_args, dict) and 'ram_inactive' in cache_args:
            return True

        return any(source is not None and 'ram_inactive' in source
                   for source in self._executor_async_sources())

    def _executor_async_sources(self):
        PromptExecutor = getattr(execution, 'PromptExecutor', None)
        sources = []
        # Newer executors keep cleanup in execute_async and execution in _execute_async.
        for name in ('execute_async', '_execute_async'):
            method = getattr(PromptExecutor, name, None)
            if method is None:
                continue
            try:
                sources.append(inspect.getsource(inspect.unwrap(method)))
            except (OSError, TypeError, ValueError):
                sources.append(None)
        return sources

    def _can_set_executor_ram_type(self, executor):
        if self._is_executor_ram_type(executor):
            return True
        return not self._uses_prompt_local_ram_release_callback()

    def _should_keep_ram_mode(self, executor):
        return self._is_executor_ram_type(executor) and self._uses_prompt_local_ram_release_callback()

    def _is_executor_ram_type(self, executor):
        CacheType = getattr(execution, 'CacheType', None)
        if CacheType is None:
            return False

        ram_type = getattr(CacheType, 'RAM_PRESSURE', None)
        return ram_type is not None and getattr(executor, 'cache_type', None) == ram_type

    def _uses_prompt_local_ram_release_callback(self):
        sources = self._executor_async_sources()
        # Unknown implementations must not enable a callback captured as None.
        return not sources or any(
            source is None or 'ram_release_callback' in source
            for source in sources
        )

    def _set_executor_cache_type(self, executor, target_mode_ram):
        CacheType = getattr(execution, 'CacheType', None)
        if CacheType is None:
            return

        if target_mode_ram:
            ram_type = getattr(CacheType, 'RAM_PRESSURE', None)
            if ram_type is not None:
                executor.cache_type = ram_type
            return

        classic_type = getattr(CacheType, 'CLASSIC', None)
        if classic_type is not None:
            executor.cache_type = classic_type

    def _format_headroom_log(self, prefix, active_headroom, inactive_headroom, supports_inactive):
        if supports_inactive:
            return f"{prefix} (active: {active_headroom}GB, inactive: {inactive_headroom}GB)"
        return f"{prefix} (headroom: {active_headroom}GB)"

    def _format_headroom_update_log(self, old_ram_arg, old_ram_inactive_arg, active_headroom, inactive_headroom, supports_inactive):
        if supports_inactive:
            return f"[DynamicRAMCache] Updated RAM headroom: active {old_ram_arg}GB -> {active_headroom}GB, inactive {old_ram_inactive_arg}GB -> {inactive_headroom}GB"
        return f"[DynamicRAMCache] Updated RAM headroom: {old_ram_arg}GB -> {active_headroom}GB"

    def _release_ram_cache(self, cache, active_headroom, inactive_headroom, supports_inactive):
        ram_release = getattr(cache, 'ram_release', None)
        if callable(ram_release):
            try:
                if supports_inactive and inactive_headroom is not None:
                    ram_release(int(inactive_headroom * (1024 ** 3)))
                ram_release(int(active_headroom * (1024 ** 3)), free_active=True)
                return
            except TypeError:
                try:
                    ram_release(int(active_headroom * (1024 ** 3)))
                    return
                except Exception:
                    pass
            except Exception as e:
                logging.warning(f"[DynamicRAMCache] RAM release failed: {e}")

        poll = getattr(cache, 'poll', None)
        if callable(poll):
            try:
                if supports_inactive:
                    poll(ram=active_headroom, ram_inactive=inactive_headroom)
                else:
                    poll(active_headroom)
            except TypeError:
                try:
                    poll(active_headroom)
                except Exception:
                    pass
            except Exception:
                pass

    def _find_executor(self):
        for obj in gc.get_objects():
            try:
                if obj.__class__.__name__ == 'PromptExecutor':
                    return obj
            except (ReferenceError, AttributeError):
                continue
            except Exception:
                continue
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
        try:
            cache_set.outputs = new_cache
            
            if hasattr(cache_set, 'all') and isinstance(cache_set.all, list):
                for i, item in enumerate(cache_set.all):
                    if i == 0: 
                        cache_set.all[i] = new_cache
        except (ReferenceError, AttributeError):
            logging.warning("[DynamicRAMCache] Failed to update cache_set: object no longer exists.")
        except Exception as e:
            logging.warning(f"[DynamicRAMCache] Unexpected error updating cache_set: {e}")

    def _switch_to_ram_pressure(self, cache_set, old_cache, caching_mod):
        key_class = getattr(old_cache, 'key_class', None)
        if not key_class:
            key_class = getattr(caching_mod, 'CacheKeySetInputSignature', None)

        new_cache = self._create_cache(caching_mod.RAMPressureCache, key_class)
        self._migrate_cache_data(old_cache, new_cache)
        if getattr(new_cache, 'timestamps', None) is None:
            new_cache.timestamps = {}
        if getattr(new_cache, 'used_generation', None) is None:
            new_cache.used_generation = {}
        if getattr(new_cache, 'children', None) is None:
            new_cache.children = {}
        if getattr(new_cache, 'generation', None) is None:
            new_cache.generation = 1
        if getattr(new_cache, 'min_generation', None) is None:
            new_cache.min_generation = 0

        if isinstance(getattr(new_cache, 'cache', None), dict) and isinstance(new_cache.timestamps, dict) and isinstance(new_cache.used_generation, dict):
            now = time.time()
            for key in new_cache.cache:
                if key not in new_cache.timestamps:
                    new_cache.timestamps[key] = now
                if key not in new_cache.used_generation:
                    new_cache.used_generation[key] = 0 

        self._update_cache_set(cache_set, new_cache)

    def _switch_to_classic(self, cache_set, old_cache, caching_mod):
        key_class = getattr(old_cache, 'key_class', None)
        if not key_class:
            key_class = getattr(caching_mod, 'CacheKeySetInputSignature', None)

        new_cache = self._create_cache(caching_mod.HierarchicalCache, key_class)
        self._migrate_cache_data(old_cache, new_cache)

        self._update_cache_set(cache_set, new_cache)

    def _create_cache(self, cache_class, key_class):
        try:
            return cache_class(key_class, enable_providers=True)
        except TypeError:
            return cache_class(key_class)

    def _migrate_cache_data(self, old_cache, new_cache):
        """迁移缓存核心数据"""
        try:
            old_dict = getattr(old_cache, '__dict__', None)
            new_dict = getattr(new_cache, '__dict__', None)
            if isinstance(old_dict, dict) and isinstance(new_dict, dict):
                new_dict.update(old_dict)
            else:
                old_cache_data = getattr(old_cache, 'cache', None)
                if old_cache_data is not None:
                    new_cache.cache = old_cache_data

                old_subcaches = getattr(old_cache, 'subcaches', None)
                if old_subcaches is not None:
                    new_cache.subcaches = old_subcaches

                new_cache.dynprompt = getattr(old_cache, 'dynprompt', None)
                new_cache.cache_key_set = getattr(old_cache, 'cache_key_set', None)
                new_cache.initialized = getattr(old_cache, 'initialized', False)

            if getattr(new_cache, 'cache', None) is None:
                new_cache.cache = {}
            if getattr(new_cache, 'subcaches', None) is None:
                new_cache.subcaches = {}

            if hasattr(old_cache, 'is_changed_cache'):
                new_cache.is_changed_cache = old_cache.is_changed_cache
            if getattr(new_cache, 'is_changed_cache', None) is None:
                new_cache.is_changed_cache = {}
        except (ReferenceError, AttributeError):
            logging.warning("[DynamicRAMCache] Failed to migrate cache data: source object no longer exists.")
        except Exception as e:
            logging.warning(f"[DynamicRAMCache] Unexpected error migrating cache data: {e}")

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
                if not hasattr(executor, 'cache_args') or executor.cache_args is None:
                    executor.cache_args = {}
                old_ram_arg = self._read_threshold(executor.cache_args.get('ram'), 2.0)
                old_ram_inactive_arg = self._read_threshold(executor.cache_args.get('ram_inactive'), old_ram_arg)
                cache_set = self._get_cache_set(executor)
                if cache_set is not None:
                    RAMPressureCacheClass = getattr(caching, 'RAMPressureCache', None)
                    if RAMPressureCacheClass:
                        is_currently_ram = isinstance(cache_set.outputs, RAMPressureCacheClass)
                        old_mode = "RAM_PRESSURE (Auto Purge)" if is_currently_ram else "CLASSIC (No Eviction)"
                    else:
                        old_mode = "CLASSIC (No Eviction)"
                    self._execute_cache_logic("RAM_PRESSURE (Auto Purge)", purge_threshold, purge_threshold)
                    self._execute_cache_logic(old_mode, old_ram_arg, old_ram_inactive_arg)
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
