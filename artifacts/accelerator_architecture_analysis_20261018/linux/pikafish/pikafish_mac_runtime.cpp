#include "pikafish_mac_runtime.h"
#include "pikafish_mmio_shadow.h"

#include <array>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>

#include "pango_mac_uapi.h"

#if (defined(PIKAFISH_STAGEA_ACCEL) || defined(PIKAFISH_STAGEB_ACCEL)) \
  && !defined(PIKAFISH_MAC_RUNTIME_EMULATED)
    #include <fcntl.h>
    #include <sys/ioctl.h>
    #include <sys/mman.h>
    #include <unistd.h>
#endif

namespace Stockfish::Eval::NNUE::MacRuntime {

namespace {

constexpr std::uint32_t RegId      = 0x00u;
constexpr std::uint32_t RegVersion = 0x04u;
constexpr std::uint32_t RegControl = 0x08u;
constexpr std::uint32_t RegStatus  = 0x0cu;
constexpr std::uint32_t RegDims    = 0x10u;
constexpr std::uint32_t RegFormat  = 0x14u;
constexpr std::uint32_t RegInput   = 0x18u;
constexpr std::uint32_t RegWeight  = 0x1cu;
constexpr std::uint32_t RegBias    = 0x20u;
constexpr std::uint32_t RegOutput  = 0x24u;
constexpr std::uint32_t RegCycles  = 0x28u;

constexpr std::uint32_t MacId            = 0x4d41434bu;
constexpr std::uint32_t MacVersion       = 0x00020100u;
constexpr std::uint32_t ControlStart     = 1u << 0;
constexpr std::uint32_t ControlClear     = 1u << 1;
constexpr std::uint32_t StatusBusy       = 1u << 0;
constexpr std::uint32_t StatusDone       = 1u << 1;
constexpr std::uint32_t StatusError      = 1u << 2;
constexpr std::uint32_t FormatZeroBias   = 1u << 30;
constexpr std::uint32_t DefaultPollLimit = 1000000u;
constexpr std::uint32_t DefaultTimeoutUs = 100000u;
constexpr const char*   DriverPath       = "/dev/pango-mac0";

enum class InjectedFault : std::uint8_t { None, Busy, Error, Timeout };

const char* client_name(Client client) noexcept {
    return client == Client::StageA ? "stagea" : "stageb";
}

struct Runtime {
    std::mutex              mutex;
    volatile std::uint32_t* registers = nullptr;
    std::uint8_t*           ddr       = nullptr;
    bool                    attempted = false;
    bool                    ready     = false;
    bool                    fused     = false;
    bool                    fallbackReported = false;
    std::uint32_t           pollLimit = DefaultPollLimit;
    std::uint32_t           timeoutUs = DefaultTimeoutUs;
    std::uint32_t           lastStatus = 0;
    std::uint32_t           lastCycles = 0;
    int                     deviceFd = -1;
    bool                    driverManaged = false;
    bool                    mmioShadow = false;
    volatile std::uint32_t* physicalDdr = nullptr;
    std::uint8_t*           shadowDdr = nullptr;
    bool                    stageaGather = false;
    bool                    residentSupported = false;
    bool                    residentRegistered = false;
    std::size_t             residentOffset = 0;
    std::size_t             residentBytes = 0;
    std::uint64_t           gatherCompleted = 0;
    std::uint64_t           gatherCycles = 0;
    std::uint64_t           gatherTerms = 0;
    std::uint64_t           gatherHostNanoseconds = 0;
    std::uint64_t           submitted[2]{};
    std::uint64_t           completed[2]{};
    std::uint64_t           failed[2]{};
    InjectedFault           injectedFault = InjectedFault::None;
    bool                    faultInjected = false;
#if defined(PIKAFISH_MAC_RUNTIME_EMULATED)
    std::array<std::uint8_t, DdrBytes> emulatedDdr{};
#endif

    ~Runtime() {
#if (defined(PIKAFISH_STAGEA_ACCEL) || defined(PIKAFISH_STAGEB_ACCEL)) \
  && !defined(PIKAFISH_MAC_RUNTIME_EMULATED)
        if (registers)
            munmap(const_cast<std::uint32_t*>(registers), 4096);
        if (physicalDdr)
            munmap(const_cast<std::uint32_t*>(physicalDdr), DdrBytes);
        else if (ddr)
            munmap(ddr, DdrBytes);
        std::free(shadowDdr);
        if (deviceFd >= 0)
            close(deviceFd);
#endif
    }
};

Runtime& runtime() {
    static Runtime instance;
    return instance;
}

std::uint32_t read_register(const Runtime& state, std::uint32_t offset) noexcept {
    return state.registers[offset / 4u];
}

void write_register(Runtime& state, std::uint32_t offset, std::uint32_t value) noexcept {
    state.registers[offset / 4u] = value;
}

[[maybe_unused]] void report_fallback(Runtime& state, Client client,
                                      const char* reason) noexcept {
    if (!state.fallbackReported)
    {
        state.fallbackReported = true;
        std::fprintf(stderr, "PIKAFISH_MAC_RUNTIME_FALLBACK client=%s reason=%s\n",
                     client_name(client), reason);
    }
}

void fuse(Runtime& state, Client client, const char* reason) noexcept {
    state.fused = true;
    state.ready = false;
    ++state.failed[static_cast<unsigned>(client)];
    const std::uint32_t status = state.registers ? read_register(state, RegStatus)
                                                 : state.lastStatus;
    const std::uint32_t cycles = state.registers ? read_register(state, RegCycles)
                                                 : state.lastCycles;
    if (state.registers)
    {
        write_register(state, RegControl, ControlClear);
        __sync_synchronize();
    }
    std::fprintf(stderr,
                 "PIKAFISH_MAC_RUNTIME_FUSED client=%s reason=%s status=0x%08x cycles=%u\n",
                 client_name(client), reason, static_cast<unsigned>(status),
                 static_cast<unsigned>(cycles));
}

bool initialize(Runtime& state, Client client) noexcept {
    if (state.attempted)
        return state.ready && !state.fused;
    state.attempted = true;

#if !defined(PIKAFISH_STAGEA_ACCEL) && !defined(PIKAFISH_STAGEB_ACCEL)
    report_fallback(state, client, "not-compiled");
    return false;
#else
    if (const char* limit = std::getenv("PIKAFISH_MAC_POLL_LIMIT"))
    {
        char*               end   = nullptr;
        const unsigned long value = std::strtoul(limit, &end, 10);
        if (end != limit && *end == '\0' && value >= 10000u && value <= 10000000u)
            state.pollLimit = static_cast<std::uint32_t>(value);
    }
    if (const char* timeout = std::getenv("PIKAFISH_MAC_TIMEOUT_US"))
    {
        char*               end   = nullptr;
        const unsigned long value = std::strtoul(timeout, &end, 10);
        if (end != timeout && *end == '\0' && value >= 1000u && value <= 1000000u)
            state.timeoutUs = static_cast<std::uint32_t>(value);
    }
    if (const char* fault = std::getenv("PIKAFISH_MAC_FAULT"))
    {
        if (std::strcmp(fault, "busy") == 0)
            state.injectedFault = InjectedFault::Busy;
        else if (std::strcmp(fault, "error") == 0)
            state.injectedFault = InjectedFault::Error;
        else if (std::strcmp(fault, "timeout") == 0)
            state.injectedFault = InjectedFault::Timeout;
    }

#if defined(PIKAFISH_MAC_RUNTIME_EMULATED)
    (void) client;
    state.ddr   = state.emulatedDdr.data();
    state.ready = true;
    std::fprintf(stderr,
                 "PIKAFISH_MAC_RUNTIME_READY id=%08x version=%08x poll_limit=%u "
                 "ddr=emulated\n",
                 static_cast<unsigned>(MacId), static_cast<unsigned>(MacVersion),
                 static_cast<unsigned>(state.pollLimit));
    return true;
#else

    const char* const backend = std::getenv("PIKAFISH_MAC_BACKEND");
    const bool mmioShadow = backend && std::strcmp(backend, "mmio-shadow") == 0;
    if (backend && *backend && !mmioShadow) {
        report_fallback(state, client, "unknown-backend");
        return false;
    }
    const char* const configuredDevice = std::getenv("PIKAFISH_MAC_DEVICE");
    const char* const devicePath = configuredDevice && *configuredDevice
                                 ? configuredDevice : DriverPath;
    const char* const requireDriverValue = std::getenv("PIKAFISH_MAC_REQUIRE_DRIVER");
    const bool requireDriver = configuredDevice
                            || (requireDriverValue
                                && std::strcmp(requireDriverValue, "0") != 0);
    const int driverFd = mmioShadow ? -1 : open(devicePath, O_RDWR | O_CLOEXEC);
    if (driverFd >= 0)
    {
        pango_mac_info info{};
        if (ioctl(driverFd, PANGO_MAC_IOC_GET_INFO, &info) != 0
            || info.abi_version != PANGO_MAC_ABI_VERSION || info.device_id != MacId
            || info.device_version != MacVersion || info.scratch_bytes != DdrBytes
            || (info.features & (PANGO_MAC_FEATURE_PRIVATE_SHADOW
                                 | PANGO_MAC_FEATURE_SERIALIZED))
                 != (PANGO_MAC_FEATURE_PRIVATE_SHADOW | PANGO_MAC_FEATURE_SERIALIZED))
        {
            close(driverFd);
            report_fallback(state, client, "driver-abi");
            return false;
        }
        void* const ddrMap = mmap(nullptr, DdrBytes, PROT_READ | PROT_WRITE,
                                  MAP_SHARED, driverFd, 0);
        if (ddrMap == MAP_FAILED)
        {
            close(driverFd);
            report_fallback(state, client, "driver-mmap");
            return false;
        }
        state.deviceFd = driverFd;
        state.driverManaged = true;
        state.stageaGather = (info.features & PANGO_MAC_FEATURE_STAGEA_GATHER)!=0;
        state.residentSupported = (info.features & PANGO_MAC_FEATURE_RESIDENT_MODEL)!=0;
        state.ddr = static_cast<std::uint8_t*>(ddrMap);
        state.ready = true;
        std::fprintf(stderr,
                     "PIKAFISH_MAC_RUNTIME_READY id=%08x version=%08x timeout_us=%u "
                     "ddr=private backend=driver\n",
                     static_cast<unsigned>(MacId), static_cast<unsigned>(MacVersion),
                     static_cast<unsigned>(state.timeoutUs));
        return true;
    }
    const int driverError = errno;
    if (!mmioShadow && (requireDriver || (driverError != ENOENT && driverError != ENODEV)))
    {
        report_fallback(state, client, "open-driver");
        return false;
    }

    const int memFd = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
    if (memFd < 0)
    {
        report_fallback(state, client, "open-devmem");
        return false;
    }
    void* const regMap = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, memFd,
                              static_cast<off_t>(RegisterPhysical));
    void* const ddrMap = mmap(nullptr, DdrBytes, PROT_READ | PROT_WRITE, MAP_SHARED, memFd,
                              static_cast<off_t>(DdrCpuAlias));
    close(memFd);
    if (regMap == MAP_FAILED || ddrMap == MAP_FAILED)
    {
        if (regMap != MAP_FAILED)
            munmap(regMap, 4096);
        if (ddrMap != MAP_FAILED)
            munmap(ddrMap, DdrBytes);
        report_fallback(state, client, "mmap");
        return false;
    }
    state.registers = static_cast<volatile std::uint32_t*>(regMap);
    state.ddr       = static_cast<std::uint8_t*>(ddrMap);
    if (read_register(state, RegId) != MacId || read_register(state, RegVersion) != MacVersion)
    {
        munmap(const_cast<std::uint32_t*>(state.registers), 4096);
        munmap(state.ddr, DdrBytes);
        state.registers = nullptr;
        state.ddr       = nullptr;
        report_fallback(state, client, "mac-id-version");
        return false;
    }
    write_register(state, RegControl, ControlClear);
    __sync_synchronize();
    if ((read_register(state, RegStatus) & StatusBusy) != 0u)
    {
        fuse(state, client, "busy-after-clear");
        return false;
    }
    if (mmioShadow) {
        state.shadowDdr = static_cast<std::uint8_t*>(std::calloc(DdrBytes, 1u));
        if (!state.shadowDdr) {
            report_fallback(state, client, "shadow-alloc");
            return false;
        }
        state.physicalDdr = static_cast<volatile std::uint32_t*>(ddrMap);
        state.ddr = state.shadowDdr;
        state.mmioShadow = true;
        state.stageaGather =
          read_register(state, 0x100u) == PANGO_MAC_STAGEA_ID &&
          read_register(state, 0x104u) == PANGO_MAC_STAGEA_VERSION;
        std::fprintf(stderr,
          "PIKAFISH_MAC_RUNTIME_READY id=%08x version=%08x backend=mmio-shadow "
          "gather=%u owner=single-process\n",
          static_cast<unsigned>(MacId), static_cast<unsigned>(MacVersion),
          static_cast<unsigned>(state.stageaGather));
        state.ready = true;
        return true;
    }
    state.ready = true;
    std::fprintf(stderr,
                 "PIKAFISH_MAC_RUNTIME_READY id=%08x version=%08x poll_limit=%u "
                 "ddr=0x%08x backend=legacy-devmem\n",
                 static_cast<unsigned>(MacId), static_cast<unsigned>(MacVersion),
                 static_cast<unsigned>(state.pollLimit), static_cast<unsigned>(DdrBusBase));
    return true;
#endif
#endif
}

bool range_ok(std::size_t offset, std::size_t bytes) noexcept {
    return offset <= DdrBytes && bytes <= DdrBytes - offset;
}

bool validate_job(const Job& job, std::size_t& inputBytes, std::size_t& weightBytes,
                  std::size_t& biasBytes, std::size_t& outputBytes) noexcept {
    if (job.pixels == 0 || job.pixels > 16 || job.cin == 0 || job.cin > 256
        || job.cout == 0 || job.cout > 256
        || static_cast<unsigned>(job.computeMode) > 2u
        || static_cast<unsigned>(job.outputFormat) > 3u)
        return false;
    const std::size_t ciTiles = (job.cin + 3u) / 4u;
    const std::size_t coStep = job.computeMode == ComputeMode::S16S16 ? 16u : 32u;
    const std::size_t coTiles = (job.cout + coStep - 1u) / coStep;
    inputBytes  = static_cast<std::size_t>(job.pixels) * ciTiles * 8u;
    weightBytes = coTiles * ciTiles * 128u;
    biasBytes   = job.zeroBias ? 0u : coTiles * 192u;
    outputBytes = static_cast<std::size_t>(job.pixels) * job.cout * 4u;
    return range_ok(job.inputOffset, inputBytes) && range_ok(job.weightOffset, weightBytes)
        && (job.zeroBias || range_ok(job.biasOffset, biasBytes))
        && range_ok(job.outputOffset, outputBytes);
}

}  // namespace

Session::Session(Client client) noexcept : client_(client) {
    Runtime& state = runtime();
    state.mutex.lock();
    locked_ = true;
    ready_  = initialize(state, client);
}

Session::~Session() {
    if (locked_)
        runtime().mutex.unlock();
}

std::uint8_t* Session::ddr(std::size_t offset, std::size_t bytes) const noexcept {
    Runtime& state = runtime();
    return ready_ && range_ok(offset, bytes) ? state.ddr + offset : nullptr;
}

bool Session::submit(const Job& job, std::uint32_t* cycles) noexcept {
    Runtime&    state = runtime();
    std::size_t inputBytes = 0, weightBytes = 0, biasBytes = 0, outputBytes = 0;
    if (!ready_ || !validate_job(job, inputBytes, weightBytes, biasBytes, outputBytes))
        return false;

    const unsigned clientIndex = static_cast<unsigned>(client_);
    ++state.submitted[clientIndex];
    if (!state.faultInjected && state.injectedFault != InjectedFault::None)
    {
        state.faultInjected = true;
        const char* reason = state.injectedFault == InjectedFault::Busy ? "injected-busy"
                           : state.injectedFault == InjectedFault::Error ? "injected-error"
                                                                        : "injected-timeout";
        fuse(state, client_, reason);
        ready_ = false;
        return false;
    }

#if defined(PIKAFISH_MAC_RUNTIME_EMULATED)
    if (job.pixels != 1 || job.cin != 256 || job.cout > 32
        || job.computeMode != ComputeMode::U8S8
        || job.outputFormat != OutputFormat::I32 || !job.zeroBias)
        return false;
    for (unsigned output = 0; output < job.cout; ++output)
    {
        std::uint32_t sum = 0;
        for (unsigned input = 0; input < job.cin; ++input)
        {
            const std::size_t inputIndex = job.inputOffset + (input / 4u) * 8u
                                         + (input % 4u) * 2u;
            const std::size_t weightIndex = job.weightOffset + (input / 4u) * 128u
                                          + ((output / 2u) * 4u + input % 4u) * 2u
                                          + output % 2u;
            const auto weight = static_cast<std::int8_t>(state.ddr[weightIndex]);
            sum += static_cast<std::uint32_t>(static_cast<std::int32_t>(weight)
                                              * state.ddr[inputIndex]);
        }
        std::memcpy(state.ddr + job.outputOffset + output * sizeof(sum), &sum,
                    sizeof(sum));
    }
    if (cycles)
        *cycles = static_cast<std::uint32_t>(job.pixels) * job.cin * job.cout;
    ++state.completed[clientIndex];
    return true;
#else
    if (state.driverManaged)
    {
        pango_mac_job request{};
        request.abi_version  = PANGO_MAC_ABI_VERSION;
        request.pixels       = job.pixels;
        request.cin          = job.cin;
        request.cout         = job.cout;
        request.out_shift    = job.outShift;
        request.compute_mode = static_cast<std::uint8_t>(job.computeMode);
        request.output_format = static_cast<std::uint8_t>(job.outputFormat);
        request.zero_bias    = job.zeroBias ? 1u : 0u;
        request.input_offset = static_cast<std::uint32_t>(job.inputOffset);
        request.weight_offset = static_cast<std::uint32_t>(job.weightOffset);
        request.bias_offset  = static_cast<std::uint32_t>(job.biasOffset);
        request.output_offset = static_cast<std::uint32_t>(job.outputOffset);
        request.timeout_us   = state.timeoutUs;
        const unsigned long command=client_==Client::StageB && state.residentRegistered ?
            PANGO_MAC_IOC_RUN_RESIDENT : PANGO_MAC_IOC_RUN;
        if (ioctl(state.deviceFd, command, &request) != 0)
        {
            state.lastStatus = request.status;
            state.lastCycles = request.cycles;
            const char* reason = errno == ETIMEDOUT ? "driver-timeout"
                               : errno == EBUSY ? "driver-busy"
                               : errno == EIO ? "driver-hardware"
                                              : "driver-ioctl";
            fuse(state, client_, reason);
            ready_ = false;
            return false;
        }
        state.lastStatus = request.status;
        state.lastCycles = request.cycles;
        if (cycles)
            *cycles = request.cycles;
        ++state.completed[clientIndex];
        return true;
    }

    if ((read_register(state, RegStatus) & StatusBusy) != 0u)
    {
        write_register(state, RegControl, ControlClear);
        __sync_synchronize();
        if ((read_register(state, RegStatus) & StatusBusy) != 0u)
        {
            fuse(state, client_, "busy");
            ready_ = false;
            return false;
        }
    }

    if (state.mmioShadow) {
        if ((job.inputOffset | job.weightOffset | job.biasOffset |
             job.outputOffset) & 3u ||
            (state.stageaGather && (read_register(state, 0x10cu) & 1u))) {
            fuse(state, client_, "mmio-range-or-gather-busy");
            ready_ = false;
            return false;
        }
        const bool weightResident = client_ == Client::StageB && state.residentRegistered;
        if (weightResident &&
            (job.weightOffset < state.residentOffset ||
             weightBytes > state.residentBytes ||
             job.weightOffset - state.residentOffset > state.residentBytes - weightBytes)) {
            fuse(state, client_, "resident-range");
            ready_ = false;
            return false;
        }
        if (!MmioShadow::publish(state.physicalDdr, state.ddr, job.inputOffset,
                                 inputBytes, DdrBytes) ||
            (!weightResident && !MmioShadow::publish(state.physicalDdr, state.ddr,
                                 job.weightOffset, weightBytes, DdrBytes)) ||
            (!job.zeroBias && !MmioShadow::publish(state.physicalDdr, state.ddr,
                                 job.biasOffset, biasBytes, DdrBytes))) {
            fuse(state, client_, "mmio-publish");
            ready_ = false;
            return false;
        }
    }

    const std::uint32_t dims = (static_cast<std::uint32_t>(job.cin) << 16) | job.pixels;
    const std::uint32_t format = static_cast<std::uint32_t>(job.cout)
                               | (static_cast<std::uint32_t>(job.outShift) << 16)
                               | (static_cast<std::uint32_t>(job.outputFormat) << 24)
                               | (static_cast<std::uint32_t>(job.computeMode) << 28)
                               | (job.zeroBias ? FormatZeroBias : 0u);
    write_register(state, RegControl, ControlClear);
    write_register(state, RegDims, dims);
    write_register(state, RegFormat, format);
    write_register(state, RegInput,
                   DdrBusBase + static_cast<std::uint32_t>(job.inputOffset));
    write_register(state, RegWeight,
                   DdrBusBase + static_cast<std::uint32_t>(job.weightOffset));
    write_register(state, RegBias,
                   DdrBusBase + static_cast<std::uint32_t>(job.biasOffset));
    write_register(state, RegOutput,
                   DdrBusBase + static_cast<std::uint32_t>(job.outputOffset));
    __sync_synchronize();
    write_register(state, RegControl, ControlStart);

    for (std::uint32_t poll = 0; poll < state.pollLimit; ++poll)
    {
        const std::uint32_t status = read_register(state, RegStatus);
        if ((status & StatusError) != 0u)
        {
            fuse(state, client_, "hardware-error");
            ready_ = false;
            return false;
        }
        if ((status & StatusDone) != 0u)
        {
            __sync_synchronize();
            if (state.mmioShadow && !MmioShadow::collect(state.physicalDdr,
                state.ddr, job.outputOffset, outputBytes, DdrBytes)) {
                fuse(state, client_, "mmio-collect");
                ready_ = false;
                return false;
            }
            const std::uint32_t elapsed = read_register(state, RegCycles);
            if (cycles)
                *cycles = elapsed;
            ++state.completed[clientIndex];
            return true;
        }
    }
    fuse(state, client_, "timeout");
    ready_ = false;
    return false;
#endif
}

bool Session::register_model(std::size_t offset,std::size_t bytes) noexcept
{
    Runtime& state=runtime();
    if(!ready_ || client_!=Client::StageB || offset>DdrBytes || bytes>DdrBytes-offset)
        return false;
#if !defined(PIKAFISH_MAC_RUNTIME_EMULATED) && (defined(PIKAFISH_STAGEA_ACCEL) || defined(PIKAFISH_STAGEB_ACCEL))
    if(state.mmioShadow) {
        if (!MmioShadow::publish(state.physicalDdr, state.ddr, offset, bytes, DdrBytes))
            return false;
        state.residentRegistered = true;
        state.residentOffset = offset;
        state.residentBytes = bytes;
    } else if(state.driverManaged && state.residentSupported) {
        pango_mac_model model{};
        model.abi_version=PANGO_MAC_MODEL_ABI_VERSION;
        model.offset=static_cast<std::uint32_t>(offset);model.bytes=static_cast<std::uint32_t>(bytes);
        if(ioctl(state.deviceFd,PANGO_MAC_IOC_REGISTER_MODEL,&model)!=0) return false;
        state.residentRegistered=true;
        std::fprintf(stderr,"PIKAFISH_STAGEB_KERNEL_RESIDENT bytes=%zu backend=driver\n",bytes);
    }
#else
    (void)state;
#endif
    return true;
}

bool Session::gather_available() const noexcept {
    return ready_ && runtime().stageaGather &&
           (runtime().driverManaged || runtime().mmioShadow);
}

bool Session::gather(std::uint32_t terms, std::uint32_t* cycles) noexcept {
#if defined(PIKAFISH_MAC_RUNTIME_EMULATED) || (!defined(PIKAFISH_STAGEA_ACCEL) && !defined(PIKAFISH_STAGEB_ACCEL))
    (void)terms;(void)cycles;return false;
#else
    Runtime& state=runtime();
    if(client_!=Client::StageA || !gather_available() || !terms || terms>256) return false;
    pango_mac_stagea_job job{};
    job.abi_version=PANGO_MAC_STAGEA_ABI_VERSION;job.terms=terms;
    job.base_offset=StageAInputOffset;job.descriptor_offset=StageAWeightOffset;
    job.output_offset=StageAOutputOffset;job.timeout_us=state.timeoutUs;
    ++state.submitted[0];
    const auto start=std::chrono::steady_clock::now();
    if(state.mmioShadow) {
        if (!pango_mac_stagea_job_valid(&job, DdrBytes) ||
            (read_register(state, RegStatus) & StatusBusy) ||
            (read_register(state, 0x10cu) & 1u)) {
            fuse(state, client_, "gather-invalid-or-busy");
            ready_=false;return false;
        }
        for(std::uint32_t i=0;i<terms;i++) {
            std::uint32_t descriptor;
            std::memcpy(&descriptor,state.ddr+StageAWeightOffset+i*4u,4u);
            if(!pango_mac_stagea_descriptor_valid(descriptor)) {
                fuse(state,client_,"gather-descriptor");ready_=false;return false;
            }
        }
        if(!MmioShadow::publish(state.physicalDdr,state.ddr,StageAInputOffset,
                                StageAGatherBaseBytes,DdrBytes) ||
           !MmioShadow::publish(state.physicalDdr,state.ddr,StageAWeightOffset,
                                terms*4u,DdrBytes)) {
            fuse(state,client_,"gather-publish");ready_=false;return false;
        }
        write_register(state,0x108u,2u);
        write_register(state,0x110u,DdrBusBase+StageAInputOffset);
        write_register(state,0x114u,DdrBusBase+StageAWeightOffset);
        write_register(state,0x118u,DdrBusBase+StageAOutputOffset);
        write_register(state,0x11cu,terms);
        __sync_synchronize();
        write_register(state,0x108u,1u);
        bool done=false;
        for(std::uint32_t poll=0;poll<state.pollLimit;poll++) {
            job.status=read_register(state,0x10cu);
            if((job.status & 3u)==2u) { done=true; break; }
        }
        job.cycles=read_register(state,0x120u);
        if(!done || (job.status & 4u) ||
           !MmioShadow::collect(state.physicalDdr,state.ddr,StageAOutputOffset,
                                StageAGatherOutputBytes,DdrBytes)) {
            fuse(state,client_,done ? "gather-hardware" : "gather-timeout");
            ready_=false;return false;
        }
    } else if(ioctl(state.deviceFd,PANGO_MAC_IOC_RUN_STAGEA,&job)!=0) {
        state.lastStatus=job.status;state.lastCycles=job.cycles;
        fuse(state,client_,errno==ETIMEDOUT ? "gather-timeout" : "gather-ioctl");
        ready_=false;return false;
    }
    state.lastStatus=job.status;state.lastCycles=job.cycles;
    if(cycles)*cycles=job.cycles;
    ++state.gatherCompleted;
    state.gatherCycles+=job.cycles;
    state.gatherTerms+=terms;
    state.gatherHostNanoseconds+=static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now()-start).count());
    ++state.completed[0];return true;
#endif
}

Statistics statistics() noexcept {
    Runtime& state = runtime();
    std::lock_guard<std::mutex> lock(state.mutex);
    Statistics result{};
    result.ready = state.ready;
    result.fused = state.fused;
    result.residentRegistered = state.residentRegistered;
    result.gatherCompleted = state.gatherCompleted;
    result.gatherCycles = state.gatherCycles;
    result.gatherTerms = state.gatherTerms;
    result.gatherHostNanoseconds = state.gatherHostNanoseconds;
    for (unsigned client = 0; client < 2; ++client)
    {
        result.submitted[client] = state.submitted[client];
        result.completed[client] = state.completed[client];
        result.failed[client] = state.failed[client];
    }
    return result;
}

}  // namespace Stockfish::Eval::NNUE::MacRuntime
