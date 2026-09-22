[简体中文](./README_zh.md) | English

# ComfyUI Dynamic RAM Cache Control

A custom node for ComfyUI that manages RAM cache objects inside a workflow, updates RAM cache thresholds, and triggers active cache purging.

## Features

- **Dual Cache Management Modes**:
  - CLASSIC (No Eviction): Standard cache behavior with no automatic purging
  - RAM_PRESSURE (Auto Purge): RAM pressure cache behavior; per-node automatic release requires the executor to start the prompt in RAM_PRESSURE
- **RAM Cache Extreme Cleanup (🧹)**: Performs a one-time aggressive purge and automatically restores the previous mode and thresholds.
- **Configurable Memory Thresholds**: Supports the newer `--cache-ram active inactive` RAM threshold pair
- **Cache Migration**: Preserves essential cache data when the cache mode changes
- **Runtime Compatibility Handling**: Avoids unsafe prompt-time executor mode changes on newer ComfyUI builds

## Installation

1. Clone or download this repository
2. Place the `ComfyUI_Dynamic-RAMCache` folder in your ComfyUI `custom_nodes` directory
3. Restart ComfyUI

Requires a ComfyUI build that includes `RAMPressureCache`, available upstream from 2025-10-31.

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
  - Active cache free RAM threshold, matching the first `--cache-ram` value

- **inactive_threshold**:
  - Range: 0 - 256.0 GB
  - Default: 0 GB
  - Inactive cache / pinned memory threshold, matching the optional second `--cache-ram` value
  - Optional for old workflows. `0` keeps ComfyUI's current value, and older ComfyUI builds ignore it

### Extreme Cleanup Parameters

- **purge_threshold**:
  - Range: 0.1 - 256.0 GB
  - Default: 256.0 GB
  - Temporary headroom used for the one-shot purge

- **restore behavior**:
  - Automatically restores the mode and both thresholds that were active before cleanup

3. Connect the node anywhere in your workflow to update cache behavior and trigger active purging when it executes
4. Optionally add the "RAMCacheExtremeCleanup" node at the end of a workflow to trigger a one-shot cleanup and restore the previous state

## How It Works

### CLASSIC Mode

In CLASSIC mode, the node maintains standard cache behavior without automatic purging. This mode is suitable when:
- You have abundant RAM
- You prefer maximum performance without worrying about memory usage
- You're working with complex workflows that benefit from extensive caching

### RAM_PRESSURE Mode

In RAM_PRESSURE mode, cache purging can happen in two ways:
1. If the executor starts the prompt in RAM_PRESSURE, ComfyUI can release RAM cache after each node
2. When this node executes, it can trigger an active purge using the configured thresholds

When purging, it prioritizes removing older, less recently used cache items while attempting to preserve critical data.

## Upstream Change Dates

- 2025-10-31: ComfyUI added `RAMPressureCache`, commit `513b0c46` (Add RAM Pressure cache mode)
- 2026-04-29: `PromptExecutor.execute_async()` started directly calling the prompt-start `ram_release_callback`, commit `fce03984` (dynamicVRAM + --cache-ram 2)
- 2026-05-21: RAM cache became the default cache mode and active/inactive thresholds were added, commit `5aa5ccc9` (Multi-threaded load of models from disk)

This node's newer ComfyUI compatibility handling mainly targets the prompt-local RAM release callback behavior after 2026-04-29 and the default RAM cache behavior after 2026-05-21.

## Newer ComfyUI Behavior

Some newer ComfyUI builds capture the RAM release callback when a prompt starts. A custom node runs after prompt execution has already started, so changing the executor from CLASSIC to RAM_PRESSURE during the same prompt can cause `NoneType object is not callable`.

To avoid that error, this node detects that executor behavior:

- Detection covers both `execute_async()` and the newer `_execute_async()` implementation. If source inspection is unavailable, mode switching remains restricted for safety.
- Newer ComfyUI builds usually start in RAM_PRESSURE/RAM cache mode. The node keeps that state, updates thresholds, and preserves per-node automatic cache release
- If the executor starts in CLASSIC, the node enables the RAMPressureCache object, migrates cache data, and performs an active purge, but keeps the executor mode unchanged for the current prompt
- If a workflow requests CLASSIC, the node keeps RAM_PRESSURE active on newer prompt-local callback builds to avoid making later prompts start from CLASSIC
- For full per-node automatic release, keep RAM_PRESSURE active before the prompt starts. If your ComfyUI build does not default to RAM cache, launch it with `--cache-ram`

## Compatibility

- Requires a ComfyUI build that includes `RAMPressureCache`
- Handles both old and new `--cache-ram` argument shapes
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

### "executor mode kept as CLASSIC" Warning
- This means the current ComfyUI build stores a prompt-local RAM release callback
- The node keeps the executor mode unchanged to avoid the `NoneType object is not callable` error
- Threshold updates, cache migration, and active purging still run, but executor-level per-node automatic release is not enabled for that prompt

### "CLASSIC requested, RAM_PRESSURE kept active" Warning
- Newer ComfyUI builds usually start in RAM cache mode, so the node ignores CLASSIC mode requests inside a prompt
- RAM cache remains active; if you need to disable it, do that outside prompt execution through ComfyUI startup or global settings

## Log Information

The node outputs helpful log messages to track its operations, including:
- Mode changes (CLASSIC to RAM_PRESSURE or vice versa)
- Cache initialization and migration
- Memory threshold updates
- Compatibility warnings when the executor mode is kept unchanged on newer ComfyUI builds
- Cache purging events when in RAM_PRESSURE mode

## License

MIT License

## Acknowledgements

This node is designed to help users maximize both performance and stability in their ComfyUI workflows by intelligently managing system resources.

---

For more information or to report issues, please visit the repository page.
