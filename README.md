# 绝区零剧情语料提取器

为绳网剧情档案库 MCP 生成简体中文语料。

在 Windows 上安装 Python 3.11 或更高版本，双击仓库根目录的 **一键提取.cmd**。首次运行会准备 Python 环境并下载文本和配置。工具会自动查找本机游戏资源，用来识别说话人和场景。

提取完成后，供档案库导入的文件是 **out/story-corpus.json.gz**。包内含主线、活动、支线、代理人故事、漫画、过场字幕和设定资料。哲与铃的剧情收在同一包中。再次双击即可更新，成功后才会替换旧包。

## 上传到绳网后端

已有语料包时，直接双击 **一键上传.cmd**。按提示输入绳网管理员的邮箱或用户名和密码，工具会把现有包发到 `https://ik.tiwat.cn`。看到「语料已生效」和语料版本 ID 即表示发布成功。

也可以在仓库根目录用 PowerShell 运行同一条上传命令。

```powershell
.\.venv\Scripts\python.exe -m zzz_story upload
```

原有的 `IK_ACCOUNT`、`IK_PASSWORD` 和 `IK_TOKEN` 环境变量仍可用。设置了管理员令牌 `IK_TOKEN` 就会直接上传。自建后端可用 `IK_SERVER` 指定地址。

## 许可与来源

代码采用 [MIT 许可](LICENSE)。游戏文本版权归米哈游所有，请勿公开分发提取的语料。

文本与配置来自 [ZenlessData](https://git.mero.moe/dimbreath/ZenlessData)。演出资源解析参考 [zenless-voice](https://github.com/simon300000/zenless-voice)（MIT），Oodle 解压使用 [pyooz](https://pypi.org/project/pyooz/)（GPLv3）。
