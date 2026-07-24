#ifndef MACRO_SIM_GENERATED_RNG_VECTORS_HPP
#define MACRO_SIM_GENERATED_RNG_VECTORS_HPP

#include <array>
#include <cstdint>
#include <string_view>

namespace macro_sim::generated {

inline constexpr std::string_view kRngSemanticSha256 = "4fc5a96de6d99505aaf65b5fe3fa8586b71739a92d2b7590bc9b1a9233528d0c";

struct PhiloxBlockVector final {
    std::array<std::uint32_t, 4> counter;
    std::array<std::uint32_t, 2> key;
    std::array<std::uint32_t, 4> output;
};
inline constexpr std::array<PhiloxBlockVector, 4> kPhiloxBlockVectors{{
    {{0U, 0U, 0U, 0U}, {0U, 0U}, {1713891541U, 3781805453U, 3159862348U, 2600524760U}},
    {{1U, 0U, 0U, 0U}, {0U, 0U}, {4175744164U, 1555169499U, 2980410603U, 159317863U}},
    {{0U, 1U, 2U, 3U}, {4U, 5U}, {3290935133U, 3881757242U, 1203941666U, 1610286023U}},
    {{4294967295U, 4294967295U, 4294967295U, 4294967295U}, {4294967295U, 4294967295U}, {1083123565U, 1103641358U, 2718681030U, 1834242557U}},
}};

inline constexpr std::array<std::uint32_t, 16> kStreamU32{{
    211137116U, 2423764656U, 2671379769U, 2083268178U, 3965094734U, 3328146504U, 424335527U, 3128986081U, 2990035399U, 3885963827U, 3230728570U, 3602205487U, 368636407U, 2968340421U, 1020865188U, 3923849712U
}};
inline constexpr std::array<std::uint64_t, 8> kUniformBits{{
    4600561947830507414ULL, 4603142009082059970ULL, 4595970285938150220ULL, 4590853874281374776ULL, 4596860393438444444ULL, 4601078804753733730ULL, 4597170278409626848ULL, 4591856232438182432ULL
}};
inline constexpr std::array<std::uint64_t, 8> kOpenUniformBits{{
    4595899670143183482ULL, 4602849060953646570ULL, 4605001192528673618ULL, 4605977444148733844ULL, 4604417738063311928ULL, 4599718206463138139ULL, 4602553296809731513ULL, 4601394652550197591ULL
}};

struct BoundedVector final { std::uint64_t bound; std::uint64_t value; };
inline constexpr std::array<BoundedVector, 7> kBoundedVectors{{
    {1ULL, 0ULL},
    {2ULL, 0ULL},
    {3ULL, 0ULL},
    {7ULL, 5ULL},
    {10ULL, 1ULL},
    {257ULL, 237ULL},
    {4294967291ULL, 4003184001ULL},
}};

struct BernoulliVector final { double probability; bool value; };
inline constexpr std::array<BernoulliVector, 5> kBernoulliVectors{{
    {0, false},
    {0.10000000000000001, false},
    {0.5, false},
    {0.90000000000000002, true},
    {1, true},
}};
inline constexpr std::array<std::size_t, 12> kShuffleVector{{
    6, 9, 10, 11, 5, 7, 4, 8, 0, 2, 3, 1
}};
inline constexpr std::array<std::size_t, 7> kSampleVector{{
    9, 14, 3, 10, 16, 6, 17
}};
inline constexpr std::array<std::uint64_t, 6> kNormalBits{{
    13797788690346085376ULL, 13818020643954815872ULL, 4611389498827914616ULL, 13818826059783278720ULL, 13825266235589704304ULL, 13832881073279293924ULL
}};

struct PoissonVector final { double lambda; std::uint64_t value; };
inline constexpr std::array<PoissonVector, 6> kPoissonVectors{{
    {0, 0ULL},
    {0.25, 0ULL},
    {1, 2ULL},
    {4, 8ULL},
    {17, 12ULL},
    {40, 54ULL},
}};

}  // namespace macro_sim::generated

#endif
