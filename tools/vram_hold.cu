// vram_hold.cu -- 主动触发工具（V3）：占住指定 MiB 显存并保持（释放=进程退出）
// 用法：vram_hold.exe <MiB> <seconds>
#include <cstdio>
#include <cstdlib>
#include <chrono>
#include <thread>
#include <cuda_runtime.h>

int main(int argc, char** argv) {
    if (argc < 3) { std::printf("usage: vram_hold <MiB> <seconds>\n"); return 2; }
    const std::size_t mib = (std::size_t)std::atoi(argv[1]);
    const double secs = std::atof(argv[2]);
    const std::size_t bytes = mib << 20;
    if (cudaSetDevice(0) != cudaSuccess) { std::printf("setDevice failed\n"); return 1; }
    void* p = nullptr;
    const cudaError_t err = cudaMalloc(&p, bytes);
    if (err != cudaSuccess) { std::printf("alloc %zu MiB failed: %s\n", mib, cudaGetErrorString(err)); return 1; }
    if (cudaMemset(p, 7, bytes) != cudaSuccess) { std::printf("memset failed\n"); return 1; }
    std::printf("vram_hold: %zu MiB held for %.0fs\n", mib, secs);
    std::fflush(stdout);
    std::this_thread::sleep_for(std::chrono::milliseconds((long long)(secs * 1000.0)));
    cudaFree(p);
    std::printf("vram_hold: released\n");
    return 0;
}
