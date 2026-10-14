// Implements: include/ninfer/ops/speculative_round.h
// Match: validated speculative state and BF16 verification logits.
// Algorithm assumptions: the shared sampling layout selects either one block
// or a two-launch partial/group pipeline without host reads of device config.
#include "ops/launcher/speculative_round.h"

#include "ops/common/math.h"
#include "ops/kernel/speculative_round.cuh"
#include "core/device.h"
#include "core/pdl.cuh"

#include <algorithm>
#include <cstdint>

namespace ninfer::ops::detail {

void speculative_prepare_verify_inputs_launch(const Tensor& anchors, const Tensor& drafts,
                                              const Tensor& base_positions,
                                              const Tensor& current_extents, Tensor& verify_ids,
                                              Tensor& positions, cudaStream_t stream) {
    constexpr int kBlock = 32;
    const int k          = drafts.ne[0];
    const int batch      = drafts.ne[1];
    const dim3 grid(static_cast<unsigned int>(div_up(k + 1, kBlock)),
                    static_cast<unsigned int>(batch));
    CUDA_CHECK(pdl::launch_consumer({dim3(grid), dim3(kBlock), 0, stream},
                                    speculative_prepare_verify_inputs_kernel,
                                    static_cast<const std::int32_t*>(anchors.data),
                                    static_cast<const std::int32_t*>(drafts.data),
                                    static_cast<const std::int32_t*>(base_positions.data),
                                    static_cast<const std::int32_t*>(current_extents.data),
                                    static_cast<std::int32_t*>(verify_ids.data),
                                    static_cast<std::int32_t*>(positions.data), k));
    CUDA_CHECK(cudaGetLastError());
}

void speculative_prepare_verify_ids_launch(const Tensor& anchors, const Tensor& drafts,
                                           const Tensor& current_extents, Tensor& verify_ids,
                                           cudaStream_t stream) {
    constexpr int kBlock = 32;
    const int k          = drafts.ne[0];
    const int batch      = drafts.ne[1];
    const dim3 grid(static_cast<unsigned int>(div_up(k + 1, kBlock)),
                    static_cast<unsigned int>(batch));
    CUDA_CHECK(pdl::launch_consumer({dim3(grid), dim3(kBlock), 0, stream},
                                    speculative_prepare_verify_inputs_kernel,
                                    static_cast<const std::int32_t*>(anchors.data),
                                    static_cast<const std::int32_t*>(drafts.data), nullptr,
                                    static_cast<const std::int32_t*>(current_extents.data),
                                    static_cast<std::int32_t*>(verify_ids.data), nullptr, k));
    CUDA_CHECK(cudaGetLastError());
}

void speculative_overlay_copy_proposals_launch(const Tensor& copy_rows, const Tensor& copy_drafts,
                                               const Tensor& copy_candidates, const Tensor& copy_q,
                                               Tensor& drafts, Tensor& candidates,
                                               Tensor& proposal_q, cudaStream_t stream) {
    constexpr int kBlock = 128;
    const int k          = drafts.ne[0];
    const int batch      = drafts.ne[1];
    CUDA_CHECK(pdl::launch_consumer(
        {dim3(batch), dim3(kBlock), 0, stream}, speculative_overlay_copy_proposals_kernel,
        static_cast<const std::int32_t*>(copy_rows.data),
        static_cast<const std::int32_t*>(copy_drafts.data),
        static_cast<const std::int32_t*>(copy_candidates.data),
        static_cast<const float*>(copy_q.data), static_cast<std::int32_t*>(drafts.data),
        static_cast<std::int32_t*>(candidates.data), static_cast<float*>(proposal_q.data), k,
        kSparseSpeculativeCandidates));
    CUDA_CHECK(cudaGetLastError());
}

void speculative_accept_greedy_drafts_launch(const Tensor& target_tokens, const Tensor& logits,
                                             const Tensor& drafts, const Tensor& current_extents,
                                             Tensor& lengths, Tensor& anchors,
                                             Tensor& licensed_tokens, Tensor& licensed_counts,
                                             Tensor& accepted, std::int32_t token_domain,
                                             const SamplingConfig* configs, DeviceSpan workspace,
                                             cudaStream_t stream) {
    const std::int32_t physical_rows = logits.ne[0];
    const std::int32_t cols          = drafts.ne[0] + 1;
    const std::int32_t batch         = drafts.ne[1];
    const SamplingWorkspaceLayout layout =
        make_sampling_workspace_layout(token_domain, cols, kSpeculativeSamplerMaxColumns);
    if (!layout.multiblock) {
        speculative_accept_greedy_drafts_kernel<<<batch, kSamplerBlock, 0, stream>>>(
            static_cast<const std::int32_t*>(target_tokens.data),
            static_cast<const __nv_bfloat16*>(logits.data),
            static_cast<const std::int32_t*>(drafts.data),
            static_cast<const std::int32_t*>(current_extents.data),
            static_cast<std::int32_t*>(lengths.data), static_cast<std::int32_t*>(anchors.data),
            static_cast<std::int32_t*>(licensed_tokens.data),
            static_cast<std::int32_t*>(licensed_counts.data),
            static_cast<std::int32_t*>(accepted.data), configs, token_domain, physical_rows,
            drafts.ne[0]);
        CUDA_CHECK(cudaGetLastError());
        return;
    }
    const std::int32_t partial_blocks = div_up(token_domain, kSamplerPartialTileItems);
    const std::int32_t groups         = sampler_group_count(partial_blocks);
    const SamplingWorkspace scratch   = layout.bind(workspace);
    const dim3 partial_grid(static_cast<unsigned int>(partial_blocks),
                            static_cast<unsigned int>(cols), static_cast<unsigned int>(batch));
    CUDA_CHECK(pdl::launch_consumer(
        {dim3(partial_grid), dim3(kSamplerBlock), 0, stream},
        speculative_sampling_partial_topk_kernel, static_cast<const __nv_bfloat16*>(logits.data),
        static_cast<const std::int32_t*>(drafts.data),
        static_cast<const std::int32_t*>(current_extents.data), configs, token_domain,
        physical_rows, cols, drafts.ne[0], scratch, layout.bytes));
    CUDA_CHECK(cudaGetLastError());
    const dim3 batched_group_grid(static_cast<unsigned int>(groups),
                                  static_cast<unsigned int>(cols),
                                  static_cast<unsigned int>(batch));
    CUDA_CHECK(pdl::launch_consumer(
        {dim3(batched_group_grid), dim3(kSamplerGroupBlock), 0, stream},
        speculative_sampling_group_finalize_kernel<false>,
        static_cast<const std::int32_t*>(target_tokens.data),
        static_cast<const __nv_bfloat16*>(logits.data),
        static_cast<const std::int32_t*>(drafts.data), nullptr, nullptr,
        static_cast<const std::int32_t*>(current_extents.data),
        static_cast<std::int32_t*>(lengths.data), static_cast<std::int32_t*>(anchors.data),
        static_cast<std::int32_t*>(licensed_tokens.data),
        static_cast<std::int32_t*>(licensed_counts.data), static_cast<std::int32_t*>(accepted.data),
        configs, token_domain, cols, partial_blocks, groups, physical_rows, scratch, layout.bytes));
    CUDA_CHECK(cudaGetLastError());
}

void speculative_accept_sparse_drafts_launch(
    const Tensor& target_tokens, const Tensor& logits, const Tensor& drafts,
    const Tensor& candidate_ids, const Tensor& proposal_q, const Tensor& current_extents,
    Tensor& round_lengths, Tensor& round_anchors, Tensor& licensed_tokens, Tensor& licensed_counts,
    Tensor& accepted_drafts, std::int32_t token_domain, const SamplingConfig* configs,
    bool raw_greedy, DeviceSpan workspace, cudaStream_t stream) {
    const std::int32_t batch         = drafts.ne[1];
    const std::int32_t k             = drafts.ne[0];
    const std::int32_t cols          = k + 1;
    const std::int32_t physical_rows = logits.ne[0];
    if (raw_greedy) {
        speculative_accept_sparse_warp_greedy_kernel<<<1, 32 * batch, 0, stream>>>(
            static_cast<const int*>(target_tokens.data),
            static_cast<const __nv_bfloat16*>(logits.data), static_cast<const int*>(drafts.data),
            static_cast<const int*>(current_extents.data), static_cast<int*>(round_lengths.data),
            static_cast<int*>(round_anchors.data), static_cast<int*>(licensed_tokens.data),
            static_cast<int*>(licensed_counts.data), static_cast<int*>(accepted_drafts.data), k,
            physical_rows);
        CUDA_CHECK(cudaGetLastError());
        return;
    }

    const SamplingWorkspaceLayout layout =
        make_sampling_workspace_layout(token_domain, cols, kSpeculativeSamplerMaxColumns);
    const std::int32_t partial_blocks = div_up(token_domain, kSamplerPartialTileItems);
    const std::int32_t groups         = sampler_group_count(partial_blocks);
    const SamplingWorkspace scratch   = layout.bind(workspace);
    const dim3 partial_grid(static_cast<unsigned int>(partial_blocks),
                            static_cast<unsigned int>(cols), static_cast<unsigned int>(batch));
    CUDA_CHECK(pdl::launch_consumer({dim3(partial_grid), dim3(kSamplerBlock), 0, stream},
                                    speculative_sampling_partial_topk_kernel,
                                    static_cast<const __nv_bfloat16*>(logits.data),
                                    static_cast<const std::int32_t*>(drafts.data),
                                    static_cast<const std::int32_t*>(current_extents.data), configs,
                                    token_domain, logits.ne[0], cols, k, scratch, layout.bytes));
    CUDA_CHECK(cudaGetLastError());

    const dim3 group_grid(static_cast<unsigned int>(groups), static_cast<unsigned int>(cols),
                          static_cast<unsigned int>(batch));

    CUDA_CHECK(pdl::launch_consumer({dim3(group_grid), dim3(kSamplerGroupBlock), 0, stream},
                                    speculative_sampling_group_finalize_kernel<true>,
                                    static_cast<const std::int32_t*>(target_tokens.data),
                                    static_cast<const __nv_bfloat16*>(logits.data),
                                    static_cast<const std::int32_t*>(drafts.data),
                                    static_cast<const std::int32_t*>(candidate_ids.data),
                                    static_cast<const float*>(proposal_q.data),
                                    static_cast<const std::int32_t*>(current_extents.data),
                                    static_cast<std::int32_t*>(round_lengths.data),
                                    static_cast<std::int32_t*>(round_anchors.data),
                                    static_cast<std::int32_t*>(licensed_tokens.data),
                                    static_cast<std::int32_t*>(licensed_counts.data),
                                    static_cast<std::int32_t*>(accepted_drafts.data), configs,
                                    token_domain, cols, partial_blocks, groups, physical_rows,
                                    scratch, layout.bytes));

    CUDA_CHECK(cudaGetLastError());
}

void speculative_select_accepted_hidden_launch(const Tensor& hidden, const Tensor& selectors,
                                               Tensor& out, cudaStream_t stream) {
    constexpr int kBlock = 256;
    const int rows       = hidden.ne[0];
    const int batch      = hidden.ne[2];
    const dim3 grid(static_cast<unsigned int>(std::max(1, div_up(rows, kBlock))),
                    static_cast<unsigned int>(batch));
    CUDA_CHECK(pdl::launch_consumer({dim3(grid), dim3(kBlock), 0, stream},
                                    speculative_select_accepted_hidden_kernel,
                                    static_cast<const __nv_bfloat16*>(hidden.data),
                                    static_cast<const std::int32_t*>(selectors.data),
                                    static_cast<__nv_bfloat16*>(out.data), rows, hidden.ne[1]));
    CUDA_CHECK(cudaGetLastError());
}

void proposal_remap_token_ids_launch(Tensor& proposal_tokens, const std::int32_t* id_map,
                                     std::int32_t n, cudaStream_t stream) {
    constexpr int kBlock = 256;
    const int count      = proposal_tokens.ne[0];
    const int grid       = std::max(1, div_up(count, kBlock));
    proposal_remap_token_ids_kernel<<<grid, kBlock, 0, stream>>>(
        static_cast<std::int32_t*>(proposal_tokens.data), count, id_map, n);
    CUDA_CHECK(cudaGetLastError());
}

} // namespace ninfer::ops::detail


// ---- I3b S6: device-side %globaltimer stamps (see step_graph_profile.h) ----
#include "models/qwen3_5/program/speculative/step_graph_profile.h"

#include <cstdio>
#include <cstdlib>

namespace ninfer::models::qwen3_5::execution {
namespace {
unsigned long long* g_stamp_host = nullptr;  // mapped host view (zero-copy readback)
unsigned long long* g_stamp_dev = nullptr;   // device view written by the stamp kernel
int g_stamp_ref_prints = 0;
int g_stamp_slow_prints = 0;

__global__ void step_stamp_kernel(unsigned long long* out, int slot) {
    if (threadIdx.x == 0 && blockIdx.x == 0) {
        unsigned long long t = 0ULL;
        asm volatile("mov.u64 %0, %%globaltimer;" : "=l"(t));
        out[slot] = t;
    }
}
}  // namespace

bool step_stamp_arm() {
    if (g_stamp_host != nullptr) { return true; }
    void* host = nullptr;
    if (cudaHostAlloc(&host, sizeof(unsigned long long) * 8, cudaHostAllocMapped) != cudaSuccess) {
        (void)cudaGetLastError();
        return false;
    }
    void* dev = nullptr;
    if (cudaHostGetDevicePointer(&dev, host, 0) != cudaSuccess) {
        (void)cudaGetLastError();
        (void)cudaFreeHost(host);
        return false;
    }
    g_stamp_host = static_cast<unsigned long long*>(host);
    g_stamp_dev = static_cast<unsigned long long*>(dev);
    for (int i = 0; i < 8; ++i) { g_stamp_host[i] = 0ULL; }
    std::fprintf(stderr, "[ninfer] spin-stamp DEBUG: armed (mapped host buffer, 8 slots)\n");
    return true;
}

void step_stamp_launch(int slot, cudaStream_t stream) {
    if (g_stamp_dev == nullptr || slot < 0 || slot > 7) { return; }  // S7/E2: 8 槽（5/6 = target 子界）
    step_stamp_kernel<<<1, 1, 0, stream>>>(g_stamp_dev, slot);
}

void step_stamp_report(const char* tag) {
    if (g_stamp_host == nullptr) { return; }
    const unsigned long long t0 = g_stamp_host[0], t1 = g_stamp_host[1], t2 = g_stamp_host[2];
    const unsigned long long t3 = g_stamp_host[3], t4 = g_stamp_host[4];
    const unsigned long long t5 = g_stamp_host[5], t6 = g_stamp_host[6];  // S7/E2: target 子界
    if (t0 == 0ULL || t4 == 0ULL || t4 <= t0) { return; }
    const double total_ms = static_cast<double>(t4 - t0) / 1e6;
    const bool verbose = std::getenv("NINFER_SPIN_STAMP_VERBOSE") != nullptr;
    if (!verbose) {
        if (total_ms > 100.0) {
            if (g_stamp_slow_prints >= 60) { return; }
            ++g_stamp_slow_prints;
        } else {
            if (g_stamp_ref_prints >= 3) { return; }
            ++g_stamp_ref_prints;
        }
    }
    const double d0 = static_cast<double>(t1 - t0) / 1e6;
    const double d1 = static_cast<double>(t2 - t1) / 1e6;
    const double d2 = static_cast<double>(t3 - t2) / 1e6;
    const double d3 = static_cast<double>(t4 - t3) / 1e6;
    std::fprintf(stderr,
                 "[ninfer] spin-stamp %s: ingress=%.1f target=%.1f draft=%.1f egress=%.1f ms | total=%.1f ms\n",
                 tag ? tag : "round", d0, d1, d2, d3, total_ms);
    if (t5 != 0ULL && t6 != 0ULL && t5 >= t1 && t6 >= t5 && t2 >= t6) {
        const double s_setup   = static_cast<double>(t5 - t1) / 1e6;  // card 装配 + 张量视图
        const double s_prepare = static_cast<double>(t6 - t5) / 1e6;  // prepare_verify_inputs
        const double s_verify  = static_cast<double>(t2 - t6) / 1e6;  // target_verify_accept
        std::fprintf(stderr,
                     "[ninfer] target-split %s: setup=%.2f prepare=%.2f verify=%.2f ms | sum=%.2f (target=%.1f)\n",
                     tag ? tag : "round", s_setup, s_prepare, s_verify,
                     s_setup + s_prepare + s_verify, d1);
    }
    std::fflush(stderr);
}
}  // namespace ninfer::models::qwen3_5::execution
