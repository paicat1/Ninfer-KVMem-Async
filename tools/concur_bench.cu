// concur_bench.cu -- 跨进程并发核延迟微基准（I3b 诊断用，2026-10-15 23:4x）
// 用途：引擎在跑（谷或健康）时，从本进程向 GPU 发一枚极小核，测其端到端延迟。
//   健康态：SM 有余量 ⇒ 小核延迟 ≈ 空载值（亚毫秒）
//   自旋态：我们的自旋 CTA 占满 SM ⇒ 小核被排到后面 ⇒ 延迟显著放大（数倍）
// 用法：concur_bench.exe [iters=200] [--json]
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

__global__ void tiny_kernel(unsigned long long* out, unsigned long long v) {
    if (threadIdx.x == 0 && blockIdx.x == 0) { *out = v; }
}

int main(int argc, char** argv) {
    int iters = argc > 1 ? std::atoi(argv[1]) : 200;
    if (iters <= 0) { iters = 200; }

    int dev = 0;
    if (cudaSetDevice(dev) != cudaSuccess) { std::printf("{\"error\":\"setDevice\"}\n"); return 1; }
    unsigned long long* d = nullptr;
    if (cudaMalloc(&d, sizeof(unsigned long long)) != cudaSuccess) {
        std::printf("{\"error\":\"malloc\"}\n");
        return 1;
    }
    cudaStream_t s;
    if (cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking) != cudaSuccess) {
        std::printf("{\"error\":\"stream\"}\n");
        return 1;
    }

    // warmup
    for (int i = 0; i < 20; ++i) { tiny_kernel<<<1, 1, 0, s>>>(d, 1ULL); }
    if (cudaStreamSynchronize(s) != cudaSuccess) { std::printf("{\"error\":\"warmup\"}\n"); return 1; }

    double sum = 0.0, best = 1e9, worst = 0.0;
    int n = 0;
    for (int i = 0; i < iters; ++i) {
        cudaEvent_t a, b;
        cudaEventCreate(&a); cudaEventCreate(&b);
        cudaEventRecord(a, s);
        tiny_kernel<<<1, 1, 0, s>>>(d, 2ULL);
        cudaEventRecord(b, s);
        if (cudaEventSynchronize(b) != cudaSuccess) { cudaGetLastError(); break; }
        float ms = 0.0f;
        if (cudaEventElapsedTime(&ms, a, b) == cudaSuccess) {
            sum += ms; ++n;
            if (ms < best) { best = ms; }
            if (ms > worst) { worst = ms; }
        }
        cudaEventDestroy(a); cudaEventDestroy(b);
    }
    if (n == 0) { std::printf("{\"error\":\"no samples\"}\n"); return 1; }
    std::printf("{\"iters\":%d,\"mean_ms\":%.4f,\"min_ms\":%.4f,\"max_ms\":%.4f}\n", n, sum / n, best, worst);
    cudaStreamDestroy(s);
    cudaFree(d);
    return 0;
}
