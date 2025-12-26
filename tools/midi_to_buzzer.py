#!/usr/bin/env python3
"""
midi_to_buzzer.py

用法示例：
  python tools/midi_to_buzzer.py assets/badapple.mid Core/Src/badapple_melody.h

依赖：
  需要安装第三方库 `mido`：
    python -m pip install mido

脚本功能（针对初学者说明）：
- 从 MIDI 文件中提取单声道（单旋律）音符序列，转换为 C 语言头文件，
  包含类似 `static const Note_t melody[] = { ... };` 的数据结构，便于在
  STM32 等微控制器上用蜂鸣器播放。
- 时间单位采用毫秒（ms）并把间隔（休止）用 freq==0 标记为休止符。
- 当同一时刻出现多个同时发声（和弦）时，脚本只选取“最响（velocity 最大）”
  的音符作为单声道输出，这是为了适配只能播放单音的蜂鸣器。
"""
import sys
import math
from collections import defaultdict

try:
    import mido
except ImportError:
    print("Missing dependency 'mido'. Install with: python -m pip install mido")
    sys.exit(2)


def note_to_freq(n):
    """
    将 MIDI 音符号（数字）转换为频率（Hz）。

    参数：
    - n (int): MIDI 音符编号（例如 69 表示 A4，即 440Hz）。

    返回：
    - int: 四舍五入后的频率（Hz）。

    说明：
    - 公式：440 * 2^((n - 69) / 12)，每个半音频率乘以 2 的 1/12 次方。
    - 返回整数是为了方便在微控制器上直接用整数频率控制定时。
    """
    return int(round(440.0 * (2 ** ((n - 69) / 12.0))))


def ticks_to_ms(ticks, tempo, ticks_per_beat):
    """
    将 MIDI ticks（节拍单位的时间）转换为毫秒（ms）。

    参数：
    - ticks (int): MIDI 的 ticks 数量（通常来自事件时间差）。
    - tempo (int or None): 每拍持续的微秒数（microseconds per beat），
      由 MIDI 的 set_tempo 事件指定。若为 None，则使用默认值 500000（120 BPM）。
    - ticks_per_beat (int): MIDI 文件头定义的每拍 ticks 数。

    返回：
    - int: 对应的毫秒数（四舍五入）。

    解释：
    - 先用 ticks * tempo / ticks_per_beat 得到微秒数，再除以 1000 得到毫秒。
    """
    if tempo is None:
        tempo = 500000  # 默认 120 BPM
    micros = (ticks * tempo) / ticks_per_beat
    return int(round(micros / 1000.0))


def extract_monophonic(mid):
    """
    从 MIDI 文件中提取单声道（单旋律）音符事件序列，返回每个音符的起止 tick。

    处理步骤（面向初学者）：
    1. 把所有轨道的事件合并，并按绝对时间（ticks）排序，这样可以按照时间顺序处理事件。
    2. 遇到 note_on（velocity>0）时记录该音符的起始 tick 和速度（velocity）；
       遇到 note_off 或 note_on（velocity==0）时记录结束 tick 并把该音符加入结果。
    3. 如果多个音符在同一 tick 同时开始（和弦），按优先级选择一个音符保留：
       先按 velocity（响度）比较，若相等再选择音高更高者。这样可以把多音转换为单音，
       便于蜂鸣器播放。

    返回：
    - output: 列表 (note_number, start_tick, end_tick)
    - tempo: 最后看到的 tempo（microseconds per beat）值，用于时间转换
    - ticks_per_beat: MIDI 文件头中的 ticks_per_beat
    """
    # 1) 合并所有轨道的消息并计算绝对 tick 时间
    ticks_per_beat = mid.ticks_per_beat
    tempo = 500000
    events = []  # (abs_ticks, msg)
    for i, track in enumerate(mid.tracks):
        abs_ticks = 0
        for msg in track:
            abs_ticks += msg.time
            events.append((abs_ticks, msg))
    events.sort(key=lambda x: x[0])

    # 2) 记录处于按下状态的音符（active），并收集已经完成的 note 事件
    active = {}  # note -> (on_tick, velocity)
    results = []  # will hold (note, start_tick, end_tick, velocity)

    for abs_tick, msg in events:
        # 处理 tempo 变化，供后续 ticks->时间 转换使用
        if msg.type == 'set_tempo':
            tempo = msg.tempo
        # note_on 且 velocity>0 -> 开始音符
        if msg.type == 'note_on' and msg.velocity > 0:
            active[msg.note] = (abs_tick, msg.velocity)
        # note_off 或 note_on 且 velocity==0 -> 结束音符
        elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
            if msg.note in active:
                start_tick, vel = active.pop(msg.note)
                results.append((msg.note, start_tick, abs_tick, vel))

    # 3) 按起始时间分组，同时开始的（和弦）只保留一个音符
    results.sort(key=lambda x: x[1])

    by_start = {}
    for note, s, e, vel in results:
        by_start.setdefault(s, []).append((note, s, e, vel))

    timeline = []
    for s in sorted(by_start.keys()):
        group = by_start[s]
        # 选择 velocity 最大的音符；若 velocity 相同则选择音高更高的音符
        chosen = max(group, key=lambda x: (x[3], x[0]))
        timeline.append(chosen)

    timeline.sort(key=lambda x: x[1])  # 确保时间顺序

    # 输出格式转换为 (note, start_tick, end_tick)
    output = [(note, s, e) for (note, s, e, vel) in timeline]

    return output, tempo, ticks_per_beat


def build_note_array(events, tempo, ticks_per_beat):
    """
    把提取到的事件（以 ticks 表示）转换为 (频率, 毫秒) 的列表，方便生成 C 头文件。

    - events: 列表 (note_number, start_tick, end_tick)
    - tempo, ticks_per_beat: 用于 ticks -> ms 的转换

    行为说明：
    - 如果某个音符开始时间 s 大于当前时间 current_tick，则说明当前存在间隔，
      把间隔时间转换为休止（freq=0，duration=间隔毫秒数）。
    - 然后把实际音符的持续时间与对应频率加入输出。
    """
    notes = []
    if not events:
        return notes
    current_tick = events[0][1]
    for note, s, e in events:
        # 如果出现空白间隔，插入休止（freq==0）
        if s > current_tick:
            rest_ms = ticks_to_ms(s - current_tick, tempo, ticks_per_beat)
            if rest_ms > 0:
                notes.append((0, rest_ms))
        # 计算音符持续时间并转换为频率
        dur_ms = ticks_to_ms(e - s, tempo, ticks_per_beat)
        freq = note_to_freq(note)
        notes.append((freq, dur_ms))
        current_tick = e
    return notes


def emit_c_header(notes, out_path):
    """
    将 notes 写入 C 头文件，生成一个 `static const Note_t melody[]` 数组。

    注意点：
    - 使用 `freq==0` 表示休止（rest）。
    - 为避免生成负或 0 时长的条目，会跳过持续时间 <= 0 的项。
    - 生成的头文件包含头保护（#ifndef/#define）和 `melody_len` 计数变量，便于 C 端使用。
    """
    print(f"[emit_c_header] Writing header to: {out_path}", flush=True)
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("/* Auto-generated by tools/midi_to_buzzer.py */\n")
            f.write("#ifndef BADAPPLE_MELODY_H\n")
            f.write("#define BADAPPLE_MELODY_H\n\n")
            f.write("#include \"main.h\"\n\n")
            f.write("typedef struct {\n    uint16_t freq;\n    uint16_t duration;\n} Note_t;\n\n")

            f.write("static const Note_t melody[] = {\n")
            for freq, dur in notes:
                if dur <= 0:
                    continue
                if freq == 0:
                    # 休止
                    f.write(f"  {{0, {dur}}},\n")
                else:
                    f.write(f"  {{{freq}, {dur}}},\n")
            f.write("};\n\n")
            f.write("static const size_t melody_len = sizeof(melody)/sizeof(melody[0]);\n\n")
            f.write("#endif /* BADAPPLE_MELODY_H */\n")
        print(f"[emit_c_header] Wrote {out_path} with {len(notes)} events", flush=True)
    except Exception as ex:
        # 输出异常信息（对初学者有帮助）
        print(f"[emit_c_header] ERROR writing header: {ex}", flush=True)    


def simplify_notes(notes, quarter_ms, denom=8, min_ms=80, max_notes=400):
    """
    将音符列表简化为适合蜂鸣器播放的版本（为初学者详细解释）：

    处理步骤：
    1. 合并相邻且频率相同的音符（它们会被当成一个更长的音符）。
    2. 将每个音符的时长量化到最近的单位：unit = quarter_ms / denom。举例：
       如果 quarter_ms==500, denom==8，则 unit==62.5 ms。
    3. 如果量化后的时长小于 min_ms，则把该时间并入前一个音符（如果没有前一个，则转成休止）。
    4. 如果音符数量超过 max_notes，会把尾部时间合并到最后一个保留的条目中，以限制总长度。

    参数及含义：
    - notes: 列表 (freq, duration_ms)
    - quarter_ms: 四分之一拍对应的毫秒数（由 tempo 决定）
    - denom: 量化分母（更大表示更细的时间网格）
    - min_ms: 最小保留时间，过短的时间会被合并
    - max_notes: 输出的最大音符数量

    返回：
    - 简化并量化后的列表 (freq, duration_ms)
    """
    if not notes:
        return []
    unit = quarter_ms / denom

    # 合并相邻相同频率的音符
    merged = []
    for f, d in notes:
        if merged and merged[-1][0] == f:
            merged[-1] = (f, merged[-1][1] + d)
        else:
            merged.append((f, d))

    # 量化时长并删除过短音符（把时间并入前一个条目）
    quant = []
    for f, d in merged:
        q = int(round(d / unit))
        if q <= 0:
            q = 1
        d2 = int(q * unit)
        if d2 < min_ms:
            if quant:
                quant[-1] = (quant[-1][0], quant[-1][1] + d2)
            else:
                quant.append((0, d2))  # 转成休止
        else:
            quant.append((f, d2))

    # 限制最大条目数，如果超出则合并尾部
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


def main():
    # 命令行参数说明：
    #   python tools/midi_to_buzzer.py <midi-file> <out-h-header> [--simplify] [--denom=N] [--min-ms=N] [--max-notes=N] [--monophonic]
    if len(sys.argv) < 3:
        print("用法: python tools/midi_to_buzzer.py <midi-file> <out-h-header>")
        sys.exit(1)
    mid_path = sys.argv[1]
    out_header = sys.argv[2]

    print(f"[main] Opening MIDI: {mid_path}", flush=True)
    try:
        mid = mido.MidiFile(mid_path)
    except Exception as ex:
        print(f"[main] 打开 MIDI 文件出错: {ex}", flush=True)
        sys.exit(2)
    print(f"[main] MIDI 加载完成: tracks={len(mid.tracks)}, ticks_per_beat={mid.ticks_per_beat}", flush=True)

    # 提取单声道事件并转换为 (note, start, end)
    events, tempo, tpb = extract_monophonic(mid)
    print(f"[main] 提取到事件数量: {len(events)}, tempo={tempo}, tpb={tpb}", flush=True)
    notes = build_note_array([(n, s, e) for (n, s, e) in events], tempo, tpb)
    print(f"[main] 构建的音符列表长度: {len(notes)}", flush=True)

    # 可选的简化参数
    simplify = False
    denom = 8
    min_ms = 80
    max_notes = 400
    monophonic = False
    for a in sys.argv[3:]:
        if a.startswith('--simplify'):
            simplify = True
        if a.startswith('--denom='):
            try:
                denom = int(a.split('=',1)[1])
            except:
                pass
        if a.startswith('--min-ms='):
            try:
                min_ms = int(a.split('=',1)[1])
            except:
                pass
        if a.startswith('--max-notes='):
            try:
                max_notes = int(a.split('=',1)[1])
            except:
                pass
        if a.startswith('--monophonic') or a.startswith('--preserve-length'):
            monophonic = True

    # 根据参数选择输出：保留单声道、简化或直接输出原始音符
    if monophonic:
        mono_out = out_header.replace('.h', '_mono.h')
        emit_c_header(notes, mono_out)
        print(f"[main] 已写入单声道头文件: {mono_out} (events: {len(notes)})", flush=True)
    elif simplify:
        # 计算四分之一拍的毫秒数用于量化
        quarter_ms = tempo / 1000.0
        simple_notes = simplify_notes(notes, quarter_ms, denom=denom, min_ms=min_ms, max_notes=max_notes)
        simple_out = out_header.replace('.h', '_simple.h')
        emit_c_header(simple_notes, simple_out)
        print(f"[main] 已写入简化头文件: {simple_out} (原始 {len(notes)} -> 简化 {len(simple_notes)})", flush=True)
    else:
        emit_c_header(notes, out_header)


if __name__ == '__main__':
    main()
