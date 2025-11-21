简体中文 | [English](./README.md)

# ComfyUI_Dynamic_RAMCache

一个ComfyUI的自定义节点，用于动态控制和优化RAM缓存管理，支持智能内存清理以提高大模型运行效率。

## 功能特点

- **动态缓存模式切换**：支持在CLASSIC（无内存回收）和RAM_PRESSURE（自动内存清理）模式之间切换
- **智能内存管理**：自动监控和清理RAM缓存，当内存不足时释放不必要的缓存数据
- **自定义清理阈值**：允许用户设置最小空闲内存保持量，灵活适应不同硬件配置
- **无缝数据迁移**：在切换缓存模式时保留现有缓存数据，避免重复计算
- **直观的节点接口**：简单易用的参数设置，适用于不同水平的用户

## 安装方法

1. 确保已安装ComfyUI（支持2025.10.31及更新版本）
2. 克隆或下载本仓库
3. 将`ComfyUI_Dynamic_RAMCache`文件夹复制到ComfyUI的`custom_nodes`目录下
4. 重启ComfyUI

## 使用方法

1. 在ComfyUI中，从`utils/dynamic_ramcache`类别中添加`DynamicRAMCacheControl`节点
2. 配置以下参数：
   - **mode**：选择缓存模式（CLASSIC或RAM_PRESSURE）
   - **cleanup_threshold**：设置最小空闲内存保持量（GB）
3. 可以选择性地连接任意输入到`any_input`端口（节点会透传此输入）
4. 运行工作流

## 参数说明

### mode（模式）

- **CLASSIC (No Eviction)**：传统缓存模式，不会自动清理缓存，可能导致内存使用持续增长
- **RAM_PRESSURE (Auto Purge)**：自动内存清理模式，当可用内存低于设定阈值时会自动清理缓存

### cleanup_threshold（清理阈值）

- 类型：浮点数（0.1-256.0 GB）
- 默认值：2.0 GB
- 说明：系统尝试维持的最小空闲内存量。当可用内存低于此值时，RAM_PRESSURE模式会触发缓存清理

### 输出

- **output_passthrough**：如果连接了输入，则透传输入值；否则返回None

## 工作原理

该节点通过以下机制工作：

1. 检测ComfyUI的`PromptExecutor`实例
2. 根据所选模式在`RAMPressureCache`和`HierarchicalCache`之间切换
3. 在切换过程中保留现有的缓存数据
4. 当处于RAM_PRESSURE模式时，监控系统内存并在需要时触发缓存清理

## 兼容性要求

- **ComfyUI版本**：需要2025.10.31或更新版本（包含RAMPressureCache类）
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
   - 原因：可能清理阈值设置过高或系统内存监控不工作
   - 解决方案：尝试降低cleanup_threshold值，或检查系统内存使用情况

## 注意事项

- 在大型工作流中，过低的清理阈值可能导致频繁的缓存清理，反而降低性能
- 建议根据系统实际RAM大小调整清理阈值，一般建议设置为总内存的10-20%
- 首次切换到RAM_PRESSURE模式时可能需要一些时间来初始化新的缓存系统

## 日志信息

该节点会在以下情况输出日志：

- 缓存模式切换
- 清理阈值更新
- 错误和警告信息

日志可在ComfyUI的控制台或日志文件中查看，前缀为`[DynamicRAMCache]`

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎提交问题报告和拉取请求！