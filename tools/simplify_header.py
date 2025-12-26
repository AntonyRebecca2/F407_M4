#!/usr/bin/env python3
"""
simplify_header.py

功能（针对初学者说明）：
- 读取由 `midi_to_buzzer.py` 生成的 C 头文件（例如包含 `static const Note_t melody[]` 的文件），
  并生成一个“简化版”头文件，例如 `badapple_melody_simple.h`。
- 简化操作包括：合并相同音高的相邻音符、对时长进行量化、删除/合并过短的音符、并限制总音符数。

用法示例：
  python tools/simplify_header.py Core/Src/badapple_melody.h Core/Src/badapple_melody_simple.h
"""
import re
import sys

def parse_header(path):
    """
    解析 C 头文件中的 melody 数组，提取 (freq, duration) 列表。

    实现细节：
    - 使用正则 `\\{\\s*(\\d+)\\s*,\\s*(\\d+)\\s*\\},` 匹配形如 `{123, 456},` 的条目。
      （注意：在此 docstring 中反斜杠已转义为 `\\`，以避免 Python 报告 SyntaxWarning）
    - 只提取数字并返回一个列表，格式为 [(freq, dur), ...]。

    参数：
    - path: 要解析的头文件路径（字符串）

    返回：
    - notes: 列表，元素为 (freq, dur) 的整数元组
    """
    pattern = re.compile(r"\{\s*(\d+)\s*,\s*(\d+)\s*\},")
    notes = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            m = pattern.search(line)
            if m:
                freq = int(m.group(1))
                dur = int(m.group(2))
                notes.append((freq, dur))
    return notes


def simplify_notes(notes, unit_ms=128, min_ms=80, max_notes=300):
    """
    简化并量化 notes 列表，适用于生成更短、更规则的蜂鸣器数据。

    步骤说明（面向初学者）：
    1. 合并相邻相同频率的音符（使其成为一个更长的音符）。
    2. 将每个音符的时长四舍五入到 unit_ms 的整数倍（time quantization）。
    3. 如果量化后时长小于 min_ms，则把该时间并入前一个条目（或在开头转为休止）。
    4. 如果输出条目数超过 max_notes，则把尾部时间合并到最后一个保留条目中。

    参数：
    - notes: 原始列表 [(freq, dur_ms), ...]
    - unit_ms: 量化单位（毫秒）
    - min_ms: 最小保留时长（毫秒）
    - max_notes: 最大允许的条目数

    返回：
    - quant: 简化后的列表 [(freq, dur_ms), ...]
    """
    if not notes:
        return []
    merged = []
    for f, d in notes:
        if merged and merged[-1][0] == f:
            merged[-1] = (f, merged[-1][1] + d)
        else:
            merged.append((f, d))

    quant = []
    for f, d in merged:
        q = int(round(d / unit_ms))
        if q <= 0:
            q = 1
        d2 = int(q * unit_ms)
        if d2 < min_ms:
            if quant:
                quant[-1] = (quant[-1][0], quant[-1][1] + d2)
            else:
                quant.append((0, d2))
        else:
            quant.append((f, d2))

    if len(quant) > max_notes:
        keep = quant[:max_notes-1]
        tail = quant[max_notes-1:]
        tail_time = sum(d for _, d in tail)
        if keep:
            lastf, lastd = keep[-1]
            keep[-1] = (lastf, lastd + tail_time)
        else:
            keep = [(0, tail_time)]
        quant = keep
    return quant


def emit_header(notes, out_path, guard_name='BADAPPLE_MELODY_SIMPLE_H'):
    """
    将 notes 列表写入 C 头文件，生成格式化良好的 `melody` 数组。

    注意事项：
    - 把负值时长转换为 0，超出 uint16 最大值的时长会被截断为 0xFFFF，
      以避免生成会导致 C 端溢出的常量。
    - 生成包含头保护（#ifndef/#define）和 `melody_len` 的完整头文件。
    """
    MAX_UINT16 = 0xFFFF
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('/* Auto-generated simplified melody */\n')
        f.write(f'#ifndef {guard_name}\n')
        f.write(f'#define {guard_name}\n\n')
        f.write('#include "main.h"\n\n')
        f.write('typedef struct {\n    uint16_t freq;\n    uint16_t duration;\n} Note_t;\n\n')
        f.write('static const Note_t melody[] = {\n')
        for freq, dur in notes:
            if dur < 0:
                dur = 0
            if dur > MAX_UINT16:
                # 超出 uint16 上限则截断
                dur = MAX_UINT16
            f.write(f'  {{{freq}, {dur}}},\n')
        f.write('};\n\n')
        f.write('static const size_t melody_len = sizeof(melody)/sizeof(melody[0]);\n\n')
        f.write(f'#endif /* {guard_name} */\n')


def main():
    # 用法提示（简体中文）
    if len(sys.argv) < 3:
        print('用法: python tools/simplify_header.py <in-header.h> <out-simple.h>')
        return
    inp = sys.argv[1]
    out = sys.argv[2]
    notes = parse_header(inp)
    print(f'已解析 {len(notes)} 个事件来自文件: {inp}')

    # 估算四分之一拍的毫秒数（quarter_ms）用于量化：
    # 这里使用中位数 * 4 / 8 的方式来估计量化单位（与 midi_to_buzzer 的策略匹配）。
    durs = [d for f, d in notes if d>0]
    if durs:
        durs_sorted = sorted(durs)
        q = durs_sorted[len(durs_sorted)//2] * 4
        unit = int(round(q / 8))
    else:
        unit = 128
    print(f'使用量化单位 unit_ms={unit}')

    simple = simplify_notes(notes, unit_ms=unit, min_ms=80, max_notes=300)
    print(f'简化后得到 {len(simple)} 个事件')
    emit_header(simple, out)
    print(f'已写入简化头文件: {out}')

if __name__ == '__main__':
    main()
