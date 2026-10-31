// PFF1 fully decoded NNUE loader.
// Included by nnue/network.cpp inside Stockfish::Eval::NNUE.

namespace FlatPff1 {

constexpr u32 HeaderBytes  = 4096;
constexpr u32 SectionCount = 6;
constexpr u32 Flags        = 0x00000007u;

struct Section {
    char name[4];
    u64  offset;
    u64  size;
    u32  crc32;
};

enum class LoadStatus {
    Ok,
    Size,
    Seek,
    Read,
    Crc
};

static const char* load_status_name(LoadStatus status) {
    switch (status)
    {
    case LoadStatus::Ok:
        return "ok";
    case LoadStatus::Size:
        return "size";
    case LoadStatus::Seek:
        return "seek";
    case LoadStatus::Read:
        return "read";
    case LoadStatus::Crc:
        return "crc";
    }
    return "unknown";
}

static u16 get_u16(const char* p) {
    const auto* b = reinterpret_cast<const unsigned char*>(p);
    return static_cast<u16>(b[0]) | static_cast<u16>(static_cast<u16>(b[1]) << 8);
}

static u32 get_u32(const char* p) {
    const auto* b = reinterpret_cast<const unsigned char*>(p);
    return static_cast<u32>(b[0]) | (static_cast<u32>(b[1]) << 8)
         | (static_cast<u32>(b[2]) << 16) | (static_cast<u32>(b[3]) << 24);
}

static u64 get_u64(const char* p) {
    return static_cast<u64>(get_u32(p)) | (static_cast<u64>(get_u32(p + 4)) << 32);
}

static const std::array<u32, 256>& crc_table() {
    static const std::array<u32, 256> table = [] {
        std::array<u32, 256> result{};
        for (u32 i = 0; i < result.size(); ++i)
        {
            u32 value = i;
            for (unsigned bit = 0; bit < 8; ++bit)
                value = (value >> 1) ^ (0xEDB88320u & (0u - (value & 1u)));
            result[i] = value;
        }
        return result;
    }();
    return table;
}

static u32 update_crc(u32 crc, const char* data, usize size) {
    const auto& table = crc_table();
    for (usize i = 0; i < size; ++i)
        crc = table[(crc ^ static_cast<unsigned char>(data[i])) & 0xFFu] ^ (crc >> 8);
    return crc;
}

static bool seek_to(std::istream& stream, u64 offset) {
    stream.clear();
    stream.seekg(static_cast<std::streamoff>(offset), std::ios_base::beg);
    return bool(stream);
}

static bool read_fully(std::istream& stream, char* destination, usize size) {
    while (size != 0) {
        stream.read(destination, static_cast<std::streamsize>(size));
        const std::streamsize count = stream.gcount();
        if (count <= 0)
            return false;
        destination += count;
        size -= static_cast<usize>(count);
        if (size != 0 && stream.fail())
            stream.clear();
    }
    return true;
}

#if !defined(PIKAFISH_PFF1_DIRECT_VIEW)
static LoadStatus
read_and_crc(std::istream& stream, const Section& section, void* destination, usize size) {
    if (section.size != size)
        return LoadStatus::Size;
    if (!seek_to(stream, section.offset))
        return LoadStatus::Seek;

    char* out  = static_cast<char*>(destination);
    usize left = size;
    u32   crc  = 0xFFFFFFFFu;
    while (left != 0)
    {
        constexpr usize Chunk = 1u << 20;
        const usize     count = std::min(left, Chunk);
        if (!read_fully(stream, out, count))
            return LoadStatus::Read;
        crc = update_crc(crc, out, count);
        out += count;
        left -= count;
    }
    return (crc ^ 0xFFFFFFFFu) == section.crc32 ? LoadStatus::Ok : LoadStatus::Crc;
}
#endif

#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
static LoadStatus check_crc(std::istream& stream, const Section& section) {
    if (!seek_to(stream, section.offset))
        return LoadStatus::Seek;

    std::array<char, 4096> buffer{};
    u64                    left = section.size;
    u32                    crc  = 0xFFFFFFFFu;
    while (left != 0)
    {
        const usize count = static_cast<usize>(std::min<u64>(left, buffer.size()));
        if (!read_fully(stream, buffer.data(), count))
            return LoadStatus::Read;
        crc = update_crc(crc, buffer.data(), count);
        left -= count;
    }
    return (crc ^ 0xFFFFFFFFu) == section.crc32 ? LoadStatus::Ok : LoadStatus::Crc;
}
#endif

static bool named(const Section& section, const char (&expected)[5]) {
    return std::memcmp(section.name, expected, 4) == 0;
}

class MemoryViewBuf final : public std::streambuf {
   public:
    void reset(char* data, usize size) {
        begin = data;
        end   = data + size;
        setg(begin, begin, end);
    }

   protected:
    pos_type seekoff(off_type offset, std::ios_base::seekdir direction,
                     std::ios_base::openmode mode) override {
        if (!(mode & std::ios_base::in) || begin == nullptr)
            return pos_type(off_type(-1));
        off_type base = 0;
        if (direction == std::ios_base::cur)
            base = gptr() - begin;
        else if (direction == std::ios_base::end)
            base = end - begin;
        const off_type next = base + offset;
        if (next < 0 || next > end - begin)
            return pos_type(off_type(-1));
        setg(begin, begin + next, end);
        return pos_type(next);
    }

    pos_type seekpos(pos_type position, std::ios_base::openmode mode) override {
        return seekoff(off_type(position), std::ios_base::beg, mode);
    }

   private:
    char* begin = nullptr;
    char* end   = nullptr;
};

class PhysicalMapping final {
   public:
    ~PhysicalMapping() {
        if (data != MAP_FAILED)
            munmap(data, bytes);
        if (fd >= 0)
            close(fd);
    }

    bool open_at(u64 address, usize length) {
        return open_physical(address, length, true);
    }

    bool open_cached_at(u64 address, usize length) {
        return open_physical(address, length, false);
    }

    bool open_file(const fs::path& path) {
        struct stat status{};
        const std::string requested = "file:" + path.string();
        if (data != MAP_FAILED)
            return key == requested;
        fd = open(path.c_str(), O_RDONLY);
        if (fd < 0 || fstat(fd, &status) != 0 || status.st_size <= 0)
            return false;
        bytes = static_cast<usize>(status.st_size);
        data  = mmap(nullptr, bytes, PROT_READ, MAP_SHARED, fd, 0);
        if (data == MAP_FAILED)
            return false;
        key = requested;
        return true;
    }

    char* begin() const { return static_cast<char*>(data); }
    usize size() const { return bytes; }

   private:
    bool open_physical(u64 address, usize length, bool uncached) {
        if ((address & 4095u) != 0u || length == 0)
            return false;
        const std::string requested = std::string(uncached ? "uncached:" : "cached:")
                                    + std::to_string(address) + ":" + std::to_string(length);
        if (data != MAP_FAILED)
            return key == requested;
        fd = open("/dev/mem", uncached ? O_RDONLY | O_SYNC : O_RDONLY);
        if (fd < 0)
            return false;
        bytes = length;
        data  = mmap(nullptr, bytes, PROT_READ, MAP_SHARED, fd,
                    static_cast<off_t>(address));
        if (data == MAP_FAILED)
            return false;
        key = requested;
        return true;
    }

    int         fd    = -1;
    void*       data  = MAP_FAILED;
    usize       bytes = 0;
    std::string key;
};

#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
static PhysicalMapping& persistent_view_mapping() {
    static PhysicalMapping mapping;
    return mapping;
}
#endif

static bool parse_memory_path(const fs::path& path, u64& address, usize& bytes) {
    constexpr const char Prefix[] = "pff1-mem:";
    const std::string text = path.string();
    if (text.compare(0, sizeof(Prefix) - 1, Prefix) != 0)
        return false;
    const char* cursor = text.c_str() + sizeof(Prefix) - 1;
    char*       end    = nullptr;
    errno              = 0;
    address            = std::strtoull(cursor, &end, 0);
    if (errno != 0 || end == cursor || *end != ':')
        return false;
    cursor = end + 1;
    errno  = 0;
    const unsigned long long parsedBytes = std::strtoull(cursor, &end, 0);
    if (errno != 0 || end == cursor || *end != '\0' || parsedBytes == 0
        || parsedBytes > std::numeric_limits<usize>::max())
        return false;
    bytes = static_cast<usize>(parsedBytes);
    return true;
}

static bool parse_view_path(const fs::path& path, u64& address, usize& bytes) {
    constexpr const char Prefix[] = "pff1-view:";
    const std::string text = path.string();
    if (text.compare(0, sizeof(Prefix) - 1, Prefix) != 0)
        return false;
    const char* cursor = text.c_str() + sizeof(Prefix) - 1;
    char*       end    = nullptr;
    errno              = 0;
    address            = std::strtoull(cursor, &end, 0);
    if (errno != 0 || end == cursor || *end != ':')
        return false;
    cursor = end + 1;
    errno  = 0;
    const unsigned long long parsedBytes = std::strtoull(cursor, &end, 0);
    if (errno != 0 || end == cursor || *end != '\0' || parsedBytes == 0
        || parsedBytes > std::numeric_limits<usize>::max())
        return false;
    bytes = static_cast<usize>(parsedBytes);
    return true;
}

}  // namespace FlatPff1

std::optional<std::string> Network::load_flat(const fs::path& path) {
    using namespace FlatPff1;

    const auto loadStarted = std::chrono::steady_clock::now();
    const auto reportStage = [&loadStarted](const char* stage) {
        const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now() - loadStarted);
        sync_cout << "info string PIKAFISH_PFF1_STAGE stage=" << stage
                  << " elapsed_ms=" << elapsed.count() << sync_endl;
    };

#if !defined(PIKAFISH_PFF1_DIRECT_VIEW)
    std::ifstream    fileStream;
    PhysicalMapping  temporaryMapping;
#endif
    MemoryViewBuf    memoryBuffer;
    std::istream     memoryStream(&memoryBuffer);
    std::istream*    source        = nullptr;
#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
    char*            directBase    = nullptr;
#endif
    u64              memoryAddress = 0;
    usize            memoryBytes   = 0;
    const bool       memoryPath    = parse_memory_path(path, memoryAddress, memoryBytes);
    u64              viewAddress   = 0;
    usize            viewBytes     = 0;
    const bool       viewPath      = parse_view_path(path, viewAddress, viewBytes);

    if (memoryPath)
    {
#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
        PhysicalMapping& mapping = persistent_view_mapping();
#else
        PhysicalMapping& mapping = temporaryMapping;
#endif
        if (!mapping.open_at(memoryAddress, memoryBytes))
        {
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=mmap reason=open"
                      << sync_endl;
            return std::nullopt;
        }
        memoryBuffer.reset(mapping.begin(), memoryBytes);
        memoryStream.clear();
        source = &memoryStream;
        sync_cout << "info string PIKAFISH_PFF1_MMAP address=" << memoryAddress
                  << " bytes=" << memoryBytes << sync_endl;
#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
        directBase = mapping.begin();
#endif
    }
    else if (viewPath)
    {
#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
        PhysicalMapping& mapping = persistent_view_mapping();
        if (!mapping.open_cached_at(viewAddress, viewBytes))
        {
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=mmap-cached reason=open"
                      << sync_endl;
            return std::nullopt;
        }
        memoryBuffer.reset(mapping.begin(), viewBytes);
        memoryStream.clear();
        source     = &memoryStream;
        directBase = mapping.begin();
        memoryBytes = viewBytes;
        sync_cout << "info string PIKAFISH_PFF1_VIEW_MMAP physical=" << viewAddress
                  << " bytes=" << viewBytes << " cacheable=1" << sync_endl;
#else
        sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=view reason=unsupported"
                  << sync_endl;
        return std::nullopt;
#endif
    }
    else
    {
#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
        PhysicalMapping& mapping = persistent_view_mapping();
        if (!mapping.open_file(path))
            return std::nullopt;
        memoryBuffer.reset(mapping.begin(), mapping.size());
        memoryStream.clear();
        source      = &memoryStream;
        directBase  = mapping.begin();
        memoryBytes = mapping.size();
        sync_cout << "info string PIKAFISH_PFF1_VIEW_FILE bytes=" << memoryBytes
                  << sync_endl;
#else
        fileStream.open(path, std::ios_base::binary);
        if (!fileStream)
            return std::nullopt;
        source = &fileStream;
#endif
    }
    reportStage("source-ready");
    std::istream& stream = *source;

    std::array<char, HeaderBytes> header{};
    if (!read_fully(stream, header.data(), header.size()))
    {
        sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=header reason=read"
                  << sync_endl;
        return std::nullopt;
    }
    reportStage("header-ready");

    const u16 endianProbe = 1;
    if (*reinterpret_cast<const unsigned char*>(&endianProbe) != 1u
        || std::memcmp(header.data(), "PFF1", 4) != 0
        || get_u32(header.data() + 4) != 0x00010000u
        || get_u32(header.data() + 8) != HeaderBytes
        || get_u32(header.data() + 12) != Flags
        || get_u32(header.data() + 16) != Version
        || get_u32(header.data() + 20) != Network::hash
        || get_u32(header.data() + 24) != FeatureTransformer::get_hash_value()
        || get_u32(header.data() + 28) != NetworkArchitecture::get_hash_value()
        || get_u16(header.data() + 32) != L1 || get_u16(header.data() + 34) != L2
        || get_u16(header.data() + 36) != L3
        || get_u16(header.data() + 38) != LayerStacks
        || get_u32(header.data() + 40) != FeatureTransformer::PsqDimensions
        || get_u32(header.data() + 44) != FeatureTransformer::ThreatInputDimensions
        || get_u32(header.data() + 48) != PSQTBuckets
        || get_u32(header.data() + 52) != SectionCount || get_u32(header.data() + 68) != 0u)
    {
        sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=header reason=metadata"
                  << sync_endl;
        return std::nullopt;
    }

    constexpr u32 MlpStackBytes =
      L2 * sizeof(i32) + L2 * L1 * sizeof(i8) + L3 * sizeof(i32)
      + L3 * (L2 * 2) * sizeof(i8) + sizeof(i32) + (L2 * 2 + L3 * 2) * sizeof(i8);
    if (get_u32(header.data() + 64) != MlpStackBytes)
    {
        sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=header reason=mlp-size"
                  << sync_endl;
        return std::nullopt;
    }

    const u64 fileBytes = get_u64(header.data() + 56);
    stream.seekg(0, std::ios_base::end);
    const std::streamoff actualBytes = stream.tellg();
    if (actualBytes < 0 || static_cast<u64>(actualBytes) != fileBytes)
    {
        sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=file reason=size"
                  << sync_endl;
        return std::nullopt;
    }

    std::array<Section, SectionCount> sections{};
    u64                               previousEnd = HeaderBytes;
    for (u32 i = 0; i < SectionCount; ++i)
    {
        const char* descriptor = header.data() + 104 + i * 32;
        std::memcpy(sections[i].name, descriptor, 4);
        if (get_u32(descriptor + 4) != 0u || get_u32(descriptor + 28) != 0u)
        {
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=sections reason=reserved"
                      << sync_endl;
            return std::nullopt;
        }
        sections[i].offset = get_u64(descriptor + 8);
        sections[i].size   = get_u64(descriptor + 16);
        sections[i].crc32  = get_u32(descriptor + 24);
        if ((sections[i].offset & 4095u) != 0u || sections[i].offset < previousEnd
            || sections[i].offset > fileBytes
            || sections[i].size > fileBytes - sections[i].offset)
        {
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=sections reason=layout"
                      << sync_endl;
            return std::nullopt;
        }
        previousEnd = sections[i].offset + sections[i].size;
    }
    if (previousEnd != fileBytes || !named(sections[0], "FTBI")
        || sections[0].size != FeatureTransformer::BiasesBytes
        || !named(sections[1], "FTTW")
        || sections[1].size != FeatureTransformer::ThreatWeightsBytes
        || !named(sections[2], "FTTP")
        || sections[2].size != FeatureTransformer::ThreatPsqtWeightsBytes
        || !named(sections[3], "FTPW")
        || sections[3].size != FeatureTransformer::WeightsBytes
        || !named(sections[4], "FTPP")
        || sections[4].size != FeatureTransformer::PsqtWeightsBytes
        || !named(sections[5], "MLPS")
        || sections[5].size != static_cast<u64>(LayerStacks) * MlpStackBytes)
    {
        sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=sections reason=contract"
                  << sync_endl;
        return std::nullopt;
    }
    reportStage("layout-ready");

    sync_cout << "info string PIKAFISH_PFF1_LOAD bytes=" << fileBytes << sync_endl;

    const auto reportSection = [](const Section& section, LoadStatus status) {
        const std::string name(section.name, sizeof(section.name));
        if (status == LoadStatus::Ok)
            sync_cout << "info string PIKAFISH_PFF1_SECTION_READY name=" << name
                      << " bytes=" << section.size << sync_endl;
        else
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=" << name
                      << " reason=" << load_status_name(status) << sync_endl;
        return status == LoadStatus::Ok;
    };

#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
    if (!viewPath
        && (!reportSection(sections[0], check_crc(stream, sections[0]))
            || !reportSection(sections[1], check_crc(stream, sections[1]))
            || !reportSection(sections[2], check_crc(stream, sections[2]))
            || !reportSection(sections[3], check_crc(stream, sections[3]))
            || !reportSection(sections[4], check_crc(stream, sections[4]))))
        return std::nullopt;
    if (viewPath)
    {
        sync_cout << "info string PIKAFISH_PFF1_FEATURE_CRC_SKIPPED bytes="
                  << sections[0].size + sections[1].size + sections[2].size
                       + sections[3].size + sections[4].size
                  << " reason=sd-crc16-host-verified" << sync_endl;
        reportStage("feature-crc-skipped");
    }
    else
        reportStage("feature-crc-ready");

    if (directBase == nullptr
        || !featureTransformer.biases.bind(directBase + sections[0].offset,
                                            sections[0].size)
        || !featureTransformer.threatWeights.bind(directBase + sections[1].offset,
                                                   sections[1].size)
        || !featureTransformer.threatPsqtWeights.bind(directBase + sections[2].offset,
                                                       sections[2].size)
        || !featureTransformer.weights.bind(directBase + sections[3].offset,
                                             sections[3].size)
        || !featureTransformer.psqtWeights.bind(directBase + sections[4].offset,
                                                 sections[4].size))
    {
        sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=view-bind reason=alignment"
                  << sync_endl;
        return std::nullopt;
    }
    sync_cout << "info string PIKAFISH_PFF1_VIEW_READY direct_bytes="
              << FeatureTransformer::BiasesBytes + FeatureTransformer::ThreatWeightsBytes
                   + FeatureTransformer::ThreatPsqtWeightsBytes
                   + FeatureTransformer::WeightsBytes + FeatureTransformer::PsqtWeightsBytes
              << " mlp_direct_bytes=" << sections[5].size << sync_endl;
    reportStage("view-bind-ready");
#if defined(PIKAFISH_STAGEA_ACCEL)
    if(viewPath)
        StageAAccel::bind_gather_model(directBase+sections[1].offset,sections[1].size,
            viewAddress+sections[1].offset,directBase+sections[3].offset,sections[3].size,
            viewAddress+sections[3].offset);
#endif
#else
    if (!reportSection(sections[0],
                       read_and_crc(stream, sections[0], featureTransformer.biases.data(),
                                    FeatureTransformer::BiasesBytes))
        || !reportSection(sections[1],
                          read_and_crc(stream, sections[1],
                                       featureTransformer.threatWeights.data(),
                                       FeatureTransformer::ThreatWeightsBytes))
        || !reportSection(sections[2],
                          read_and_crc(stream, sections[2],
                                       featureTransformer.threatPsqtWeights.data(),
                                       FeatureTransformer::ThreatPsqtWeightsBytes))
        || !reportSection(sections[3],
                          read_and_crc(stream, sections[3], featureTransformer.weights.data(),
                                       FeatureTransformer::WeightsBytes))
        || !reportSection(sections[4],
                          read_and_crc(stream, sections[4],
                                       featureTransformer.psqtWeights.data(),
                                       FeatureTransformer::PsqtWeightsBytes)))
        return std::nullopt;

    featureTransformer.permute_weights();
    reportStage("copy-ready");
#endif
#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
    const char* mlpsBegin = directBase + sections[5].offset;
    const char* mlpsEnd   = mlpsBegin + sections[5].size;
    const u32 mlpsCrc = update_crc(0xFFFFFFFFu, mlpsBegin,
                                   static_cast<usize>(sections[5].size))
                      ^ 0xFFFFFFFFu;
#else
    std::string mlps(static_cast<usize>(sections[5].size), '\0');
    if (!seek_to(stream, sections[5].offset)
        || !read_fully(stream, mlps.data(), mlps.size()))
    {
        sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=MLPS-COPY reason=read"
                  << sync_endl;
        return std::nullopt;
    }
    const u32 mlpsCrc = update_crc(0xFFFFFFFFu, mlps.data(), mlps.size()) ^ 0xFFFFFFFFu;
#endif
    if (!reportSection(sections[5],
                       mlpsCrc == sections[5].crc32 ? LoadStatus::Ok : LoadStatus::Crc))
        return std::nullopt;
    reportStage("mlps-crc-ready");
#if defined(PIKAFISH_PFF1_DIRECT_VIEW)
    const char* mlpCursor = mlpsBegin;
    for (usize i = 0; i < LayerStacks; ++i)
    {
        if (!network[i].read_parameters_flat(mlpCursor, mlpsEnd))
        {
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=MLPS-PARSE stack="
                      << i << " reason=read" << sync_endl;
            return std::nullopt;
        }
        const u64 expected = (static_cast<u64>(i) + 1u) * MlpStackBytes;
        if (static_cast<u64>(mlpCursor - mlpsBegin) != expected)
        {
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=MLPS-PARSE stack="
                      << i << " reason=position" << sync_endl;
            return std::nullopt;
        }
        sync_cout << "info string PIKAFISH_PFF1_MLPS_STACK_READY stack=" << i
                  << " bytes=" << expected << sync_endl;
    }
#else
    std::istringstream mlpStream(mlps, std::ios_base::in | std::ios_base::binary);
    for (usize i = 0; i < LayerStacks; ++i)
    {
        if (!network[i].read_parameters(mlpStream))
        {
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=MLPS-PARSE stack="
                      << i << " reason=read" << sync_endl;
            return std::nullopt;
        }
        const std::streamoff position = mlpStream.tellg();
        const u64 expected = (static_cast<u64>(i) + 1u) * MlpStackBytes;
        if (position < 0 || static_cast<u64>(position) != expected)
        {
            sync_cout << "info string PIKAFISH_PFF1_LOAD_FAILED stage=MLPS-PARSE stack="
                      << i << " reason=position" << sync_endl;
            return std::nullopt;
        }
    }
#endif
    reportStage("mlps-ready");

#if defined(PIKAFISH_STAGEB_ACCEL)
    StageBAccel::ModelBinding stageBBinding{};
    std::memcpy(stageBBinding.decodedStreamSha256, header.data() + 72,
                sizeof(stageBBinding.decodedStreamSha256));
    stageBBinding.mlpsBytes = static_cast<u32>(sections[5].size);
    stageBBinding.mlpsCrc32 = sections[5].crc32;
    StageBAccel::prepare(stageBBinding);
    reportStage("stageb-prepare");
#endif

    initialize();
    sync_cout << "info string PIKAFISH_PFF1_READY bytes=" << fileBytes << sync_endl;
    reportStage("ready");
    return std::make_optional(std::string("PFF1 fully decoded official NNUE"));
}
