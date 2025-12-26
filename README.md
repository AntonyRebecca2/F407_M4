# F407_M4 工具说明

✅ 本仓库包含两个用于把 MIDI 转为适合微控制器蜂鸣器播放的 C 头文件的工具：
- `tools/midi_to_buzzer.py`：从 MIDI 文件提取单旋律并生成 C 头文件。
- `tools/simplify_header.py`：对已有的 melody 头文件做二次简化（量化、合并、裁剪）。

---

## 目录
- 📘 简介
- ⚙️ 依赖与安装
- ▶️ 使用示例
  - `midi_to_buzzer.py`
  - `simplify_header.py`
- 🔧 输出格式说明
- 🐞 调试与常见问题
- 📝 许可证

---

## 简介 ✨
这些脚本用于把 MIDI 的旋律转换为微控制器可用的常量表（C 头文件），方便在 STM32 等嵌入式设备上通过蜂鸣器或 PWM 生成旋律。

- 时间单位为毫秒（ms）。
- 休止（rest）用 `freq == 0` 表示。
- 当 MIDI 同时有多个音符（和弦）时，工具会选取**响度（velocity）最大**的音符来生成单声道序列，以适配只能播放单音的蜂鸣器。

---

## 依赖与安装 ✅
- Python 3.x
- 仅 `midi_to_buzzer.py` 需要第三方库：

```bash
python -m pip install mido
```

`simplify_header.py` 仅使用标准库（`re`, `sys`）。

---

## 使用示例 ▶️

### 1) 从 MIDI 生成头文件（`midi_to_buzzer.py`）
基本用法：

```bash
python tools/midi_to_buzzer.py <midi-file> <out-header.h>
```

示例：

```bash
python tools/midi_to_buzzer.py assets/badapple.mid Core/Src/badapple_melody.h
```

可选参数（简要说明）：
- `--simplify`：在生成的基础上做量化与简化并写入 `<name>_simple.h`。
- `--denom=N`：量化分母（默认 8，值越大，时间网格越细）。
- `--min-ms=N`：最小保留时长（默认 80 ms），低于该值的短音会被并入前一条。
- `--max-notes=N`：简化时允许的最大音符数（默认 400）。
- `--monophonic` / `--preserve-length`：只输出已提取的单声道（不简化）。

举例（生成简化头文件）：

```bash
python tools/midi_to_buzzer.py assets/badapple.mid Core/Src/badapple_melody.h --simplify --denom=8 --min-ms=80 --max-notes=300
```

输出：`Core/Src/badapple_melody_simple.h`（包含 `static const Note_t melody[]`）。

---

### 2) 对已有头文件做二次简化（`simplify_header.py`）
基本用法：

```bash
python tools/simplify_header.py <in-header.h> <out-simple.h>
```

示例：

```bash
python tools/simplify_header.py Core/Src/badapple_melody.h Core/Src/badapple_melody_simple.h
```

该脚本会：解析 `{freq, duration},` 这类条目，合并相邻相同频率、量化时长、合并过短项并限制总条目数。

---

## 输出格式说明 🔎
生成的头文件包含：

```c
typedef struct {
    uint16_t freq;      // 0 表示休止
    uint16_t duration;  // 毫秒（ms）
} Note_t;

static const Note_t melody[] = {
  {440, 200},
  {0, 50},
  {523, 300},
};

static const size_t melody_len = sizeof(melody)/sizeof(melody[0]);
```

- `freq==0` 表示休止。
- `duration` 单位为毫秒。为了兼容嵌入式平台，持续时间会截断到 `uint16_t` 的范围（最大 65535）。

---

## 调试与常见问题 🐞
- 如果缺少 `mido`，会在运行时报导出错：

```text
Missing dependency 'mido'. Install with: python -m pip install mido
```

- 语法检查：可以使用 `python -m py_compile` 对脚本做快速语法校验：

```bash
python -m py_compile tools/midi_to_buzzer.py tools/simplify_header.py
```

- 时间量化（unit）如何得到：脚本会根据 MIDI tempo 或已生成头文件的时长中位数估算量化单位。你可以使用 `--denom` 或手动调用 `simplify_header.py` 来调整。

- 如果希望更精细的控制（例如使用 `argparse` 提供更详细的 CLI 帮助），我可以帮你改写工具以支持更友好的参数解析和帮助信息。

### 在闭源项目中安全使用生成的头文件（小贴士） 🔒
- 生成的 `.h` 文件通常只包含数据（频率/时长），通常被视为工具的“输出”而不是工具源码的衍生作品，因此**通常可以安全地包含在闭源或商业固件中**。
- 但如果你**直接复制或重用本仓库的源代码**（比如把工具的某些实现粘贴到你的项目中），则需要遵守本仓库的 MIT 许可证：保留版权声明并包含 `LICENSE` 文件（或在文档中注明）。
- 建议做法：在闭源项目中使用生成的头文件时，在项目文档或发行说明中注明“该头文件由本仓库生成（MIT 许可证）”，保留 `LICENSE` 链接以提高透明度。
- 以上为一般性说明，不构成法律意见；如需在商业环境中完全确认许可合规性，请咨询专业法律顾问。

---

## 贡献 & 联系 🤝
欢迎提交 issue 或 PR 来改进脚本（例如：增加单元测试、支持更多 MIDI 特性、加入示例文件等）。

---

## 许可证 📄
本项目采用 **MIT 许可证（MIT License）**。

Copyright (c) 2025 RX_11

详细信息请见仓库根目录的 `LICENSE` 文件。