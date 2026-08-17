# 5100 完整交付说明

## 为什么别人电脑上没有素材

这个项目不是只复制 Python 源码就能完整运行。剧情播放同时依赖：

- `generated/`：已经生成好的图片、Q3 分镜和完整剧情视频，当前约 2.23 GB。
- `data/production-jobs.json`：上述媒体文件的任务索引。
- `data/stories.json`：剧情树和节点配置。
- `../agent/`：PolarDB Mem0 外部记忆调用代码。

缺少 `generated/` 或 `production-jobs.json` 时，5100 服务虽然能打开，但剧情素材会显示未就绪。

## 发送方打包

在 `interactive-film-game` 目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\package-delivery.ps1
```

默认输出 `interactive-film-game-full.zip`。压缩包包含完整媒体和 `agent`，不包含 `.env`、API Key、控制台密码、日志或自动付费生产授权。

## 接收方首次启动

解压后保持以下目录关系：

```text
vidu-demo/
  agent/
  interactive-film-game/
```

进入 `interactive-film-game`，双击 `start-5100.cmd`。第一次运行会创建 `.env` 并停止，请在 `.env` 中填写接收方自己的 `VIDU_API_KEY`，然后再次双击启动。

也可以在 PowerShell 中运行：

```powershell
cd interactive-film-game
powershell -ExecutionPolicy Bypass -File .\start-5100.ps1
```

启动后打开：

```text
http://127.0.0.1:5100/
```

只验证预生成剧情、不启用 S1 时，可以执行：

```powershell
.\start-5100.ps1 -PreviewOnly
```

## 全链路配置

预生成剧情视频：压缩包必须包含 `generated/` 和 `data/production-jobs.json`，无需重新付费生成。

S1 实时数字人：接收方必须在 `.env` 填写自己的 `VIDU_API_KEY`，浏览器需要允许麦克风和摄像头权限。

PolarDB Mem0：接收方需要填写自己的 `POLARDB_MEM0_BASE_URL`、`POLARDB_MEM0_USER_ID`、`POLARDB_MEM0_AUTHORIZATION`，并将 `STORY_MEMORY_ENABLED` 设置为 `true`。

Vidu 云端无法访问 `localhost`。启用 Mem0 回调时，还必须用 Cloudflare Tunnel 或其他方式将本机 5100 暴露为公网 HTTPS，并设置：

```dotenv
PUBLIC_BASE_URL=https://接收方自己的公网域名
MEMORY_TOKEN=接收方自己生成的随机回调令牌
STORY_MEMORY_ENABLED=true
```

如果使用临时 Cloudflare Tunnel，每次重启 Tunnel 后公网域名可能变化，需要同步修改 `.env` 并重启 5100 服务。

## 验证命令

启动前检查交付包是否完整：

```powershell
py -3 tools\verify_delivery.py
```

启动后检查服务和剧情接口：

```powershell
py -3 tools\verify_delivery.py --url http://127.0.0.1:5100
```

正确结果最后一行应为：

```text
DELIVERY_OK
```

如果网页启用了 `CONSOLE_AUTH_USER` 和 `CONSOLE_AUTH_PASS`，验证时追加：

```powershell
py -3 tools\verify_delivery.py --url http://127.0.0.1:5100 --user 用户名 --password 密码
```

## 兼容性和注意事项

- 推荐 Python 3.10 或更高版本；脚本会自动安装 `requirements.txt`。
- 已有成片可以直接播放；只有继续合成缺失视频时才需要 FFmpeg。
- `5100` 被占用时，需要关闭旧进程，或修改 `.env` 中的 `INTERACTIVE_FILM_PORT`。
- 不要把你自己的 `.env` 发给别人，里面包含真实密钥。
- 2.23 GB 素材不适合通过只同步源码的 Git 仓库交付，应发送完整压缩包或对象存储下载地址。
