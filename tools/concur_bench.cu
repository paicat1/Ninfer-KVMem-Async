// concur_bench.cu -- 跨进程并发核延迟 + host 映射页读延迟微基准（I3b 诊断用，2026-10-16 00:1x）
// 两个子测：
//   [gpu] 发一枚 1-thread 空核（侧流），测端到端延迟——判 SM 是否被占满（自旋型会显著放大）
//   [host] 让一枚核读一块 cudaHostAlloc(Mapped) 的主机页并写回，测延迟——判"图内读 host 页"是否变慢
//          （gpu_sampler 判读 A' 分支：GPU 100% + PCIe 高 ⇒ 图内读 host 页）
// 用法：concur_bench.exe [iters=200]
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cuda_runtime.h>

__global__ void tiny_kernel(unsigned long long* out, unsigned long long v) {
    if (threadIdx.x == 0 && blockIdx.x == 0) { *out = v; }
}

// 读一块主机映射页（zero-copy：设备直接经 PCIe 读主机内存），把读到的和写回
__global__ void host_page_kernel(const unsigned long long* in, unsigned long long* out) {
    if (threadIdx.x == 0 && blockIdx.x == 0) { *out = in[0] + in[1] + in[2] + in[3]; }
}

static void run_gpu(int iters) {
    unsigned long long* d = nullptr;
    if (cudaMalloc(&d, sizeof(unsigned long long)) != cudaSuccess) { std::printf("{\"gpu\":\"malloc-fail\"}\n"); return; }
    cudaStream_t s;
    if (cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking) != cudaSuccess) { std::printf("{\"gpu\":\"stream-fail\"}\n"); return; }
    for (int i = 0; i < 20; ++i) { tiny_kernel<<<1, 1, 0, s>>>(d, 1ULL); }
    if (cudaStreamSynchronize(s) != cudaSuccess) { std::printf("{\"gpu\":\"warmup-fail\"}\n"); return; }
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
    if (n == 0) { std::printf("{\"gpu\":\"no-samples\"}\n"); return; }
    std::printf("{\"gpu\":{\"iters\":%d,\"mean_ms\":%.4f,\"min_ms\":%.4f,\"max_ms\":%.4f}}", n, sum / n, best, worst);
    cudaStreamDestroy(s); cudaFree(d);
}

static void run_host(int iters) {
    void* host = nullptr;
    if (cudaHostAlloc(&host, sizeof(unsigned long long) * 4, cudaHostAllocMapped) != cudaSuccess) {
        std::printf("{\"host\":\"hostalloc-fail\"}\n"); return;
    }
    std::memset(host, 0, sizeof(unsigned long long) * 4);
    unsigned long long* hp = static_cast<unsigned long long*>(host);
    hp[0] = 1; hp[1] = 2; hp[2] = 3; hp[3] = 4;
    void* dev = nullptr;
    if (cudaHostGetDevicePointer(&dev, host, 0) != cudaSuccess) {
        std::printf("{\"host\":\"devptr-fail\"}\n"); cudaFreeHost(host); return;
    }
    unsigned long long* dout = nullptr;
    if (cudaMalloc(&dout, sizeof(unsigned long long)) != cudaSuccess) {
        std::printf("{\"host\":\"malloc-fail\"}\n"); cudaFreeHost(host); return;
    }
    cudaStream_t s;
    if (cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking) != cudaSuccess) {
        std::printf("{\"host\":\"stream-fail\"}\n"); cudaFreeHost(host); return;
    }
    for (int i = 0; i < 20; ++i) { host_page_kernel<<<1, 1, 0, s>>>(static_cast<unsigned long long*>(dev), dout); }
    if (cudaStreamSynchronize(s) != cudaSuccess) { std::printf("{\"host\":\"warmup-fail\"}\n"); cudaFreeHost(host); return; }
    double sum = 0.0, best = 1e9, worst = 0.0;
    int n = 0;
    for (int i = 0; i < iters; ++i) {
        cudaEvent_t a, b;
        cudaEventCreate(&a); cudaEventCreate(&b);
        cudaEventRecord(a, s);
        host_page_kernel<<<1, 1, 0, s>>>(static_cast<unsigned long long*>(dev), dout);
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
    if (n == 0) { std::printf("{\"host\":\"no-samples\"}\n"); cudaFreeHost(host); return; }
    std::printf(",{\"host_page\":{\"iters\":%d,\"mean_ms\":%.4f,\"min_ms\":%.4f,\"max_ms\":%.4f}}\n", n, sum / n, best, worst);
    cudaStreamDestroy(s); cudaFree(dout); cudaFreeHost(host);
}

int main(int argc, char** argv) {
    int iters = argc > 1 ? std::atoi(argv[1]) : 200;
    if (iters <= 0) { iters = 200; }
    if (cudaSetDevice(0) != cudaSuccess) { std::printf("{\"error\":\"setDevice\"}\n"); return 1; }
    run_gpu(iters);
    run_host(iters);
    return 0;
}
