#include "ninfer/ops/speculative_round.h"
#include "models/qwen3_5/program/graph_execution.h"
#include "models/qwen3_5/program/internal.h"
#include "models/qwen3_5/program/context.h"
#include "core/nvtx.h"
#include "ninfer/ops/mtp_round.h"
#include "ninfer/ops/scatter.h"
#include "ninfer/ops/scalar.h"
#include "models/qwen3_5/program/speculative/step_graph_profile.h"

#include <cstdlib>
#include <cuda_runtime.h>
#include <stdexcept>

namespace ninfer::models::qwen3_5::execution {

// ---- I3b S3b（2026-10-14）：MTP 图体内事件计时（NINFER_STEP_PROFILE 门下；默认关）------------
// 5 事件 -> 4 区间：ingress / target / draft / egress。arm 在建图前创建，record 在（被捕获的）
// 图体内成为 event-record 节点（eager 期即真实记录），replay 后由 harvest 读回。
namespace {
cudaEvent_t g_step_graph_events[5] = {nullptr, nullptr, nullptr, nullptr, nullptr};
} // namespace

bool step_graph_enabled() {
    static const bool enabled = [] {
        const char* text = std::getenv("NINFER_STEP_PROFILE");
        return text != nullptr && text[0] != '\0' && std::strtol(text, nullptr, 10) > 0;
    }();
    return enabled;
}

void step_graph_arm() {
    if (!step_graph_enabled()) { return; }
    for (int i = 0; i < 5; ++i) {
        if (g_step_graph_events[i] == nullptr) {
            if (cudaEventCreate(&g_step_graph_events[i]) != cudaSuccess) {
                g_step_graph_events[i] = nullptr;
            }
        }
    }
}

void step_graph_record(int slot, cudaStream_t stream) {
    if (!step_graph_enabled() || slot < 0 || slot >= 5) { return; }
    if (g_step_graph_events[slot] == nullptr) { return; }
    (void)cudaEventRecord(g_step_graph_events[slot], stream);
}

bool step_graph_harvest(double out_ms[4]) {
    if (!step_graph_enabled()) { return false; }
    for (int i = 0; i < 5; ++i) {
        if (g_step_graph_events[i] == nullptr) { return false; }
    }
    float ms = 0.0f;
    for (int i = 0; i < 4; ++i) {
        if (cudaEventElapsedTime(&ms, g_step_graph_events[i], g_step_graph_events[i + 1]) !=
            cudaSuccess) {
            // 2026-10-14 修复：未记录过的事件会让 cudaEventElapsedTime 置 sticky last-error，
            // 后续任何 CUDA_CHECK(cudaGetLastError()) 会捡到它并 abort（warmup recurrent.cu 实测）。
            (void)cudaGetLastError();
            return false;
        }
        out_ms[i] = static_cast<double>(ms);
    }
    return true;
}

void mtp_bridge_and_propose(PrefillContext& state, const Tensor& next_token,
                            const Tensor& previous_hidden, std::int32_t position,
                            std::span<const std::int32_t> rope_position, bool build_proposal,
                            const Tensor* next_embedding) {
    if (!state.mtp_kv.valid() || !state.execution.io.mtp) {
        throw std::logic_error("MTP bridge requires MTP storage");
    }
    if (rope_position.size() != 3) {
        throw std::invalid_argument("MTP bridge requires one three-axis rope position");
    }
    state.execution.work.reset();
    TextContext card(state.execution.device, state.execution.parameters, state.execution.work,
                     state.text_kv, state.execution.linear_attention, state.execution.io,
                     state.execution.prefill_hidden, state.execution.prefill_chunk,
                     state.text_kv_base, state.mtp_kv, &state.text_cache, state.mtp_cache);
    card.set_stage_runtime(state.execution.stages);
    card.set_rope_yarn(state.execution.rope_yarn);
    card.set_mtp_attention_window(state.execution.mtp_attention_window);
    configure_text_card(card, state.execution, state.sampling, state.state_source_slot,
                        state.state_destination_slot, state.mtp_proposal_extent);

    Tensor position_view = state.execution.io.mtp->target_positions.slice(0, 0, 1);
    ops::set_i32_scalar(position_view, position, state.execution.device.stream);
    Tensor mtp_hidden         = state.execution.io.mtp->ar_hidden;
    Tensor logits             = state.execution.io.logits.slice(1, 0, 1);
    Tensor draft0             = state.execution.io.mtp->draft_tokens.slice(0, 0, 1);
    Tensor rope_position_view = state.execution.work.alloc(DType::I32, {1, 3});
    CUDA_CHECK(cudaMemcpyAsync(rope_position_view.data, rope_position.data(),
                               rope_position.size_bytes(), cudaMemcpyHostToDevice,
                               state.execution.device.stream));
    const auto bridge_visible = static_cast<std::uint32_t>(position + 1);
    const ops::CausalAttentionExecutionEnvelope bridge_envelope{bridge_visible, bridge_visible};
    card.mtp_forward_batch(next_token, previous_hidden, position_view, bridge_envelope, mtp_hidden,
                           build_proposal ? 0 : -1, build_proposal ? &logits : nullptr,
                           build_proposal ? &draft0 : nullptr, &rope_position_view, next_embedding);
    if (!build_proposal) { return; }

    if (state.mtp_proposal_extent == 0 ||
        state.mtp_proposal_extent >
            static_cast<std::uint32_t>(state.execution.io.mtp->draft_tokens.ne[0])) {
        throw std::logic_error("MTP bridge proposal extent is outside the configured window");
    }

    Tensor ar_position = state.execution.io.mtp->position.slice(0, 0, 1);
    ops::set_i32_scalar(ar_position, position + 1, state.execution.device.stream);
    for (int i = 1; i < static_cast<int>(state.mtp_proposal_extent); ++i) {
        Tensor previous_token = state.execution.io.mtp->draft_tokens.slice(0, i - 1, 1);
        Tensor next_draft     = state.execution.io.mtp->draft_tokens.slice(0, i, 1);
        Tensor next_hidden    = state.execution.prefill_hidden.slice(1, i, 1);
        const auto visible    = static_cast<std::uint32_t>(position + i + 1);
        const ops::CausalAttentionExecutionEnvelope envelope{visible, visible};
        card.mtp_forward_ar_step(previous_token, state.execution.io.mtp->ar_hidden, ar_position,
                                 envelope, next_hidden, logits, next_draft);
        CUDA_CHECK(cudaMemcpyAsync(state.execution.io.mtp->ar_hidden.data, next_hidden.data,
                                   state.execution.io.mtp->ar_hidden.bytes(),
                                   cudaMemcpyDeviceToDevice, state.execution.device.stream));
        ops::increment_i32_scalar(ar_position, state.execution.device.stream);
    }
}

auto mtp_decode_batch_body(MtpBatchContext& state, std::int32_t batch_size,
                           std::uint32_t verify_window, std::uint32_t draft_window,
                           MtpCausalAttentionEnvelopes envelopes) {
    return [&state, batch_size, verify_window, draft_window, envelopes] {
        if (batch_size <= 0 || batch_size > static_cast<std::int32_t>(kMaximumConcurrency) ||
            verify_window == 0 || verify_window > kMtpVerifyMaximumDrafts || draft_window == 0 ||
            draft_window > kMtpDecodeMaximumDrafts ||
            state.frame.current_drafts.ne[0] != static_cast<std::int32_t>(verify_window)) {
            throw std::logic_error("MTP decode batch state is incomplete");
        }

        qwen3_5::MtpDecodeState& frame = state.frame;
        const std::int32_t width       = static_cast<std::int32_t>(verify_window) + 1;
        step_graph_record(0, state.execution.device.stream);
        CUDA_CHECK(cudaMemcpyAsync(frame.ingress.data, &state.host_ingress,
                                   sizeof(qwen3_5::MtpDecodeIngress), cudaMemcpyHostToDevice,
                                   state.execution.device.stream));
        step_graph_record(1, state.execution.device.stream);

        TextContext card(state.execution.device, state.execution.parameters, state.execution.work,
                         {}, state.execution.linear_attention, state.execution.io,
                         state.execution.prefill_hidden, state.execution.prefill_chunk, 0, {},
                         &state.text_cache, &state.mtp_cache);
        card.set_stage_runtime(state.execution.stages);
        card.set_rope_yarn(state.execution.rope_yarn);
        card.set_mtp_attention_window(state.execution.mtp_attention_window);
        Tensor anchors            = frame.anchors.slice(0, 0, batch_size);
        Tensor frontiers          = frame.base_frontiers.slice(0, 0, batch_size);
        Tensor budgets            = frame.remaining_budgets.slice(0, 0, batch_size);
        Tensor current_extents    = frame.current_extents.slice(0, 0, batch_size);
        Tensor target_valid       = frame.target_valid_columns.slice(0, 0, batch_size);
        Tensor current_drafts     = frame.current_drafts.slice(1, 0, batch_size);
        Tensor target_rope        = frame.target_rope_positions.slice(1, 0, batch_size);
        Tensor text_rows          = frame.text_kv_table_rows.slice(0, 0, batch_size);
        Tensor mtp_rows           = frame.mtp_kv_table_rows.slice(0, 0, batch_size);
        Tensor state_sources      = frame.state_source_slots.slice(0, 0, batch_size);
        Tensor state_destinations = frame.state_destination_slots.slice(0, 0, batch_size);
        Tensor rope_deltas        = frame.rope_deltas.slice(0, 0, batch_size);
        Tensor verify_ids         = frame.verify_ids.slice(1, 0, batch_size);
        Tensor target_positions   = frame.target_positions.slice(1, 0, batch_size);
        Tensor target_tokens      = frame.target_argmax.slice(1, 0, batch_size);
        Tensor target_logits      = frame.target_logits.slice(2, 0, batch_size);
        Tensor target_hidden      = frame.target_hidden.slice(2, 0, batch_size);
        Tensor selected_hidden    = frame.target_continuation_hidden.slice(1, 0, batch_size);
        Tensor licensed_tokens    = frame.licensed_tokens.slice(1, 0, batch_size);
        Tensor licensed_counts    = frame.licensed_counts.slice(0, 0, batch_size);
        Tensor accepted           = frame.accepted_drafts.slice(0, 0, batch_size);
        Tensor next_extents       = frame.next_extents.slice(0, 0, batch_size);
        Tensor alignment_ids      = frame.alignment_ids.slice(1, 0, batch_size);
        Tensor alignment_hidden   = frame.alignment_hidden.slice(2, 0, batch_size);
        Tensor ar_hidden          = frame.ar_hidden.slice(1, 0, batch_size);
        Tensor next_hidden        = frame.next_hidden.slice(1, 0, batch_size);
        Tensor ar_positions       = frame.ar_positions.slice(0, 0, batch_size);
        Tensor ar_rope_positions  = frame.ar_rope_positions.slice(0, 0, batch_size);
        Tensor ar_valid_columns   = frame.ar_valid_columns.slice(0, 0, batch_size);
        Tensor next_drafts        = frame.next_drafts.slice(0, 0, batch_size);

        ops::speculative_prepare_verify_inputs(anchors, current_drafts, frontiers, current_extents,
                                               verify_ids, target_positions,
                                               state.execution.device.stream);
        {
            nvtx::ScopedRange target_range(nvtx::Name::DecodeMtpTarget, nvtx::Category::Mtp,
                                           static_cast<std::uint64_t>(width) * batch_size);
            target_verify_accept(state.execution, state.continuation_hidden_store, card,
                                 TargetVerifyFrameView{
                                     .ids                     = verify_ids,
                                     .cache_positions         = target_positions,
                                     .rope_positions          = target_rope,
                                     .valid_columns           = target_valid,
                                     .kv_table_rows           = text_rows,
                                     .state_source_slots      = state_sources,
                                     .state_destination_slots = state_destinations,
                                     .target_hidden           = target_hidden,
                                     .target_logits           = target_logits,
                                     .target_tokens           = target_tokens,
                                     .drafts                  = current_drafts,
                                     .current_extents         = current_extents,
                                     .frontiers               = frontiers,
                                     .anchors                 = anchors,
                                     .licensed_tokens         = licensed_tokens,
                                     .licensed_counts         = licensed_counts,
                                     .accepted_drafts         = accepted,
                                     .selected_hidden         = selected_hidden,
                                     .replay_records          = state.execution.replay_records,
                                     .sampling                = frame.sampling,
                                 },
                                 envelopes.target_verify);
        }
        step_graph_record(2, state.execution.device.stream);

        {
            nvtx::ScopedRange draft_range(nvtx::Name::DecodeMtpDraft, nvtx::Category::Mtp,
                                          static_cast<std::uint64_t>(draft_window) * batch_size);
            ops::mtp_prepare_next_round(verify_ids, anchors, accepted, frontiers, budgets,
                                        licensed_counts, rope_deltas, alignment_ids, next_extents,
                                        ar_positions, ar_rope_positions, ar_valid_columns,
                                        static_cast<std::int32_t>(draft_window),
                                        static_cast<std::int32_t>(state.text_cache.max_context()),
                                        state.execution.device.stream);
            card.mtp_forward_decode_batch(alignment_ids, target_hidden, target_positions,
                                          target_rope, licensed_counts, mtp_rows, envelopes.batch,
                                          alignment_hidden);
            ops::speculative_select_accepted_hidden(alignment_hidden, accepted, ar_hidden,
                                                    state.execution.device.stream);

            Tensor proposal_logits = frame.proposal_logits.slice(1, 0, batch_size);
            Tensor draft0          = next_drafts.slice(1, 0, 1).view({batch_size});
            card.mtp_propose_batch(ar_hidden, proposal_logits, draft0);
            for (std::uint32_t step = 0; step + 1 < draft_window; ++step) {
                Tensor previous =
                    next_drafts.slice(1, static_cast<std::int32_t>(step), 1).view({batch_size});
                Tensor next =
                    next_drafts.slice(1, static_cast<std::int32_t>(step + 1), 1).view({batch_size});
                Tensor position =
                    ar_positions.slice(1, static_cast<std::int32_t>(step), 1).view({1, batch_size});
                Tensor rope = ar_rope_positions.slice(1, static_cast<std::int32_t>(step), 1)
                                  .view({1, batch_size});
                Tensor valid = ar_valid_columns.slice(1, static_cast<std::int32_t>(step), 1)
                                   .view({batch_size});
                Tensor previous_batch = previous.view({1, batch_size});
                Tensor hidden_batch   = ar_hidden.view(
                    {dimension(state.execution.parameters.model.config().text.hidden_size), 1,
                       batch_size});
                Tensor next_hidden_batch = next_hidden.view(
                    {dimension(state.execution.parameters.model.config().text.hidden_size), 1,
                     batch_size});
                card.mtp_forward_decode_batch(previous_batch, hidden_batch, position, rope, valid,
                                              mtp_rows, envelopes.ar[step], next_hidden_batch);
                card.mtp_propose_batch(next_hidden, proposal_logits, next);
                CUDA_CHECK(cudaMemcpyAsync(ar_hidden.data, next_hidden.data, ar_hidden.bytes(),
                                           cudaMemcpyDeviceToDevice,
                                           state.execution.device.stream));
            }
        }
        step_graph_record(3, state.execution.device.stream);

        CUDA_CHECK(cudaMemcpyAsync(&state.host_egress, frame.egress.data,
                                   sizeof(qwen3_5::MtpDecodeEgress), cudaMemcpyDeviceToHost,
                                   state.execution.device.stream));
        step_graph_record(4, state.execution.device.stream);
    };
}

void capture_mtp_decode_batch(MtpBatchContext& state, std::int32_t batch_size,
                              std::uint32_t verify_window, std::uint32_t draft_window,
                              MtpCausalAttentionEnvelopes envelopes,
                              DecodeGraphDefinition& definition) {
    step_graph_arm();
    auto body = mtp_decode_batch_body(state, batch_size, verify_window, draft_window, envelopes);
    capture_graph(state, definition, body);
}

void mtp_decode_batch(MtpBatchContext& state, std::int32_t batch_size, std::uint32_t verify_window,
                      std::uint32_t draft_window, MtpCausalAttentionEnvelopes envelopes,
                      DecodeGraphExecutable* executable) {
    auto body = mtp_decode_batch_body(state, batch_size, verify_window, draft_window, envelopes);
    run_prepared(state, executable, body);
}

} // namespace ninfer::models::qwen3_5::execution
