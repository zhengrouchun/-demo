# 为什么暂不把 sherpa-onnx 热词模型替换正式转写引擎

## 本机试验范围

2026-11-02 在 Windows CPU 上试验预训练的 `sherpa-onnx-funasr-nano-int8-2025-12-30`，运行库为 `sherpa-onnx 2.0.1` 与匹配的 `sherpa-onnx-core 2.0.1`。模型与运行库均放在 Git 忽略的 `LocalLecture/models/classroom-benchmark/`，没有改动正式转写代码、历史数据或用户音视频。镜像下载的三个 ONNX 文件分别通过模型作者页面公布的 SHA256 校验：

| 文件 | SHA256 |
| --- | --- |
| `embedding.int8.onnx` | `95e61cd0c9c3b9543339a4cf973c95c116815e745ccc1e0285cbd81f76d18644` |
| `encoder_adaptor.int8.onnx` | `f36dea2e30fbc33b5db1d7a7265cc976c5e5586c77b042d5adb1ad27c72db422` |
| `llm.int8.onnx` | `dfbf9aa3be41bccc257587f151e15c63fbe1b549f2b517f5ccd5bdce3bf4322a` |

本机试验使用项目现成的 26.67 秒、1.5 倍速路由器音频，以及 622.8 秒人工校对系统声音样本。对照稿和音频都没有提交。字错率沿用 `LocalLecture/scripts/score_classroom_transcription.py:character_error_rate` 的全半角、大小写、标点及空白归一化规则。

## 结果

| 同一份 622.8 秒样本 | 处理时间 | 字错率 |
| --- | ---: | ---: |
| 现有 Fun-ASR GGUF，10 秒窗口 | 370.24 秒 | 3.0133% |
| 现有 Fun-ASR GGUF，30 秒窗口 | 395.62 秒 | 2.5977% |
| sherpa-onnx INT8，10 秒窗口，无热词 | 206.11 秒 | 14.4015% |
| sherpa-onnx INT8，10 秒窗口，MAC/WAN/LAN 热词 | 230.12 秒 | 12.9884% |

这份 622.8 秒参考稿不含 MAC、WAN、LAN，因此其字错率用于检查**整体文字是否退步**，不能单独证明热词召回率。sherpa-onnx 的结果虽处理得更快，但两种设置均未达到现有准确率。

路由器音频切成 0–10、10–20、20–26.67 秒三段识别：无热词时仍出现“麦克”“万口”；加入 `MAC,WAN,LAN` 后，第二段一个 `LAN 口` 正确，但 `MAC` 仍写成“麦克”，`WAN 口` 仍写成“万口”，第一段还少了一处有关 MAC 的短语。若将 26.67 秒整段直接送入该 ONNX 运行方式，无热词结果中途截断，有热词结果只剩开头几个字；把 `max_new_tokens` 从默认 512 提高至 1024 后仍重现。**截断的内部原因尚未确定**，因此只把它记为本机复现的风险，不推断为模型本身的普遍限制。

## 排查与结论

初次加载失败提示 ONNX Runtime API 版本不匹配。检查 `sherpa_onnx-2.0.1.dist-info/METADATA` 和已安装 DLL 后，确认隔离安装漏掉所声明的 `sherpa-onnx-core==2.0.1`；补齐该核心包后模型能运行。随后 `create_stream(hotwords=...)` 提示该接口仅供 transducer 模型使用；Fun-ASR-Nano 改用创建流后的 `set_option("hotwords", "MAC,WAN,LAN")`，这是 [sherpa-onnx 的 FunASR Nano 接口](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/c-api/docs/offline-asr.dox)给出的方式。

三个权重的官方校验信息：[embedding](https://huggingface.co/csukuangfj/sherpa-onnx-funasr-nano-int8-2025-12-30/blob/main/embedding.int8.onnx)、[encoder](https://huggingface.co/csukuangfj/sherpa-onnx-funasr-nano-int8-2025-12-30/blob/main/encoder_adaptor.int8.onnx)、[llm](https://huggingface.co/csukuangfj/sherpa-onnx-funasr-nano-int8-2025-12-30/blob/main/llm.int8.onnx)。隔离安装命令为 `pip download sherpa-onnx==2.0.1`、`pip download sherpa-onnx-core==2.0.1`、`pip install --no-index --no-deps --target ...`；模型使用 Hugging Face 镜像下载后逐个运行 `Get-FileHash -Algorithm SHA256`。试验代码通过 Python 标准输入执行；完整 10 分钟结果保存在 Git 忽略的 `samples/sherpa_onnx_热词与无热词对比.json`。

**决定：不接入这一 ONNX INT8 候选。** 当前已验证的 GGUF 链路继续使用。若继续寻找可配置热词的方案，需先在同一音频上验证整体字错率、MAC/WAN/LAN 准确数、处理速度、时间戳与长课稳定性。VLAN 没有已核对的配音样本，不能宣称已改善。
