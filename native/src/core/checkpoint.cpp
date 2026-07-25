#include "macro_sim/core/checkpoint.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <new>
#include <set>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <flatbuffers/flatbuffers.h>
#include <nlohmann/json.hpp>

#include "macro_sim/core/digest.hpp"
#include "macro_sim/core/invariants.hpp"
#include "macro_sim/version.hpp"
#include "picosha2.h"

namespace macro_sim::core {
namespace {

using ByteVector = std::vector<std::uint8_t>;
using Json = nlohmann::json;

constexpr std::string_view kStateEntryName = "arrays/m2-root-state.npy";
constexpr std::string_view kMetadataEntryName = "metadata.json";
constexpr std::string_view kManifestEntryName = "manifest.fb";
constexpr std::string_view kPayloadKind = "m2-root-state-v1";
constexpr std::array<std::string_view, 4> kRequiredFeatures{
    "canonical-json-v1",
    "m2-state-array-v1",
    "npy-v2",
    "sha256",
};

[[nodiscard]] Status corrupt(const char* message) noexcept {
    return Status(ErrorCode::corrupt_input, message);
}

[[nodiscard]] std::array<std::uint8_t, 32> sha256(
    std::span<const std::uint8_t> bytes
) noexcept {
    return sha256_digest(bytes).bytes;
}

[[nodiscard]] std::string hex(
    const std::array<std::uint8_t, 32>& digest
) {
    constexpr char digits[] = "0123456789abcdef";
    std::string output(digest.size() * 2, '0');
    for (std::size_t index = 0; index < digest.size(); ++index) {
        output[index * 2] = digits[digest[index] >> 4U];
        output[index * 2 + 1] = digits[digest[index] & 0x0FU];
    }
    return output;
}

class BinaryWriter final {
public:
    void u8(std::uint8_t value) {
        bytes_.push_back(value);
    }

    void boolean(bool value) {
        u8(value ? 1U : 0U);
    }

    void u32(std::uint32_t value) {
        for (int shift = 24; shift >= 0; shift -= 8) {
            u8(static_cast<std::uint8_t>(value >> shift));
        }
    }

    void u64(std::uint64_t value) {
        for (int shift = 56; shift >= 0; shift -= 8) {
            u8(static_cast<std::uint8_t>(value >> shift));
        }
    }

    void f64(double value) {
        u64(std::bit_cast<std::uint64_t>(value));
    }

    void raw(std::string_view value) {
        bytes_.insert(bytes_.end(), value.begin(), value.end());
    }

    [[nodiscard]] ByteVector take() && {
        return std::move(bytes_);
    }

private:
    ByteVector bytes_;
};

class BinaryReader final {
public:
    BinaryReader(
        std::span<const std::uint8_t> bytes,
        const CheckpointLimits& limits
    ) noexcept
        : bytes_(bytes), limits_(limits) {}

    [[nodiscard]] Result<std::uint8_t> u8() noexcept {
        if (position_ >= bytes_.size()) {
            return corrupt("state payload is truncated");
        }
        return bytes_[position_++];
    }

    [[nodiscard]] Result<bool> boolean() noexcept {
        const auto value = u8();
        if (!value.ok()) {
            return value.status();
        }
        if (*value.get_if() > 1U) {
            return corrupt("state payload contains an invalid boolean");
        }
        return *value.get_if() == 1U;
    }

    [[nodiscard]] Result<std::uint32_t> u32() noexcept {
        if (remaining() < 4) {
            return corrupt("state payload is truncated");
        }
        std::uint32_t value = 0;
        for (int index = 0; index < 4; ++index) {
            value = static_cast<std::uint32_t>(
                (value << 8U) | bytes_[position_++]
            );
        }
        return value;
    }

    [[nodiscard]] Result<std::uint64_t> u64() noexcept {
        if (remaining() < 8) {
            return corrupt("state payload is truncated");
        }
        std::uint64_t value = 0;
        for (int index = 0; index < 8; ++index) {
            value = (value << 8U) | bytes_[position_++];
        }
        return value;
    }

    [[nodiscard]] Result<double> f64() noexcept {
        const auto bits = u64();
        if (!bits.ok()) {
            return bits.status();
        }
        return std::bit_cast<double>(*bits.get_if());
    }

    [[nodiscard]] Status expect(std::string_view value) noexcept {
        if (remaining() < value.size()
            || std::memcmp(
                bytes_.data() + position_,
                value.data(),
                value.size()
            ) != 0) {
            return corrupt("state payload identity is invalid");
        }
        position_ += value.size();
        return Status::success();
    }

    [[nodiscard]] Result<std::size_t> count() noexcept {
        const auto value = u64();
        if (!value.ok()) {
            return value.status();
        }
        if (*value.get_if() > limits_.maximum_records
            || *value.get_if()
                > static_cast<std::uint64_t>(
                    std::numeric_limits<std::size_t>::max()
                )) {
            return corrupt("state payload record limit is exceeded");
        }
        return static_cast<std::size_t>(*value.get_if());
    }

    [[nodiscard]] bool finished() const noexcept {
        return position_ == bytes_.size();
    }

private:
    [[nodiscard]] std::size_t remaining() const noexcept {
        return bytes_.size() - position_;
    }

    std::span<const std::uint8_t> bytes_;
    const CheckpointLimits& limits_;
    std::size_t position_{0};
};

template <typename Id>
void write_id(BinaryWriter& writer, Id id) {
    writer.u64(id.value());
}

void write_owner(BinaryWriter& writer, OwnerId owner) {
    writer.u8(static_cast<std::uint8_t>(owner.kind));
    writer.u64(owner.value);
}

template <typename Id>
[[nodiscard]] Result<Id> read_id(BinaryReader& reader) noexcept {
    const auto value = reader.u64();
    if (!value.ok()) {
        return value.status();
    }
    if (*value.get_if() >
        static_cast<std::uint64_t>(
            std::numeric_limits<typename Id::rep_type>::max())) {
        return corrupt("state payload ID exceeds the compact ID range");
    }
    return Id(static_cast<typename Id::rep_type>(*value.get_if()));
}

[[nodiscard]] Result<OwnerId> read_owner(BinaryReader& reader) noexcept {
    const auto kind = reader.u8();
    const auto value = reader.u64();
    if (!kind.ok()) {
        return kind.status();
    }
    if (!value.ok()) {
        return value.status();
    }
    if (*kind.get_if() > static_cast<std::uint8_t>(OwnerKind::institution)) {
        return corrupt("state payload contains an unknown owner kind");
    }
    if (*value.get_if() > OwnerId::max_packed_value()) {
        return corrupt("state payload owner exceeds the compact ID range");
    }
    OwnerId owner{
        static_cast<OwnerKind>(*kind.get_if()),
        static_cast<std::uint32_t>(*value.get_if()),
    };
    if (!owner.valid()) {
        return corrupt("state payload contains an invalid owner");
    }
    return owner;
}

template <typename Id, typename Value, typename WriteValue>
void write_slot_store(
    BinaryWriter& writer,
    const SlotStore<Id, Value>& store,
    WriteValue&& write_value
) {
    const auto allocator = store.allocator_state();
    writer.u64(allocator.next_id);
    writer.u64(allocator.next_sequence);
    writer.u64(allocator.free_slots.size());
    for (const auto index : allocator.free_slots) {
        writer.u32(index);
    }
    writer.u64(store.slots().size());
    for (const auto& slot : store.slots()) {
        write_id(writer, slot.id);
        writer.u32(slot.generation);
        writer.u64(slot.sequence);
        writer.boolean(slot.value.has_value());
        if (slot.value.has_value()) {
            write_value(writer, *slot.value);
        }
    }
    writer.u64(store.iteration_order().size());
    for (const auto id : store.iteration_order()) {
        write_id(writer, id);
    }
}

template <typename Enum>
[[nodiscard]] Result<Enum> read_enum(
    BinaryReader& reader,
    std::uint8_t maximum
) noexcept {
    const auto value = reader.u8();
    if (!value.ok()) {
        return value.status();
    }
    if (*value.get_if() > maximum) {
        return corrupt("state payload contains an unknown enum value");
    }
    return static_cast<Enum>(*value.get_if());
}

[[nodiscard]] ByteVector make_npy(std::span<const std::uint8_t> payload) {
    constexpr std::array<std::uint8_t, 8> prefix{
        0x93U, 'N', 'U', 'M', 'P', 'Y', 2U, 0U,
    };
    std::string header =
        "{'descr': '|u1', 'fortran_order': False, 'shape': ("
        + std::to_string(payload.size()) + ",), }";
    constexpr std::size_t preamble_size = 12;
    const auto padding =
        (64 - ((preamble_size + header.size() + 1) % 64)) % 64;
    header.append(padding, ' ');
    header.push_back('\n');
    if (header.size() > std::numeric_limits<std::uint32_t>::max()) {
        throw std::length_error("NPY header is too large");
    }

    ByteVector output;
    output.reserve(preamble_size + header.size() + payload.size());
    output.insert(output.end(), prefix.begin(), prefix.end());
    const auto length = static_cast<std::uint32_t>(header.size());
    for (int shift = 0; shift <= 24; shift += 8) {
        output.push_back(static_cast<std::uint8_t>(length >> shift));
    }
    output.insert(output.end(), header.begin(), header.end());
    output.insert(output.end(), payload.begin(), payload.end());
    return output;
}

[[nodiscard]] Result<ByteVector> parse_npy(
    std::span<const std::uint8_t> encoded,
    const CheckpointLimits& limits
) {
    constexpr std::array<std::uint8_t, 8> prefix{
        0x93U, 'N', 'U', 'M', 'P', 'Y', 2U, 0U,
    };
    if (encoded.size() < 12
        || !std::equal(prefix.begin(), prefix.end(), encoded.begin())) {
        return corrupt("NPY 2.0 identity is invalid");
    }
    std::uint32_t header_size = 0;
    for (std::size_t index = 0; index < 4; ++index) {
        header_size |= static_cast<std::uint32_t>(encoded[8 + index])
            << static_cast<unsigned>(index * 8);
    }
    const std::size_t data_offset = 12U + header_size;
    if (data_offset > encoded.size()) {
        return corrupt("NPY 2.0 header is truncated");
    }
    const auto payload_size = encoded.size() - data_offset;
    if (payload_size > limits.maximum_entry_bytes) {
        return corrupt("NPY payload limit is exceeded");
    }
    ByteVector payload(
        encoded.begin() + static_cast<std::ptrdiff_t>(data_offset),
        encoded.end()
    );
    if (make_npy(payload) != ByteVector(encoded.begin(), encoded.end())) {
        return corrupt("NPY 2.0 encoding is not canonical");
    }
    return payload;
}

[[nodiscard]] std::uint32_t crc32(
    std::span<const std::uint8_t> bytes
) noexcept {
    std::uint32_t crc = 0xffffffffU;
    for (const auto byte : bytes) {
        crc ^= byte;
        for (int bit = 0; bit < 8; ++bit) {
            const auto mask =
                static_cast<std::uint32_t>(-(static_cast<int>(crc & 1U)));
            crc = (crc >> 1U) ^ (0xedb88320U & mask);
        }
    }
    return ~crc;
}

void append_le16(ByteVector& output, std::uint16_t value) {
    output.push_back(static_cast<std::uint8_t>(value));
    output.push_back(static_cast<std::uint8_t>(value >> 8U));
}

void append_le32(ByteVector& output, std::uint32_t value) {
    for (int shift = 0; shift <= 24; shift += 8) {
        output.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

[[nodiscard]] Result<std::uint16_t> read_le16(
    std::span<const std::uint8_t> bytes,
    std::size_t offset
) noexcept {
    if (offset > bytes.size() || bytes.size() - offset < 2) {
        return corrupt("ZIP structure is truncated");
    }
    return static_cast<std::uint16_t>(
        bytes[offset] | (static_cast<std::uint16_t>(bytes[offset + 1]) << 8U)
    );
}

[[nodiscard]] Result<std::uint32_t> read_le32(
    std::span<const std::uint8_t> bytes,
    std::size_t offset
) noexcept {
    if (offset > bytes.size() || bytes.size() - offset < 4) {
        return corrupt("ZIP structure is truncated");
    }
    std::uint32_t value = 0;
    for (std::size_t index = 0; index < 4; ++index) {
        value |= static_cast<std::uint32_t>(bytes[offset + index])
            << static_cast<unsigned>(index * 8);
    }
    return value;
}

struct ArchiveEntry final {
    std::string name;
    ByteVector bytes;
};

[[nodiscard]] Result<ByteVector> make_zip(
    const std::vector<ArchiveEntry>& entries
) {
    struct CentralRecord final {
        const ArchiveEntry* entry{nullptr};
        std::uint32_t crc{0};
        std::uint32_t local_offset{0};
    };

    ByteVector output;
    std::vector<CentralRecord> central;
    central.reserve(entries.size());
    for (const auto& entry : entries) {
        if (entry.name.size() > std::numeric_limits<std::uint16_t>::max()
            || entry.bytes.size() > std::numeric_limits<std::uint32_t>::max()
            || output.size() > std::numeric_limits<std::uint32_t>::max()) {
            return Status(ErrorCode::out_of_range, "ZIP32 limit is exceeded");
        }
        const auto checksum = crc32(entry.bytes);
        central.push_back(
            {
                &entry,
                checksum,
                static_cast<std::uint32_t>(output.size()),
            }
        );
        append_le32(output, 0x04034b50U);
        append_le16(output, 20);
        append_le16(output, 0);
        append_le16(output, 0);
        append_le16(output, 0);
        append_le16(output, 0);
        append_le32(output, checksum);
        append_le32(output, static_cast<std::uint32_t>(entry.bytes.size()));
        append_le32(output, static_cast<std::uint32_t>(entry.bytes.size()));
        append_le16(output, static_cast<std::uint16_t>(entry.name.size()));
        append_le16(output, 0);
        output.insert(output.end(), entry.name.begin(), entry.name.end());
        output.insert(output.end(), entry.bytes.begin(), entry.bytes.end());
    }

    if (output.size() > std::numeric_limits<std::uint32_t>::max()
        || central.size() > std::numeric_limits<std::uint16_t>::max()) {
        return Status(ErrorCode::out_of_range, "ZIP32 limit is exceeded");
    }
    const auto central_offset = static_cast<std::uint32_t>(output.size());
    for (const auto& record : central) {
        const auto& entry = *record.entry;
        append_le32(output, 0x02014b50U);
        append_le16(output, 20);
        append_le16(output, 20);
        append_le16(output, 0);
        append_le16(output, 0);
        append_le16(output, 0);
        append_le16(output, 0);
        append_le32(output, record.crc);
        append_le32(output, static_cast<std::uint32_t>(entry.bytes.size()));
        append_le32(output, static_cast<std::uint32_t>(entry.bytes.size()));
        append_le16(output, static_cast<std::uint16_t>(entry.name.size()));
        append_le16(output, 0);
        append_le16(output, 0);
        append_le16(output, 0);
        append_le16(output, 0);
        append_le32(output, 0);
        append_le32(output, record.local_offset);
        output.insert(output.end(), entry.name.begin(), entry.name.end());
    }
    const auto central_size =
        static_cast<std::uint32_t>(output.size() - central_offset);
    append_le32(output, 0x06054b50U);
    append_le16(output, 0);
    append_le16(output, 0);
    append_le16(output, static_cast<std::uint16_t>(central.size()));
    append_le16(output, static_cast<std::uint16_t>(central.size()));
    append_le32(output, central_size);
    append_le32(output, central_offset);
    append_le16(output, 0);
    return output;
}

[[nodiscard]] bool safe_entry_name(std::string_view name) noexcept {
    return !name.empty() && name.front() != '/'
        && name.find('\\') == std::string_view::npos
        && name.find("../") == std::string_view::npos && name != ".."
        && name.find("/..") == std::string_view::npos;
}

[[nodiscard]] Result<std::vector<ArchiveEntry>> parse_zip(
    std::span<const std::uint8_t> archive,
    const CheckpointLimits& limits
) {
    if (archive.size() > limits.maximum_archive_bytes) {
        return corrupt("checkpoint archive limit is exceeded");
    }
    if (archive.size() < 22) {
        return corrupt("ZIP end record is absent");
    }
    const auto eocd = archive.size() - 22;
    const auto signature = read_le32(archive, eocd);
    const auto disk = read_le16(archive, eocd + 4);
    const auto central_disk = read_le16(archive, eocd + 6);
    const auto disk_entries = read_le16(archive, eocd + 8);
    const auto total_entries = read_le16(archive, eocd + 10);
    const auto central_size = read_le32(archive, eocd + 12);
    const auto central_offset = read_le32(archive, eocd + 16);
    const auto comment_size = read_le16(archive, eocd + 20);
    if (!signature.ok() || !disk.ok() || !central_disk.ok()
        || !disk_entries.ok() || !total_entries.ok() || !central_size.ok()
        || !central_offset.ok() || !comment_size.ok()) {
        return corrupt("ZIP end record is truncated");
    }
    if (*signature.get_if() != 0x06054b50U || *disk.get_if() != 0
        || *central_disk.get_if() != 0
        || *disk_entries.get_if() != *total_entries.get_if()
        || *comment_size.get_if() != 0
        || *total_entries.get_if() > limits.maximum_entries
        || static_cast<std::size_t>(*central_offset.get_if())
                + *central_size.get_if()
            != eocd) {
        return corrupt("ZIP end record is invalid");
    }

    std::vector<ArchiveEntry> entries;
    entries.reserve(*total_entries.get_if());
    std::set<std::string> names;
    std::size_t cursor = *central_offset.get_if();
    for (std::size_t index = 0; index < *total_entries.get_if(); ++index) {
        const auto central_signature = read_le32(archive, cursor);
        const auto flags = read_le16(archive, cursor + 8);
        const auto method = read_le16(archive, cursor + 10);
        const auto checksum = read_le32(archive, cursor + 16);
        const auto compressed = read_le32(archive, cursor + 20);
        const auto uncompressed = read_le32(archive, cursor + 24);
        const auto name_size = read_le16(archive, cursor + 28);
        const auto extra_size = read_le16(archive, cursor + 30);
        const auto entry_comment = read_le16(archive, cursor + 32);
        const auto local_offset = read_le32(archive, cursor + 42);
        if (!central_signature.ok() || !flags.ok() || !method.ok()
            || !checksum.ok() || !compressed.ok() || !uncompressed.ok()
            || !name_size.ok() || !extra_size.ok() || !entry_comment.ok()
            || !local_offset.ok()) {
            return corrupt("ZIP central directory is truncated");
        }
        const std::size_t record_size =
            46U + *name_size.get_if() + *extra_size.get_if()
            + *entry_comment.get_if();
        if (*central_signature.get_if() != 0x02014b50U
            || *flags.get_if() != 0 || *method.get_if() != 0
            || *compressed.get_if() != *uncompressed.get_if()
            || *uncompressed.get_if() > limits.maximum_entry_bytes
            || cursor > eocd || record_size > eocd - cursor) {
            return corrupt("ZIP central directory record is invalid");
        }
        const std::string name(
            reinterpret_cast<const char*>(archive.data() + cursor + 46),
            *name_size.get_if()
        );
        if (!safe_entry_name(name) || !names.insert(name).second) {
            return corrupt("ZIP entry path is unsafe or duplicated");
        }

        const std::size_t local = *local_offset.get_if();
        const auto local_signature = read_le32(archive, local);
        const auto local_flags = read_le16(archive, local + 6);
        const auto local_method = read_le16(archive, local + 8);
        const auto local_crc = read_le32(archive, local + 14);
        const auto local_compressed = read_le32(archive, local + 18);
        const auto local_uncompressed = read_le32(archive, local + 22);
        const auto local_name_size = read_le16(archive, local + 26);
        const auto local_extra_size = read_le16(archive, local + 28);
        if (!local_signature.ok() || !local_flags.ok() || !local_method.ok()
            || !local_crc.ok() || !local_compressed.ok()
            || !local_uncompressed.ok() || !local_name_size.ok()
            || !local_extra_size.ok()) {
            return corrupt("ZIP local record is truncated");
        }
        const std::size_t data_offset =
            local + 30U + *local_name_size.get_if()
            + *local_extra_size.get_if();
        if (*local_signature.get_if() != 0x04034b50U
            || *local_flags.get_if() != 0 || *local_method.get_if() != 0
            || *local_crc.get_if() != *checksum.get_if()
            || *local_compressed.get_if() != *compressed.get_if()
            || *local_uncompressed.get_if() != *uncompressed.get_if()
            || *local_name_size.get_if() != *name_size.get_if()
            || data_offset > *central_offset.get_if()
            || *compressed.get_if()
                > *central_offset.get_if() - data_offset) {
            return corrupt("ZIP local record is invalid");
        }
        const std::string local_name(
            reinterpret_cast<const char*>(
                archive.data() + local + 30U
            ),
            *local_name_size.get_if()
        );
        if (local_name != name) {
            return corrupt("ZIP local and central names differ");
        }
        ByteVector data(
            archive.begin() + static_cast<std::ptrdiff_t>(data_offset),
            archive.begin()
                + static_cast<std::ptrdiff_t>(
                    data_offset + *compressed.get_if()
                )
        );
        if (crc32(data) != *checksum.get_if()) {
            return corrupt("ZIP entry checksum does not match");
        }
        entries.push_back({name, std::move(data)});
        cursor += record_size;
    }
    if (cursor != eocd) {
        return corrupt("ZIP central directory size does not match");
    }
    return entries;
}

[[nodiscard]] const ByteVector* find_entry(
    const std::vector<ArchiveEntry>& entries,
    std::string_view name
) noexcept {
    const auto found = std::find_if(
        entries.begin(),
        entries.end(),
        [name](const ArchiveEntry& entry) { return entry.name == name; }
    );
    return found == entries.end() ? nullptr : &found->bytes;
}

struct CheckpointEnvelope final : private flatbuffers::Table {
    enum : flatbuffers::voffset_t {
        vt_schema_version = 4,
        vt_canonical_encoding_version = 6,
        vt_engine_version = 8,
        vt_payload_kind = 10,
        vt_payload = 12,
        vt_payload_sha256 = 14,
        vt_required_features = 16,
        vt_extensions_json = 18,
    };

    [[nodiscard]] std::uint32_t schema_version() const {
        return GetField<std::uint32_t>(vt_schema_version, 0);
    }

    [[nodiscard]] std::uint32_t canonical_encoding_version() const {
        return GetField<std::uint32_t>(
            vt_canonical_encoding_version,
            0
        );
    }

    [[nodiscard]] const flatbuffers::String* engine_version() const {
        return GetPointer<const flatbuffers::String*>(vt_engine_version);
    }

    [[nodiscard]] const flatbuffers::String* payload_kind() const {
        return GetPointer<const flatbuffers::String*>(vt_payload_kind);
    }

    [[nodiscard]] const flatbuffers::Vector<std::uint8_t>* payload() const {
        return GetPointer<const flatbuffers::Vector<std::uint8_t>*>(
            vt_payload
        );
    }

    [[nodiscard]] const flatbuffers::Vector<std::uint8_t>*
    payload_sha256() const {
        return GetPointer<const flatbuffers::Vector<std::uint8_t>*>(
            vt_payload_sha256
        );
    }

    [[nodiscard]] const flatbuffers::Vector<
        flatbuffers::Offset<flatbuffers::String>>*
    required_features() const {
        return GetPointer<const flatbuffers::Vector<
            flatbuffers::Offset<flatbuffers::String>>*>(
            vt_required_features
        );
    }

    [[nodiscard]] const flatbuffers::String* extensions_json() const {
        return GetPointer<const flatbuffers::String*>(vt_extensions_json);
    }

    [[nodiscard]] bool Verify(flatbuffers::Verifier& verifier) const {
        return VerifyTableStart(verifier)
            && VerifyField<std::uint32_t>(
                verifier,
                vt_schema_version,
                sizeof(std::uint32_t)
            )
            && VerifyField<std::uint32_t>(
                verifier,
                vt_canonical_encoding_version,
                sizeof(std::uint32_t)
            )
            && VerifyOffset(verifier, vt_engine_version)
            && verifier.VerifyString(engine_version())
            && VerifyOffset(verifier, vt_payload_kind)
            && verifier.VerifyString(payload_kind())
            && VerifyOffset(verifier, vt_payload)
            && verifier.VerifyVector(payload())
            && VerifyOffset(verifier, vt_payload_sha256)
            && verifier.VerifyVector(payload_sha256())
            && VerifyOffset(verifier, vt_required_features)
            && verifier.VerifyVector(required_features())
            && verifier.VerifyVectorOfStrings(required_features())
            && VerifyOffset(verifier, vt_extensions_json)
            && verifier.VerifyString(extensions_json())
            && verifier.EndTable();
    }
};

[[nodiscard]] flatbuffers::Offset<CheckpointEnvelope> create_envelope(
    flatbuffers::FlatBufferBuilder& builder,
    flatbuffers::Offset<flatbuffers::String> engine_version,
    flatbuffers::Offset<flatbuffers::String> payload_kind,
    flatbuffers::Offset<flatbuffers::Vector<std::uint8_t>> payload,
    flatbuffers::Offset<flatbuffers::Vector<std::uint8_t>> payload_digest,
    flatbuffers::Offset<flatbuffers::Vector<
        flatbuffers::Offset<flatbuffers::String>>> features,
    flatbuffers::Offset<flatbuffers::String> extensions
) {
    const auto start = builder.StartTable();
    builder.AddElement<std::uint32_t>(
        CheckpointEnvelope::vt_schema_version,
        kM2CheckpointSchemaVersion,
        0
    );
    builder.AddElement<std::uint32_t>(
        CheckpointEnvelope::vt_canonical_encoding_version,
        kCanonicalEncodingVersion,
        0
    );
    builder.AddOffset(CheckpointEnvelope::vt_engine_version, engine_version);
    builder.AddOffset(CheckpointEnvelope::vt_payload_kind, payload_kind);
    builder.AddOffset(CheckpointEnvelope::vt_payload, payload);
    builder.AddOffset(
        CheckpointEnvelope::vt_payload_sha256,
        payload_digest
    );
    builder.AddOffset(
        CheckpointEnvelope::vt_required_features,
        features
    );
    builder.AddOffset(
        CheckpointEnvelope::vt_extensions_json,
        extensions
    );
    return flatbuffers::Offset<CheckpointEnvelope>(builder.EndTable(start));
}

[[nodiscard]] ByteVector build_manifest(
    std::span<const std::uint8_t> metadata
) {
    flatbuffers::FlatBufferBuilder builder(1024);
    const auto engine =
        builder.CreateString(std::string(macro_sim::engine_version()));
    const auto kind = builder.CreateString(kPayloadKind.data(), kPayloadKind.size());
    const auto payload = builder.CreateVector(metadata.data(), metadata.size());
    const auto payload_digest_value = sha256(metadata);
    const auto payload_digest = builder.CreateVector(
        payload_digest_value.data(),
        payload_digest_value.size()
    );
    std::vector<flatbuffers::Offset<flatbuffers::String>> feature_offsets;
    feature_offsets.reserve(kRequiredFeatures.size());
    for (const auto feature : kRequiredFeatures) {
        feature_offsets.push_back(
            builder.CreateString(feature.data(), feature.size())
        );
    }
    const auto features = builder.CreateVector(feature_offsets);
    const auto extensions = builder.CreateString("{}\n");
    const auto root = create_envelope(
        builder,
        engine,
        kind,
        payload,
        payload_digest,
        features,
        extensions
    );
    builder.Finish(root, "MSCP");
    return ByteVector(
        builder.GetBufferPointer(),
        builder.GetBufferPointer() + builder.GetSize()
    );
}

[[nodiscard]] Status validate_manifest(
    std::span<const std::uint8_t> manifest,
    std::span<const std::uint8_t> metadata
) {
    if (manifest.size() < 8
        || !flatbuffers::BufferHasIdentifier(manifest.data(), "MSCP")) {
        return corrupt("checkpoint manifest identifier is invalid");
    }
    flatbuffers::Verifier verifier(manifest.data(), manifest.size());
    if (!verifier.VerifyBuffer<CheckpointEnvelope>("MSCP")) {
        return corrupt("checkpoint manifest is malformed");
    }
    const auto* envelope =
        flatbuffers::GetRoot<CheckpointEnvelope>(manifest.data());
    if (envelope->schema_version() < kM2CheckpointSchemaVersion
        || envelope->canonical_encoding_version()
            != kCanonicalEncodingVersion
        || envelope->engine_version() == nullptr
        || envelope->engine_version()->size() == 0
        || envelope->payload_kind() == nullptr
        || envelope->payload_kind()->string_view() != kPayloadKind
        || envelope->payload() == nullptr
        || envelope->payload_sha256() == nullptr
        || envelope->payload_sha256()->size() != 32
        || envelope->required_features() == nullptr
        || envelope->extensions_json() == nullptr) {
        return corrupt("checkpoint manifest contract is invalid");
    }
    if (envelope->payload()->size() != metadata.size()
        || !std::equal(
            envelope->payload()->begin(),
            envelope->payload()->end(),
            metadata.begin()
        )) {
        return corrupt("checkpoint manifest metadata does not match");
    }
    const auto expected_digest = sha256(metadata);
    if (!std::equal(
            envelope->payload_sha256()->begin(),
            envelope->payload_sha256()->end(),
            expected_digest.begin()
        )) {
        return corrupt("checkpoint manifest checksum does not match");
    }
    std::vector<std::string_view> features;
    features.reserve(envelope->required_features()->size());
    for (const auto* feature : *envelope->required_features()) {
        if (feature == nullptr) {
            return corrupt("checkpoint required feature is absent");
        }
        features.push_back(feature->string_view());
    }
    if (!std::equal(
            features.begin(),
            features.end(),
            kRequiredFeatures.begin(),
            kRequiredFeatures.end()
        )) {
        return Status(
            ErrorCode::unsupported,
            "checkpoint requires unsupported features"
        );
    }
    const auto extensions = envelope->extensions_json()->string_view();
    if (extensions != "{}\n"
        || !validate_canonical_json(
                std::span<const std::uint8_t>(
                    reinterpret_cast<const std::uint8_t*>(extensions.data()),
                    extensions.size()
                )
            ).ok()) {
        return corrupt("checkpoint extensions are not canonical");
    }
    return Status::success();
}

[[nodiscard]] ByteVector canonical_json(const Json& value) {
    const auto encoded =
        value.dump(-1, ' ', false, Json::error_handler_t::strict) + "\n";
    return ByteVector(encoded.begin(), encoded.end());
}

[[nodiscard]] Status validate_json_value(const Json& value) noexcept {
    if (value.is_number_float()) {
        return corrupt("raw floating-point JSON is forbidden");
    }
    if (value.is_array()) {
        for (const auto& item : value) {
            const auto status = validate_json_value(item);
            if (!status.ok()) {
                return status;
            }
        }
    }
    if (value.is_object()) {
        for (const auto& [key, item] : value.items()) {
            const auto status = validate_json_value(item);
            if (!status.ok()) {
                return status;
            }
            if (!key.empty() && key.front() == '$') {
                if (value.size() != 1 || (key != "$bytes" && key != "$f64")
                    || !item.is_string()) {
                    return corrupt("canonical JSON tag is invalid");
                }
                const auto text = item.get_ref<const std::string&>();
                const std::size_t expected = key == "$bytes" ? 0 : 16;
                if ((key == "$bytes" && text.size() % 2 != 0)
                    || (key == "$f64" && text.size() != expected)
                    || !std::all_of(
                        text.begin(),
                        text.end(),
                        [](char character) {
                            return (character >= '0' && character <= '9')
                                || (character >= 'a' && character <= 'f');
                        }
                    )) {
                    return corrupt("canonical JSON tag payload is invalid");
                }
            }
        }
    }
    return Status::success();
}

}  // namespace

class CheckpointCodec final {
public:
    [[nodiscard]] static ByteVector encode_state(const RootState& state) {
        BinaryWriter writer;
        writer.raw("MSM2");
        writer.u32(1);
        write_id(writer, state.economy);
        writer.u32(state.currency.value());
        writer.u64(state.seed);
        writer.f64(state.genesis_money.value());
        writer.f64(state.accounting_tolerance);

        write_slot_store(
            writer,
            state.households,
            [](BinaryWriter& output, const HouseholdComponent& household) {
                write_id(output, household.primary_account);
            }
        );
        write_slot_store(
            writer,
            state.firms,
            [](BinaryWriter& output, const FirmComponent& firm) {
                output.u8(static_cast<std::uint8_t>(firm.sector));
                write_id(output, firm.primary_account);
                output.f64(firm.goods_inventory.value());
                output.f64(firm.physical_capital.value());
                output.f64(firm.productivity);
            }
        );
        write_slot_store(
            writer,
            state.banks,
            [](BinaryWriter& output, const BankComponent& bank) {
                write_id(output, bank.cash_account);
                write_id(output, bank.settlement_node);
            }
        );

        writer.u64(state.postings.accounts_.size());
        for (const auto& account : state.postings.accounts_) {
            write_id(writer, account.id);
            writer.u8(static_cast<std::uint8_t>(account.key.kind));
            write_id(writer, account.key.economy);
            write_owner(writer, account.key.owner);
            writer.u32(account.key.currency.value());
            write_id(writer, account.key.settlement_node);
            writer.f64(account.balance.value());
            writer.f64(account.roundoff_drift);
            writer.boolean(account.allow_negative);
            writer.boolean(account.open);
        }

        writer.u64(state.reserves.positions_.size());
        for (const auto& reserve : state.reserves.positions_) {
            write_id(writer, reserve.node);
            write_id(writer, reserve.bank);
            writer.f64(reserve.balance.value());
            writer.f64(reserve.roundoff_drift);
        }
        writer.f64(state.reserves.reserve_stock_.value());
        writer.f64(state.reserves.reserve_stock_roundoff_drift_);

        writer.u64(state.loans.loans_.size());
        for (const auto& loan : state.loans.loans_) {
            write_id(writer, loan.id);
            write_id(writer, loan.lender);
            write_owner(writer, loan.borrower);
            write_id(writer, loan.borrower_account);
            writer.f64(loan.principal.value());
            writer.f64(loan.roundoff_drift);
            writer.f64(loan.terms.annual_rate.value());
            writer.u64(loan.terms.originated_tick.value());
            writer.u64(loan.terms.maturity_tick.value());
            writer.boolean(loan.active);
        }

        writer.u64(state.ownership.lots_.size());
        for (const auto& lot : state.ownership.lots_) {
            write_id(writer, lot.id);
            writer.u8(static_cast<std::uint8_t>(lot.asset.kind));
            write_id(writer, lot.asset.economy);
            writer.u64(lot.asset.value);
            write_owner(writer, lot.owner);
            writer.f64(lot.share);
            writer.boolean(lot.active);
        }

        writer.u64(state.named_counters.counters_.size());
        for (const auto& [stream, value] : state.named_counters.counters_) {
            writer.u64(stream);
            writer.u64(value);
        }
        write_id(writer, state.institutions.central_bank_account);
        write_id(writer, state.institutions.dealer_account);
        write_id(writer, state.institutions.rounding_residual_account);
        write_id(writer, state.institutions.treasury_account);
        return std::move(writer).take();
    }

    [[nodiscard]] static Result<RootState> decode_state(
        std::span<const std::uint8_t> bytes,
        const CheckpointLimits& limits
    );

private:
    template <typename Id, typename Value, typename ReadValue>
    [[nodiscard]] static Status read_slot_store(
        BinaryReader& reader,
        SlotStore<Id, Value>& store,
        ReadValue&& read_value
    );
};

template <typename Id, typename Value, typename ReadValue>
Status CheckpointCodec::read_slot_store(
    BinaryReader& reader,
    SlotStore<Id, Value>& store,
    ReadValue&& read_value
) {
    const auto next_id = reader.u64();
    const auto next_sequence = reader.u64();
    const auto free_count = reader.count();
    if (!next_id.ok()) {
        return next_id.status();
    }
    if (!next_sequence.ok()) {
        return next_sequence.status();
    }
    if (!free_count.ok()) {
        return free_count.status();
    }
    if (*next_id.get_if() == 0 || *next_sequence.get_if() == 0) {
        return corrupt("slot allocator counters are invalid");
    }
    std::vector<std::uint32_t> free_slots;
    free_slots.reserve(*free_count.get_if());
    for (std::size_t index = 0; index < *free_count.get_if(); ++index) {
        const auto slot = reader.u32();
        if (!slot.ok()) {
            return slot.status();
        }
        free_slots.push_back(*slot.get_if());
    }
    const auto slot_count = reader.count();
    if (!slot_count.ok()) {
        return slot_count.status();
    }
    std::vector<typename SlotStore<Id, Value>::Slot> slots;
    slots.reserve(*slot_count.get_if());
    for (std::size_t index = 0; index < *slot_count.get_if(); ++index) {
        const auto id = read_id<Id>(reader);
        const auto generation = reader.u32();
        const auto sequence = reader.u64();
        const auto alive = reader.boolean();
        if (!id.ok()) {
            return id.status();
        }
        if (!generation.ok()) {
            return generation.status();
        }
        if (!sequence.ok()) {
            return sequence.status();
        }
        if (!alive.ok()) {
            return alive.status();
        }
        typename SlotStore<Id, Value>::Slot slot;
        slot.id = *id.get_if();
        slot.generation = *generation.get_if();
        slot.sequence = *sequence.get_if();
        if (*alive.get_if()) {
            const auto value = read_value(reader);
            if (!value.ok()) {
                return value.status();
            }
            slot.value.emplace(std::move(*value.get_if()));
        }
        slots.push_back(std::move(slot));
    }
    const auto order_count = reader.count();
    if (!order_count.ok()) {
        return order_count.status();
    }
    std::vector<Id> iteration_order;
    iteration_order.reserve(*order_count.get_if());
    for (std::size_t index = 0; index < *order_count.get_if(); ++index) {
        const auto id = read_id<Id>(reader);
        if (!id.ok()) {
            return id.status();
        }
        iteration_order.push_back(*id.get_if());
    }

    if (*next_id.get_if() != iteration_order.size() + 1
        || *next_sequence.get_if() != iteration_order.size() + 1) {
        return corrupt("slot allocator counters are inconsistent");
    }
    for (std::size_t index = 0; index < iteration_order.size(); ++index) {
        if (iteration_order[index].value() != index + 1) {
            return corrupt("slot iteration order is not canonical");
        }
    }
    std::vector<bool> is_free(slots.size(), false);
    for (const auto index : free_slots) {
        if (index >= slots.size() || is_free[index]) {
            return corrupt("slot free list is invalid");
        }
        is_free[index] = true;
    }
    std::vector<SlotHandle> index_by_id(
        static_cast<std::size_t>(*next_id.get_if()),
        SlotHandle{}
    );
    std::size_t alive_count = 0;
    for (std::size_t index = 0; index < slots.size(); ++index) {
        const auto& slot = slots[index];
        if (slot.value.has_value()) {
            if (is_free[index] || !slot.id.valid() || slot.id.value() == 0
                || slot.id.value() >= *next_id.get_if()
                || slot.sequence != slot.id.value()
                || index_by_id[static_cast<std::size_t>(slot.id.value())]
                    .valid()) {
                return corrupt("live slot metadata is inconsistent");
            }
            index_by_id[static_cast<std::size_t>(slot.id.value())] =
                SlotHandle{
                    static_cast<std::uint32_t>(index),
                    slot.generation,
                };
            ++alive_count;
        } else if (!is_free[index] || slot.id.valid() || slot.sequence != 0) {
            return corrupt("free slot metadata is inconsistent");
        }
    }
    if (alive_count + free_slots.size() != slots.size()) {
        return corrupt("slot occupancy does not reconcile");
    }

    store.slots_ = std::move(slots);
    store.id_to_handle_ = std::move(index_by_id);
    store.free_slots_ = std::move(free_slots);
    store.iteration_order_ = std::move(iteration_order);
    store.next_id_ = *next_id.get_if();
    store.next_sequence_ = *next_sequence.get_if();
    store.alive_count_ = alive_count;
    return Status::success();
}

Result<RootState> CheckpointCodec::decode_state(
    std::span<const std::uint8_t> bytes,
    const CheckpointLimits& limits
) {
    BinaryReader reader(bytes, limits);
    const auto identity = reader.expect("MSM2");
    const auto version = reader.u32();
    if (!identity.ok()) {
        return identity;
    }
    if (!version.ok()) {
        return version.status();
    }
    if (*version.get_if() != 1) {
        return Status(
            ErrorCode::unsupported,
            "state payload version is unsupported"
        );
    }

    RootState state;
    const auto economy = read_id<EconomyId>(reader);
    const auto currency = reader.u32();
    const auto seed = reader.u64();
    const auto genesis_money = reader.f64();
    const auto tolerance = reader.f64();
    if (!economy.ok()) {
        return economy.status();
    }
    if (!currency.ok()) {
        return currency.status();
    }
    if (!seed.ok()) {
        return seed.status();
    }
    if (!genesis_money.ok()) {
        return genesis_money.status();
    }
    if (!tolerance.ok()) {
        return tolerance.status();
    }
    state.economy = *economy.get_if();
    state.currency = CurrencyId(*currency.get_if());
    state.seed = *seed.get_if();
    state.genesis_money = Money(*genesis_money.get_if());
    state.accounting_tolerance = *tolerance.get_if();
    if (!state.economy.valid() || !state.currency.valid()
        || !std::isfinite(state.genesis_money.value())
        || !std::isfinite(state.accounting_tolerance)
        || state.accounting_tolerance < 0.0) {
        return corrupt("root state header is invalid");
    }

    auto slot_status = read_slot_store(
        reader,
        state.households,
        [](BinaryReader& input) -> Result<HouseholdComponent> {
            const auto account = read_id<AccountId>(input);
            if (!account.ok()) {
                return account.status();
            }
            return HouseholdComponent{*account.get_if()};
        }
    );
    if (!slot_status.ok()) {
        return slot_status;
    }
    slot_status = read_slot_store(
        reader,
        state.firms,
        [](BinaryReader& input) -> Result<FirmComponent> {
            const auto sector = read_enum<FirmSector>(
                input,
                static_cast<std::uint8_t>(FirmSector::construction)
            );
            const auto account = read_id<AccountId>(input);
            const auto goods = input.f64();
            const auto capital = input.f64();
            const auto productivity = input.f64();
            if (!sector.ok()) {
                return sector.status();
            }
            if (!account.ok()) {
                return account.status();
            }
            if (!goods.ok()) {
                return goods.status();
            }
            if (!capital.ok()) {
                return capital.status();
            }
            if (!productivity.ok()) {
                return productivity.status();
            }
            return FirmComponent{
                *sector.get_if(),
                *account.get_if(),
                Goods(*goods.get_if()),
                Capital(*capital.get_if()),
                *productivity.get_if(),
            };
        }
    );
    if (!slot_status.ok()) {
        return slot_status;
    }
    slot_status = read_slot_store(
        reader,
        state.banks,
        [](BinaryReader& input) -> Result<BankComponent> {
            const auto account = read_id<AccountId>(input);
            const auto node = read_id<SettlementNodeId>(input);
            if (!account.ok()) {
                return account.status();
            }
            if (!node.ok()) {
                return node.status();
            }
            return BankComponent{*account.get_if(), *node.get_if()};
        }
    );
    if (!slot_status.ok()) {
        return slot_status;
    }

    const auto account_count = reader.count();
    if (!account_count.ok()) {
        return account_count.status();
    }
    state.postings.accounts_.reserve(*account_count.get_if());
    for (std::size_t index = 0; index < *account_count.get_if(); ++index) {
        const auto id = read_id<AccountId>(reader);
        const auto kind = read_enum<AccountKind>(
            reader,
            static_cast<std::uint8_t>(AccountKind::clearing)
        );
        const auto account_economy = read_id<EconomyId>(reader);
        const auto owner = read_owner(reader);
        const auto account_currency = reader.u32();
        const auto node = read_id<SettlementNodeId>(reader);
        const auto balance = reader.f64();
        const auto drift = reader.f64();
        const auto allow_negative = reader.boolean();
        const auto open = reader.boolean();
        if (!id.ok() || !kind.ok() || !account_economy.ok() || !owner.ok()
            || !account_currency.ok() || !node.ok() || !balance.ok()
            || !drift.ok() || !allow_negative.ok() || !open.ok()) {
            return corrupt("account record is truncated");
        }
        if (id.get_if()->value() != index + 1) {
            return corrupt("account IDs are not sequential");
        }
        state.postings.accounts_.push_back(
            AccountRecord{
                *id.get_if(),
                AccountKey{
                    *kind.get_if(),
                    *account_economy.get_if(),
                    *owner.get_if(),
                    CurrencyId(*account_currency.get_if()),
                    *node.get_if(),
                },
                Money(*balance.get_if()),
                *drift.get_if(),
                *allow_negative.get_if(),
                *open.get_if(),
            }
        );
    }
    state.postings.rebuild_account_slots();

    const auto reserve_count = reader.count();
    if (!reserve_count.ok()) {
        return reserve_count.status();
    }
    state.reserves.positions_.reserve(*reserve_count.get_if());
    for (std::size_t index = 0; index < *reserve_count.get_if(); ++index) {
        const auto node = read_id<SettlementNodeId>(reader);
        const auto bank = read_id<BankId>(reader);
        const auto balance = reader.f64();
        const auto drift = reader.f64();
        if (!node.ok() || !bank.ok() || !balance.ok() || !drift.ok()) {
            return corrupt("reserve record is truncated");
        }
        if (node.get_if()->value() != index + 1) {
            return corrupt("settlement node IDs are not sequential");
        }
        state.reserves.positions_.push_back(
            ReserveRecord{
                *node.get_if(),
                *bank.get_if(),
                Money(*balance.get_if()),
                *drift.get_if(),
            }
        );
    }
    const auto reserve_stock = reader.f64();
    const auto reserve_drift = reader.f64();
    if (!reserve_stock.ok() || !reserve_drift.ok()) {
        return corrupt("reserve stock is truncated");
    }
    state.reserves.reserve_stock_ = Money(*reserve_stock.get_if());
    state.reserves.reserve_stock_roundoff_drift_ = *reserve_drift.get_if();

    const auto loan_count = reader.count();
    if (!loan_count.ok()) {
        return loan_count.status();
    }
    state.loans.loans_.reserve(*loan_count.get_if());
    for (std::size_t index = 0; index < *loan_count.get_if(); ++index) {
        const auto id = read_id<LoanId>(reader);
        const auto lender = read_id<BankId>(reader);
        const auto borrower = read_owner(reader);
        const auto account = read_id<AccountId>(reader);
        const auto principal = reader.f64();
        const auto drift = reader.f64();
        const auto rate = reader.f64();
        const auto originated = reader.u64();
        const auto maturity = reader.u64();
        const auto active = reader.boolean();
        if (!id.ok() || !lender.ok() || !borrower.ok() || !account.ok()
            || !principal.ok() || !drift.ok() || !rate.ok()
            || !originated.ok() || !maturity.ok() || !active.ok()) {
            return corrupt("loan record is truncated");
        }
        if (id.get_if()->value() != index + 1) {
            return corrupt("loan IDs are not sequential");
        }
        state.loans.loans_.push_back(
            LoanRecord{
                *id.get_if(),
                *lender.get_if(),
                *borrower.get_if(),
                *account.get_if(),
                Money(*principal.get_if()),
                *drift.get_if(),
                LoanTerms{
                    Rate(*rate.get_if()),
                    Tick(*originated.get_if()),
                    Tick(*maturity.get_if()),
                },
                *active.get_if(),
            }
        );
    }

    const auto lot_count = reader.count();
    if (!lot_count.ok()) {
        return lot_count.status();
    }
    state.ownership.lots_.reserve(*lot_count.get_if());
    for (std::size_t index = 0; index < *lot_count.get_if(); ++index) {
        const auto id = read_id<OwnershipLotId>(reader);
        const auto kind = read_enum<AssetKind>(
            reader,
            static_cast<std::uint8_t>(AssetKind::generic_contract)
        );
        const auto asset_economy = read_id<EconomyId>(reader);
        const auto asset_value = reader.u64();
        const auto owner = read_owner(reader);
        const auto share = reader.f64();
        const auto active = reader.boolean();
        if (!id.ok() || !kind.ok() || !asset_economy.ok()
            || !asset_value.ok() || !owner.ok() || !share.ok()
            || !active.ok()) {
            return corrupt("ownership record is truncated");
        }
        if (id.get_if()->value() != index + 1) {
            return corrupt("ownership lot IDs are not sequential");
        }
        if (*asset_value.get_if() > std::numeric_limits<std::uint32_t>::max()) {
            return corrupt("ownership asset exceeds the compact ID range");
        }
        state.ownership.lots_.push_back(
            OwnershipLot{
                *id.get_if(),
                AssetKey{
                    *kind.get_if(),
                    *asset_economy.get_if(),
                    static_cast<std::uint32_t>(*asset_value.get_if()),
                },
                *owner.get_if(),
                *share.get_if(),
                *active.get_if(),
            }
        );
    }

    const auto counter_count = reader.count();
    if (!counter_count.ok()) {
        return counter_count.status();
    }
    state.named_counters.counters_.reserve(*counter_count.get_if());
    std::uint64_t previous_stream = 0;
    for (std::size_t index = 0; index < *counter_count.get_if(); ++index) {
        const auto stream = reader.u64();
        const auto value = reader.u64();
        if (!stream.ok() || !value.ok()) {
            return corrupt("named counter is truncated");
        }
        if (*stream.get_if() == 0 || *stream.get_if() <= previous_stream) {
            return corrupt("named counters are not canonical");
        }
        previous_stream = *stream.get_if();
        state.named_counters.counters_.emplace_back(
            *stream.get_if(),
            *value.get_if()
        );
    }
    const auto central_bank = read_id<AccountId>(reader);
    const auto dealer = read_id<AccountId>(reader);
    const auto residual = read_id<AccountId>(reader);
    const auto treasury = read_id<AccountId>(reader);
    if (!central_bank.ok() || !dealer.ok() || !residual.ok()
        || !treasury.ok()) {
        return corrupt("institution registry is truncated");
    }
    state.institutions = InstitutionRegistry{
        *central_bank.get_if(),
        *dealer.get_if(),
        *residual.get_if(),
        *treasury.get_if(),
    };
    if (!reader.finished()) {
        return corrupt("state payload has trailing bytes");
    }
    const auto invariants = run_invariants(state);
    if (!invariants.ok()) {
        return corrupt("loaded state violates an invariant");
    }
    return Result<RootState>(std::move(state));
}

Status validate_canonical_json(
    std::span<const std::uint8_t> encoded
) noexcept {
    try {
        if (encoded.empty() || encoded.back() != '\n') {
            return corrupt("canonical JSON requires a terminal newline");
        }
        const std::string_view text(
            reinterpret_cast<const char*>(encoded.data()),
            encoded.size() - 1
        );
        const auto parsed = Json::parse(text);
        const auto value_status = validate_json_value(parsed);
        if (!value_status.ok()) {
            return value_status;
        }
        if (canonical_json(parsed)
            != ByteVector(encoded.begin(), encoded.end())) {
            return corrupt("JSON representation is not canonical");
        }
        return Status::success();
    } catch (...) {
        return corrupt("canonical JSON is invalid");
    }
}

Result<std::vector<std::uint8_t>> save_checkpoint(const RootState& state) {
    try {
        if (state.transaction_active) {
            return Status(
                ErrorCode::invalid_transaction_state,
                "active transaction cannot be checkpointed"
            );
        }
        const auto invariants = run_invariants(state);
        if (!invariants.ok()) {
            return invariants.status;
        }
        const auto state_bytes = CheckpointCodec::encode_state(state);
        const auto state_array = make_npy(state_bytes);
        Json metadata{
            {"canonical_encoding_version", kCanonicalEncodingVersion},
            {"checkpoint_schema_version", kM2CheckpointSchemaVersion},
            {
                "entries",
                Json::array(
                    {
                        {
                            {"dtype", "|u1"},
                            {"name", kStateEntryName},
                            {"sha256", hex(sha256(state_array))},
                            {"shape", Json::array({state_bytes.size()})},
                        },
                    }
                ),
            },
            {"engine_version", std::string(macro_sim::engine_version())},
            {"payload_kind", kPayloadKind},
            {
                "required_features",
                Json::array(
                    {
                        kRequiredFeatures[0],
                        kRequiredFeatures[1],
                        kRequiredFeatures[2],
                        kRequiredFeatures[3],
                    }
                ),
            },
            {"state_digest", state_digest(state).hex()},
        };
        const auto metadata_bytes = canonical_json(metadata);
        const auto manifest = build_manifest(metadata_bytes);
        return make_zip(
            {
                {std::string(kManifestEntryName), manifest},
                {std::string(kMetadataEntryName), metadata_bytes},
                {std::string(kStateEntryName), state_array},
            }
        );
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "checkpoint allocation failed"
        );
    } catch (...) {
        return Status(ErrorCode::internal_error, "checkpoint save failed");
    }
}

Result<RootState> load_checkpoint(
    std::span<const std::uint8_t> archive,
    CheckpointLimits limits
) {
    try {
        const auto parsed_entries = parse_zip(archive, limits);
        if (!parsed_entries.ok()) {
            return parsed_entries.status();
        }
        const auto& entries = *parsed_entries.get_if();
        if (entries.size() != 3) {
            return corrupt("checkpoint entry set is invalid");
        }
        const auto* manifest = find_entry(entries, kManifestEntryName);
        const auto* metadata = find_entry(entries, kMetadataEntryName);
        const auto* state_array = find_entry(entries, kStateEntryName);
        if (manifest == nullptr || metadata == nullptr
            || state_array == nullptr) {
            return corrupt("checkpoint required entry is absent");
        }
        const auto manifest_status = validate_manifest(*manifest, *metadata);
        if (!manifest_status.ok()) {
            return manifest_status;
        }
        const auto metadata_status = validate_canonical_json(*metadata);
        if (!metadata_status.ok()) {
            return metadata_status;
        }
        const auto parsed_metadata = Json::parse(
            std::string_view(
                reinterpret_cast<const char*>(metadata->data()),
                metadata->size() - 1
            )
        );
        if (!parsed_metadata.is_object()
            || parsed_metadata.value(
                "checkpoint_schema_version",
                std::uint32_t{0}
            ) < kM2CheckpointSchemaVersion
            || parsed_metadata.value(
                "canonical_encoding_version",
                std::uint32_t{0}
            ) != kCanonicalEncodingVersion
            || parsed_metadata.value("payload_kind", std::string{})
                != kPayloadKind
            || !parsed_metadata.contains("entries")
            || !parsed_metadata["entries"].is_array()
            || parsed_metadata["entries"].size() != 1
            || !parsed_metadata.contains("required_features")
            || parsed_metadata["required_features"]
                != Json::array(
                    {
                        kRequiredFeatures[0],
                        kRequiredFeatures[1],
                        kRequiredFeatures[2],
                        kRequiredFeatures[3],
                    }
                )) {
            return corrupt("checkpoint metadata contract is invalid");
        }
        const auto& entry = parsed_metadata["entries"][0];
        if (!entry.is_object()
            || entry.value("name", std::string{}) != kStateEntryName
            || entry.value("dtype", std::string{}) != "|u1"
            || entry.value("sha256", std::string{})
                != hex(sha256(*state_array))) {
            return corrupt("checkpoint array metadata does not match");
        }
        const auto state_bytes = parse_npy(*state_array, limits);
        if (!state_bytes.ok()) {
            return state_bytes.status();
        }
        if (!entry.contains("shape") || !entry["shape"].is_array()
            || entry["shape"].size() != 1
            || entry["shape"][0].get<std::size_t>()
                != state_bytes.get_if()->size()) {
            return corrupt("checkpoint array shape does not match");
        }
        auto state = CheckpointCodec::decode_state(*state_bytes.get_if(), limits);
        if (!state.ok()) {
            return state.status();
        }
        if (parsed_metadata.value("state_digest", std::string{})
            != state_digest(*state.get_if()).hex()) {
            return corrupt("checkpoint state digest does not match");
        }
        return Result<RootState>(std::move(*state.get_if()));
    } catch (const std::bad_alloc&) {
        return Status(
            ErrorCode::allocation_failure,
            "checkpoint allocation failed"
        );
    } catch (...) {
        return corrupt("checkpoint load failed");
    }
}

}  // namespace macro_sim::core
