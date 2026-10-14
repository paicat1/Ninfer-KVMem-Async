// gpu_probe.cu -- machine-level GPU health probe (2026-10-14, CB).
// Fixed FMA workload; reports wall ms and the SM cycles the kernel actually burned,
// so the achieved SM clock = cycles / wall is visible even when the driver may be throttling.
// Usage: gpu_probe.exe [runs] [iters]
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

__global__ void fma_bench(float* out, long long* clk, int iters) {
    float a = (float)threadIdx.x * 1e-4f + 1.0f, b = 1.0000001f, c = 0.9999999f;
    long long t0 = clock64();
    #pragma unroll 8
    for (int i = 0; i < iters; ++i) {
        a = fmaf(a, b, c); b = fmaf(b, a, c); c = fmaf(c, b, a); a = fmaf(a, c, b);
        b = fmaf(b, c, a); c = fmaf(c, a, b); a = fmaf(a, b, c); b = fmaf(b, a, c);
    }
    long long t1 = clock64();
    if (threadIdx.x == 0) clk[blockIdx.x] = t1 - t0;
    out[blockIdx.x * blockDim.x + threadIdx.x] = a + b + c;
}

int main(int argc, char** argv) {
    int runs = (argc > 1) ? atoi(argv[1]) : 3;
    int iters = (argc > 2) ? atoi(argv[2]) : 20000;
    const int blocks = 132, threads = 256;
    float* d = nullptr; long long* clk = nullptr;
    if (cudaMalloc(&d, (size_t)blocks * threads * 4) != cudaSuccess) { printf("cudaMalloc d failed\n"); return 2; }
    if (cudaMalloc(&clk, 4096 * 8) != cudaSuccess) { printf("cudaMalloc clk failed\n"); return 2; }
    fma_bench<<<blocks, threads>>>(d, clk, 2000);            // warm-up
    cudaDeviceSynchronize();
    cudaEvent_t e0, e1; cudaEventCreate(&e0); cudaEventCreate(&e1);
    for (int r = 0; r < runs; ++r) {
        cudaEventRecord(e0, 0);
        fma_bench<<<blocks, threads>>>(d, clk, iters);
        cudaEventRecord(e1, 0);
        cudaEventSynchronize(e1);
        float ms = 0.0f; cudaEventElapsedTime(&ms, e0, e1);
        long long* host = (long long*)malloc(sizeof(long long) * blocks);
        cudaMemcpy(host, clk, sizeof(long long) * blocks, cudaMemcpyDeviceToHost);
        double cycles = (double)host[0];
        double ghz = (ms > 0.0) ? cycles / (ms * 1e-3) / 1e9 : 0.0;
        double gflop = (double)blocks * threads * iters * 8.0 * 2.0 / (ms * 1e-3) / 1e9;
        printf("run %d: %.2f ms | cycles(blk0)=%.0f | sm_clk=%.2f GHz | %.1f GFLOP/s\n", r, ms, cycles, ghz, gflop);
        free(host);
        cudaError_t err = cudaGetLastError();
        if (err != cudaSuccess) { printf("cuda error: %s\n", cudaGetErrorString(err)); return 3; }
    }
    return 0;
}
