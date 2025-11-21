from .nodes import DynamicRAMCacheControl

NODE_CLASS_MAPPINGS = {
    "DynamicRAMCacheControl": DynamicRAMCacheControl
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DynamicRAMCacheControl": "🔥 Dynamic RAM Cache Control"
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]