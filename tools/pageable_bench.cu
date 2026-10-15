// pageable_bench.cu -- pageable vs pinned 宿主内存的 H2D/D2H 拷贝对照（I3b，2026-10-16）
// 动机：engine 的 PinnedHostBuffer 在 NINFER_HOST_PAGEABLE=1 时走 pageable malloc，
//       引擎注释明说"对它的 memcpy 会被 bounce buffer 中转、不是真正异步"。
//       本工具同刻测三种内存的拷贝成本，用于判定"谷/瞬时深慢是否发生在 pageable 路径上"。
// 用法：pageable_bench.exe [bytes_MiB=64] [iters=20]
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cuda_runtime.h>

static double time_copy(void* dst, const void* src, std::size_t bytes, int iters,
                        cudaMemcpyKind kind, cudaStream_t s, bool sync_each) {
    // warmup
    cudaMemcpyAsync(dst, src, bytes, kind, s);
    cudaStreamSynchronize(s);
    cudaEvent_t a, b; cudaEventCreate(&a); cudaEventCreate(&b);
    cudaEventRecord(a, s);
    for (int i = 0; i < iters; ++i) {
        cudaMemcpyAsync(dst, src, bytes, kind, s);
        if (sync_each) { cudaStreamSynchronize(s); }
    }
    cudaEventRecord(b, s);
    float ms = 0.0f;
    if (cudaEventSynchronize(b) != cudaSuccess) { cudaGetLastError(); return -1.0; }
    cudaEventElapsedTime(&ms, a, b);
    cudaEventDestroy(a); cudaEventDestroy(b);
    return ms / iters;
}

int main(int argc, char** argv) {
    const std::size_t mib = argc > 1 ? (std::size_t)std::atoi(argv[1]) : 64;
    const int iters = argc > 2 ? std::atoi(argv[2]) : 20;
    const std::size_t bytes = mib << 20;
    if (cudaSetDevice(0) != cudaSuccess) { std::printf("setDevice failed\n"); return 1; }

    void* d = nullptr;
    if (cudaMalloc(&d, bytes) != cudaSuccess) { std::printf("device alloc failed\n"); return 1; }
    cudaMemset(d, 1, bytes);

    void* pageable = std::malloc(bytes);
    void* pinned = nullptr;
    if (pageable == nullptr) { std::printf("pageable malloc failed\n"); return 1; }
    if (cudaHostAlloc(&pinned, bytes, cudaHostAllocDefault) != cudaSuccess) {
        std::printf("pinned alloc failed (expected when vram is nearly full)\n");
    }
    std::memset(pageable, 2, bytes);
    if (pinned) { std::memset(pinned, 3, bytes); }

    cudaStream_t s; cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking);
    // pageable H2D (the engine's path when NINFER_HOST_PAGEABLE=1)
    const double p_h2d = time_copy(d, pageable, bytes, iters, cudaMemcpyHostToDevice, s, true);
    const double p_d2h = time_copy(pageable, d, bytes, iters, cudaMemcpyDeviceToHost, s, true);
    double k_h2d = -1.0, k_d2h = -1.0;
    if (pinned) {
        k_h2d = time_copy(d, pinned, bytes, iters, cudaMemcpyHostToDevice, s, true);
        k_d2h = time_copy(pinned, d, bytes, iters, cudaMemcpyDeviceToHost, s, true);
    }
    std::printf("{\"bytes_MiB\":%zu,\"iters\":%d,\"pageable_h2d_ms\":%.3f,\"pageable_d2h_ms\":%.3f,"
                "\"pinned_h2d_ms\":%.3f,\"pinned_d2h_ms\":%.3f}\n",
                mib, iters, p_h2d, p_d2h, k_h2d, k_d2h);
    cudaStreamDestroy(s);
    if (pinned) { cudaFreeHost(pinned); }
    std::free(pageable);
    cudaFree(d);
    return 0;
}
