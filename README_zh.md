简体中文 | [English](./README.md)

# ComfyUI_Dynamic_RAMCache

一个ComfyUI的自定义节点，用于在工作流中控制RAM缓存对象、更新清理阈值，并触发主动内存清理。

## 功能特点

- **动态缓存模式控制**：支持在CLASSIC（无内存回收）和RAM_PRESSURE（自动内存清理）模式之间调整
- **智能内存管理**：在RAM_PRESSURE可用时清理 RAM 缓存，当内存不足时释放不必要的缓存数据
- **自定义清理阈值**：支持新版 `--cache-ram active inactive` 两个 RAM 阈值
- **缓存数据迁移**：在模式变化时保留现有缓存数据，减少重复计算
- **直观的节点接口**：简单易用的参数设置，适用于不同水平的用户
- **极限清理节点**：一次性强清理（包含虚拟内存占用）并自动恢复清理前的模式与阈值

## 安装方法

1. 确保已安装包含`RAMPressureCache`的ComfyUI版本（上游从2025-10-31开始提供）
2. 克隆或下载本仓库
3. 将`ComfyUI_Dynamic-RAMCache`文件夹复制到ComfyUI的`custom_nodes`目录下
4. 重启ComfyUI

## 使用方法

1. 在ComfyUI中，从`utils/dynamic_ramcache`类别中添加`DynamicRAMCacheControl`节点
2. 配置以下参数：
   - **mode**：选择缓存模式（CLASSIC或RAM_PRESSURE）
   - **cleanup_threshold**：设置 active cache 空闲内存阈值（GB）
   - **inactive_threshold**：可选。设置 inactive cache / pinned memory 阈值（GB），填 `0` 或旧工作流缺少此项时沿用 ComfyUI 当前值
3. 可以选择性地连接任意输入到`any_input`端口（节点会透传此输入）
4. 可选：在工作流末尾添加`RAMCacheExtremeCleanup`节点，执行一次性清理并恢复之前状态
5. 运行工作流

## 参数说明

### mode（模式）

- **CLASSIC (No Eviction)**：传统缓存模式，不会自动清理缓存，可能导致内存使用持续增长
- **RAM_PRESSURE (Auto Purge)**：RAM_PRESSURE缓存模式。执行器以该模式开始时，每个节点后会自动清理；从CLASSIC开始时，本节点只在自身执行时主动清理

### cleanup_threshold（active 阈值）

- 类型：浮点数（0.1-256.0 GB）
- 默认值：2.0 GB
- 说明：对应新版 `--cache-ram` 的第一个值。可用内存低于此值时，RAM_PRESSURE模式会清理 active cache

### inactive_threshold（inactive 阈值）

- 类型：浮点数（0-256.0 GB）
- 默认值：0
- 说明：对应新版 `--cache-ram` 的第二个值。旧版 ComfyUI 不使用该参数时会自动忽略；`0` 表示不改 ComfyUI 当前值；大于 `0` 时会更新 inactive cache / pinned memory 阈值

### 极限清理参数

- **purge_threshold**：一次性清理时使用的临时阈值（默认 256.0 GB）
- **恢复行为**：自动恢复清理前的模式、active 阈值和 inactive 阈值

### 输出

- **output_passthrough**：如果连接了输入，则透传输入值；否则返回None

## 工作原理

该节点通过以下机制工作：

1. 检测ComfyUI的`PromptExecutor`实例
2. 根据所选模式在`RAMPressureCache`和`HierarchicalCache`之间切换
3. 在切换过程中保留现有的缓存数据
4. 当处于RAM_PRESSURE模式时，按 active / inactive 两个阈值处理缓存清理；执行器级别的每节点自动释放只在prompt开始前已经启用RAM_PRESSURE时生效

## 上游变更日期

- 2025-10-31：ComfyUI加入`RAMPressureCache`模式，提交`513b0c46`（Add RAM Pressure cache mode）
- 2026-04-29：`PromptExecutor.execute_async()`开始直接调用prompt开始时保存的`ram_release_callback`，提交`fce03984`（dynamicVRAM + --cache-ram 2）
- 2026-05-21：RAM cache成为默认缓存模式，并加入active/inactive双阈值，提交`5aa5ccc9`（Multi-threaded load of models from disk）

本节点的新版兼容处理主要针对2026-04-29之后的prompt-local RAM释放回调行为，以及2026-05-21之后默认启用RAM cache的行为。

## 新版ComfyUI行为说明

部分新版ComfyUI会在一个prompt开始时保存RAM释放回调。自定义节点是在prompt运行中执行的，这时再把执行器从CLASSIC改成RAM_PRESSURE，可能触发`NoneType object is not callable`。

为避免这个错误，节点会检测这种执行器实现：

- 同时检查 `execute_async()` 和新版的 `_execute_async()`；无法读取实现时，仍限制执行中切换模式，避免调用任务开始时为空的回调。
- 新版ComfyUI通常已经以RAM_PRESSURE/RAM cache模式开始，节点会保持这个状态，更新阈值，并保留每个节点执行后的自动清理行为
- 如果执行器以CLASSIC开始，节点会启用RAMPressureCache对象、迁移缓存并执行一次主动清理，但不会在当前prompt内改执行器模式
- 如果工作流请求CLASSIC，节点会在新版prompt-local回调实现中保留RAM_PRESSURE，避免把下一次prompt带入CLASSIC状态
- 需要完整的每节点自动清理时，请保持prompt开始前已经处于RAM_PRESSURE；如果你的ComfyUI版本不是默认RAM cache，再使用`--cache-ram`

## 兼容性要求

- **ComfyUI版本**：需要包含RAMPressureCache类的版本；新版和旧版`--cache-ram`参数形式都会处理
- **Python环境**：与ComfyUI兼容的Python环境
- **依赖**：使用ComfyUI内置的caching和execution模块

## 故障排除

### 常见问题

1. **"RAMPressureCache class not available"错误**
   - 原因：使用的ComfyUI版本过低
   - 解决方案：更新ComfyUI到2025.10.31或更高版本

2. **"Failed to import execution module"错误**
   - 原因：ComfyUI的模块结构可能已更改
   - 解决方案：检查ComfyUI版本，确认是否需要更新插件

3. **内存清理不生效**
   - 原因：可能清理阈值设置过高，或当前prompt是从CLASSIC执行器模式开始
   - 解决方案：尝试降低cleanup_threshold值；需要每个节点执行后的自动清理时，保持prompt开始前已经处于RAM_PRESSURE

4. **出现"executor mode kept as CLASSIC"警告**
   - 原因：当前ComfyUI在prompt开始时保存RAM释放回调，节点避免在prompt运行中改变执行器模式
   - 影响：节点仍会更新阈值、迁移缓存并执行主动清理，但当前prompt不会获得执行器级别的每节点自动释放

5. **出现"CLASSIC requested, RAM_PRESSURE kept active"警告**
   - 原因：新版ComfyUI默认已经是RAM cache模式，节点忽略工作流里的CLASSIC切换请求，避免后续prompt从CLASSIC开始
   - 影响：RAM cache继续启用；如果确实要关闭RAM cache，请在prompt外调整ComfyUI启动参数或全局设置

## 注意事项

- 在大型工作流中，过低的清理阈值可能导致频繁的缓存清理，反而降低性能
- 建议根据系统实际RAM大小调整清理阈值，一般建议设置为总内存的10-20%
- 首次使用RAM_PRESSURE模式时可能需要一些时间来初始化新的缓存系统

## 日志信息

该节点会在以下情况输出日志：

- 缓存模式变化
- 清理阈值更新
- 新版ComfyUI中保留CLASSIC执行器模式的兼容警告
- 错误和警告信息

日志可在ComfyUI的控制台或日志文件中查看，前缀为`[DynamicRAMCache]`

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎提交问题报告和拉取请求！
