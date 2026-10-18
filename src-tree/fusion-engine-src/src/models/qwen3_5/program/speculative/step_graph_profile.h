#pragma once

// I3b S3b（2026-10-14）：MTP 图体内事件计时接口。门槛 = NINFER_STEP_PROFILE（默认关、零行为）。
//   step_graph_arm()            ：建图前创建 5 个事件（必须早于 capture，事件记录才可被捕获）
//   step_graph_record(slot, s)  ：在（被捕获的）图体内调用 —— capture 期成为 event-record 节点，
//                                 eager 期则是真实记录；slot 0..4 = 起点/ingress 后/target 后/
//                                 draft 后/egress 后（4 区间：ingress / target / draft / egress）
//   step_graph_harvest(out[4])  ：device.synchronize() 之后调用，读回 4 区间毫秒；不可用返回 false
#include <cuda_runtime.h>

namespace ninfer::models::qwen3_5::execution {

bool step_graph_enabled();
void step_graph_arm();
void step_graph_record(int slot, cudaStream_t stream);
bool step_graph_harvest(double out_ms[4]);

// I3b S6（2026-10-14 午后）：设备侧 %%globaltimer 打点——替代不可用的图内事件计时（step5 已判不可用）。
//   门槛 = NINFER_STEP_PROFILE（与事件计时同门，默认关、零行为）；record 改为 launch 一枚 1-thread
//   stamp kernel ⇒ capture 期成为 kernel 节点（合法），replay 期按图序写纳秒时间戳到 mapped host buffer。
//   step_stamp_arm()            ：建 mapped 缓冲（幂等；必须早于 capture）
//   step_stamp_launch(slot, s)  ：S7/E2 起 8 槽：0..4 与事件计时同口径；5 = target 段"装配后/prepare 前"；6 = "prepare 后/verify 前"；7/8/9 = verify 内部（前向/接受/选择）；报告新增 verify-split 行（forward / accept / select / scatter）
//   step_stamp_report(tag)      ：sync 后调用；慢轮（总跨度>100ms）或前 3 轮/VERBOSE 时打印一行
bool step_stamp_arm();
void step_stamp_launch(int slot, cudaStream_t stream);
void step_stamp_report(const char* tag);
// v4.5：四个被采样层的真实层号走主机侧（内核只写 %globaltimer）；由 report 打印
void step_stamp_note_sample_layers(int l0, int l1, int l2, int l3);

} // namespace ninfer::models::qwen3_5::execution
