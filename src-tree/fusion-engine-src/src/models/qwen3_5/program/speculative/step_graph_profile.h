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

} // namespace ninfer::models::qwen3_5::execution
