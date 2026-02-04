[简体中文](./README_zh.md) | English

# ComfyUI Dynamic RAM Cache Control

A custom node for ComfyUI that dynamically manages RAM usage by intelligently controlling cache purging based on available system memory.

## Features

- **Dual Cache Management Modes**: 
  - CLASSIC (No Eviction): Standard cache behavior with no automatic purging
  - RAM_PRESSURE (Auto Purge): Smart cache purging when system memory falls below the threshold
- **RAM Cache Extreme Cleanup (🧹)**: Performs a one-time aggressive purge and automatically restores the previous mode and threshold.
- **Configurable Memory Threshold**: Fine-tune the minimum amount of free RAM to maintain
- **Seamless Cache Migration**: Preserves essential cache data when switching between modes
- **Real-time Memory Monitoring**: Continuously checks system RAM and virtual memory availability

## Installation

1. Clone or download this repository
2. Place the `ComfyUI_Dynamic-RAMCache` folder in your ComfyUI `custom_nodes` directory
3. Restart ComfyUI

## Usage

1. Add the "DynamicRAMCacheControl" node to your workflow
2. Configure the following parameters:

### Parameters

- **mode**: 
  - CLASSIC (No Eviction): Traditional cache behavior without automatic purging
  - RAM_PRESSURE (Auto Purge): Automatic cache purging when memory is constrained

- **cleanup_threshold**: 
  - Range: 0.1 - 256.0 GB
  - Default: 2.0 GB
  - Determines the minimum amount of free RAM to maintain (in gigabytes)

### Extreme Cleanup Parameters

- **purge_threshold**:
  - Range: 0.1 - 256.0 GB
  - Default: 256.0 GB
  - Temporary headroom used for the one-shot purge

- **restore behavior**:
  - Automatically restores the mode and threshold that were active before cleanup

3. Connect the node anywhere in your workflow - it will continuously monitor and manage cache based on your settings
4. Optionally add the "RAMCacheExtremeCleanup" node at the end of a workflow to trigger a one-shot cleanup and restore the previous state

## How It Works

### CLASSIC Mode

In CLASSIC mode, the node maintains standard cache behavior without automatic purging. This mode is suitable when:
- You have abundant RAM
- You prefer maximum performance without worrying about memory usage
- You're working with complex workflows that benefit from extensive caching

### RAM_PRESSURE Mode

In RAM_PRESSURE mode, the node actively monitors system memory and intelligently purges cache when:
1. Available system RAM falls below the specified cleanup_threshold
2. The system is experiencing memory pressure

When purging, it prioritizes removing older, less recently used cache items while attempting to preserve critical data.

## Compatibility

- Compatible with all ComfyUI versions
- Works with both CPU and GPU processing
- Supports all standard ComfyUI nodes and workflows

## Troubleshooting

### Performance Issues
- If you notice frequent cache purging, try increasing the cleanup_threshold value
- For systems with limited RAM, a lower threshold (0.5-1.0 GB) might be more appropriate

### Unexpected Behavior
- Ensure you're running the latest version of ComfyUI
- Check the console output for any error messages related to the dynamic cache control
- Try restarting ComfyUI if you encounter any persistent issues

## Log Information

The node outputs helpful log messages to track its operations, including:
- Mode changes (CLASSIC to RAM_PRESSURE or vice versa)
- Cache initialization and migration
- Memory threshold updates
- Cache purging events when in RAM_PRESSURE mode

## License

MIT License

## Acknowledgements

This node is designed to help users maximize both performance and stability in their ComfyUI workflows by intelligently managing system resources.

---

For more information or to report issues, please visit the repository page.
