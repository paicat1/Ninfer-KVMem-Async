// submit_load.cu -- 主动触发工具（V4）：向 GPU 提交队列/PCIe 持续加压，可秒级启停（释放=进程退出）
// 模式：
//   launch <sec>   连续发射极小核（提交洪泛）
//   copy   <sec>   连续 D2D 64MiB 拷贝（显存带宽 + 提交）
//   host   <sec>   连续 H2D+D2H 64MiB（PCIe 双向）
// 用法：submit_load.exe <launch|copy|host> <seconds>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cuda_runtime.h>

__global__ void tiny_kernel(unsigned long long* out, unsigned long long v) {
    if (threadIdx.x == 0 && blockIdx.x == 0) { *out = v; }
}

int main(int argc, char** argv) {
    if (argc < 3) { std::printf("usage: submit_load <launch|copy|host> <seconds>\n"); return 2; }
    const char* mode = argv[1];
    const double secs = std::atof(argv[2]);
    if (cudaSetDevice(0) != cudaSuccess) { std::printf("setDevice failed\n"); return 1; }

    const std::size_t bytes = (std::size_t)64 << 20;
    unsigned long long* d = nullptr;
    unsigned long long* d2 = nullptr;
    void* h = nullptr;
    if (cudaMalloc(&d, sizeof(unsigned long long)) != cudaSuccess) { std::printf("malloc failed\n"); return 1; }
    if (std::strcmp(mode, "launch") != 0) {
        if (cudaMalloc(&d2, bytes) != cudaSuccess) { std::printf("malloc2 failed\n"); return 1; }
        if (cudaMemset(d2, 1, bytes) != cudaSuccess) { std::printf("memset failed\n"); return 1; }
        if (std::strcmp(mode, "host") == 0 && cudaHostAlloc(&h, bytes, cudaHostAllocDefault) != cudaSuccess) {
            std::printf("hostalloc failed\n"); return 1;
        }
        if (h) { std::memset(h, 2, bytes); }
    }

    cudaStream_t s; cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking);
    const double t_end = (double)clock() / CLOCKS_PER_SEC + secs;
    unsigned long long iters = 0, ops = 0;
    // warm up so the first iterations are not the measurement
    for (int i = 0; i < 50; ++i) { tiny_kernel<<<1, 1, 0, s>>>(d, 1ULL); }
    cudaStreamSynchronize(s);
    while ((double)clock() / CLOCKS_PER_SEC < t_end) {
        for (int i = 0; i < 200; ++i) {
            if (std::strcmp(mode, "launch") == 0) {
                tiny_kernel<<<1, 1, 0, s>>>(d, (unsigned long long)iters);
                ++ops;
            } else if (std::strcmp(mode, "copy") == 0) {
                cudaMemcpyAsync(d, d2, bytes, cudaMemcpyDeviceToDevice, s);
                ++ops;
            } else {
                cudaMemcpyAsync(d2, h, bytes, cudaMemcpyHostToDevice, s);
                cudaMemcpyAsync(h, d2, bytes, cudaMemcpyDeviceToHost, s);
                ops += 2;
            }
        }
        cudaStreamSynchronize(s);   // keep the queue full in batches
        ++iters;
    }
    std::printf("submit_load mode=%s ops=%llu elapsed_target=%.0fs\n", mode, ops, secs);
    cudaStreamDestroy(s);
    if (h) { cudaFreeHost(h); }
    if (d2) { cudaFree(d2); }
    cudaFree(d);
    return 0;
}
