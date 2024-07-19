# HomeAssistant Integration Mihomo

在 Home Assistant 中显示 Mihomo（Clash）网速，Fallback 和 URLTest 当前状态和选择 Selector 节点的集成

## 使用方法

将 custom_components 放入 Home Assistant 的目录内，然后在 configuration.yaml 添加以下内容

```yaml
mihomo:
  uri: 路由器的地址:9090
```

然后重新启动 Home Assistant
