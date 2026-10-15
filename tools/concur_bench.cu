// concur_bench.cu -- 跨进程 CUDA 诊断微基准（I3b，2026-10-16）
// 三项同进程测量（引擎在跑时从外部进程执行，用于判别谷期瓶颈在哪一层）：
//   [gpu]       1-thread 空核端到端延迟  -> SM 是否被占满（自旋型会显著放大）
//   [host_page] 4 条 cacheline 的 host 映射页读延迟 -> 宿主页路径的"单次访问"成本
//   [host_bw]   64 MiB host 映射页扫读带宽（GB/s） -> 宿主页路径的"吞吐"能力
// 用法：concur_bench.exe [iters=100]
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cuda_runtime.h>

__global__ void tiny_kernel(unsigned long long* out, unsigned long long v) {
    if (threadIdx.x == 0 && blockIdx.x == 0) { *out = v; }
}

__global__ void host_page_kernel(const unsigned long long* in, unsigned long long* out) {
    if (threadIdx.x == 0 && blockIdx.x == 0) { *out = in[0] + in[1] + in[2] + in[3]; }
}

__global__ void host_bw_kernel(const unsigned long long* in, unsigned long long n,
                               unsigned long long* acc) {
    unsigned long long i = (unsigned long long)blockIdx.x * blockDim.x + threadIdx.x;
    const unsigned long long stride = (unsigned long long)gridDim.x * blockDim.x;
    unsigned long long s = 0;
    for (; i < n; i += stride) { s += in[i]; }
    if (threadIdx.x == 0) { atomicAdd(acc, s); }
}

static void run_gpu(int iters) {
    unsigned long long* d = nullptr;
    cudaStream_t s;
    if (cudaMalloc(&d, sizeof(unsigned long long)) != cudaSuccess) { std::printf("{\"gpu\":\"malloc-fail\"}"); return; }
    if (cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking) != cudaSuccess) { std::printf("{\"gpu\":\"stream-fail\"}"); return; }
    for (int i = 0; i < 20; ++i) { tiny_kernel<<<1, 1, 0, s>>>(d, 1ULL); }
    cudaStreamSynchronize(s);
    double sum = 0.0, best = 1e9, worst = 0.0; int n = 0;
    for (int i = 0; i < iters; ++i) {
        cudaEvent_t a, b; cudaEventCreate(&a); cudaEventCreate(&b);
        cudaEventRecord(a, s);
        tiny_kernel<<<1, 1, 0, s>>>(d, 2ULL);
        cudaEventRecord(b, s);
        if (cudaEventSynchronize(b) != cudaSuccess) { cudaGetLastError(); break; }
        float ms = 0.0f;
        if (cudaEventElapsedTime(&ms, a, b) == cudaSuccess) { sum += ms; ++n; if (ms < best) best = ms; if (ms > worst) worst = ms; }
        cudaEventDestroy(a); cudaEventDestroy(b);
    }
    if (n > 0) { std::printf("{\"gpu\":{\"n\":%d,\"mean_us\":%.2f,\"min_us\":%.2f,\"max_us\":%.2f}}", n, sum / n * 1000.0, best * 1000.0, worst * 1000.0); }
    else { std::printf("{\"gpu\":\"no-samples\"}"); }
    cudaStreamDestroy(s); cudaFree(d);
}

static void run_host_page(int iters) {
    void* host = nullptr;
    if (cudaHostAlloc(&host, sizeof(unsigned long long) * 4, cudaHostAllocMapped) != cudaSuccess) { std::printf(",{\"host_page\":\"alloc-fail\"}"); return; }
    unsigned long long* hp = static_cast<unsigned long long*>(host);
    for (int i = 0; i < 4; ++i) { hp[i] = (unsigned long long)(i + 1); }
    void* dev = nullptr;
    if (cudaHostGetDevicePointer(&dev, host, 0) != cudaSuccess) { std::printf(",{\"host_page\":\"devptr-fail\"}"); cudaFreeHost(host); return; }
    unsigned long long* dout = nullptr;
    if (cudaMalloc(&dout, sizeof(unsigned long long)) != cudaSuccess) { std::printf(",{\"host_page\":\"malloc-fail\"}"); cudaFreeHost(host); return; }
    cudaStream_t s; cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking);
    for (int i = 0; i < 20; ++i) { host_page_kernel<<<1, 1, 0, s>>>(static_cast<const unsigned long long*>(dev), dout); }
    cudaStreamSynchronize(s);
    double sum = 0.0, best = 1e9, worst = 0.0; int n = 0;
    for (int i = 0; i < iters; ++i) {
        cudaEvent_t a, b; cudaEventCreate(&a); cudaEventCreate(&b);
        cudaEventRecord(a, s);
        host_page_kernel<<<1, 1, 0, s>>>(static_cast<const unsigned long long*>(dev), dout);
        cudaEventRecord(b, s);
        if (cudaEventSynchronize(b) != cudaSuccess) { cudaGetLastError(); break; }
        float ms = 0.0f;
        if (cudaEventElapsedTime(&ms, a, b) == cudaSuccess) { sum += ms; ++n; if (ms < best) best = ms; if (ms > worst) worst = ms; }
        cudaEventDestroy(a); cudaEventDestroy(b);
    }
    if (n > 0) { std::printf(",{\"host_page\":{\"n\":%d,\"mean_us\":%.2f,\"min_us\":%.2f,\"max_us\":%.2f}}", n, sum / n * 1000.0, best * 1000.0, worst * 1000.0); }
    else { std::printf(",{\"host_page\":\"no-samples\"}"); }
    cudaStreamDestroy(s); cudaFree(dout); cudaFreeHost(host);
}

static void run_host_bw(int iters) {
    const std::size_t bytes = (std::size_t)64 << 20;
    const unsigned long long n = (unsigned long long)(bytes / sizeof(unsigned long long));
    void* host = nullptr;
    if (cudaHostAlloc(&host, bytes, cudaHostAllocMapped) != cudaSuccess) { std::printf(",{\"host_bw\":\"alloc-fail\"}\n"); return; }
    unsigned long long* hp = static_cast<unsigned long long*>(host);
    for (std::size_t i = 0; i < (std::size_t)n; ++i) { hp[i] = (unsigned long long)i; }
    void* dev = nullptr;
    if (cudaHostGetDevicePointer(&dev, host, 0) != cudaSuccess) { std::printf(",{\"host_bw\":\"devptr-fail\"}\n"); cudaFreeHost(host); return; }
    unsigned long long* acc = nullptr;
    if (cudaMalloc(&acc, sizeof(unsigned long long)) != cudaSuccess) { std::printf(",{\"host_bw\":\"acc-fail\"}\n"); cudaFreeHost(host); return; }
    cudaStream_t s; cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking);
    host_bw_kernel<<<64, 256, 0, s>>>(static_cast<const unsigned long long*>(dev), n, acc);
    cudaStreamSynchronize(s);
    cudaEvent_t a, b; cudaEventCreate(&a); cudaEventCreate(&b);
    cudaEventRecord(a, s);
    for (int k = 0; k < iters; ++k) { host_bw_kernel<<<64, 256, 0, s>>>(static_cast<const unsigned long long*>(dev), n, acc); }
    cudaEventRecord(b, s);
    if (cudaEventSynchronize(b) == cudaSuccess) {
        float ms = 0.0f; cudaEventElapsedTime(&ms, a, b);
        const double gbs = (double)bytes * (double)iters / ((double)ms / 1000.0) / 1e9;
        std::printf(",{\"host_bw\":{\"iters\":%d,\"ms\":%.2f,\"GBps\":%.2f}}\n", iters, ms, gbs);
    } else {
        std::printf(",{\"host_bw\":\"fail\"}\n");
    }
    cudaEventDestroy(a); cudaEventDestroy(b); cudaStreamDestroy(s); cudaFree(acc); cudaFreeHost(host);
}

int main(int argc, char** argv) {
    int iters = argc > 1 ? std::atoi(argv[1]) : 100;
    if (iters <= 0) { iters = 100; }
    if (cudaSetDevice(0) != cudaSuccess) { std::printf("{\"error\":\"setDevice\"}\n"); return 1; }
    run_gpu(iters);
    run_host_page(iters);
    run_host_bw(4);
    return 0;
}
