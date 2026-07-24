# ADR 0001: Canonical Encoding and Native Checkpoint Boundary

Status: accepted for M1 and binding for M2 implementation  
Decision date: 2026-07-24  
Canonical encoding version: 1  
Checkpoint envelope file identifier: `MSCP`

## Context

The native engine needs a persistence boundary that is deterministic across
macOS, Linux, and Windows, rejects damaged or ambiguous data before allocating
simulation state, and can evolve without coupling saves to C++ object layouts.
Raw struct dumps, pickle, host-endian arrays, and ordinary JSON do not satisfy
that boundary.

M1 does not persist an economic state. It freezes the representation rules,
dependency identities, executable vectors, and a small envelope prototype so
M2 can implement real checkpoints without reopening the format decision.

## Decision

### Canonical metadata

`CanonicalEncodingVersion = 1` is UTF-8 JSON with these additional rules:

1. The document ends with exactly one LF and has no other insignificant
   whitespace.
2. Object keys are Unicode NFC strings sorted by Unicode code point. Duplicate
   keys, non-string keys, and normalization collisions are rejected.
3. Strings are Unicode NFC. JSON escaping is the minimal form emitted by the
   checked encoder; alternative escape spellings are rejected by byte
   comparison.
4. Integers are signed 64-bit decimal JSON integers. Leading zeroes, a plus
   sign, negative zero, exponent notation, and values outside the range are
   rejected.
5. Raw JSON floating-point numbers are forbidden. A finite IEEE-754 binary64
   value is encoded as `{"$f64":"hhhhhhhhhhhhhhhh"}`, where the value is the
   lowercase hexadecimal big-endian bit pattern. This preserves negative zero
   and subnormals without depending on a language's decimal formatter.
6. Bytes are encoded as `{"$bytes":"hh..."}` using lowercase hexadecimal.
7. Object keys beginning with `$` are reserved. Unknown reserved tags are
   rejected.
8. NaN and infinities are invalid at persistence boundaries.
9. Decoding is strict: invalid UTF-8, duplicate keys, unknown tags, and any
   byte sequence that differs from re-encoding the decoded value are rejected.

The checked vectors in `schemas/m1/canonical_encoding_vectors.json` are the
normative examples. The Python implementation is an executable oracle for M1;
the C++ implementation in M2 must match those bytes, not merely decode to an
equivalent value.

### Checkpoint container

The M2 checkpoint is a deterministic ZIP container with stored, uncompressed
entries. Compression is a transport concern and is not part of canonical
checkpoint bytes. The entries are:

- `manifest.fb`: a FlatBuffers manifest and compatibility envelope;
- `metadata.json`: Canonical Encoding Version 1 metadata;
- `arrays/<stable-id>.npy`: bulk numeric arrays in stable-ID order.

The canonical writer uses ZIP `STORE`, sorts entry names by UTF-8 byte order,
uses the DOS epoch timestamp, emits no archive comment, no platform-specific
extra fields, no data descriptors, and no duplicate paths. Absolute paths,
parent traversal, backslashes, encrypted entries, and case-folding collisions
are rejected.

NPY entries use format 2.0, C order, explicit little-endian numeric
descriptors, fixed-width dtypes, and canonical header key order. Object arrays,
pickle payloads, native-endian `=`, platform-sized integers, and Fortran-order
arrays are forbidden. An implementation may use deflate for network transfer
or an explicitly noncanonical export, but it must restore and verify the
canonical entry stream before loading.

The manifest contains:

- checkpoint schema and minimum reader versions;
- canonical encoding version;
- engine and contract identities;
- sorted required feature identifiers;
- for every non-manifest entry: stable path, logical kind, byte length,
  SHA-256, dtype, and shape where applicable;
- a semantic digest over the canonical ordered entry descriptors.

The manifest never hashes itself. The archive may additionally have a whole
file SHA-256 in surrounding protocol metadata.

### Compatibility

FlatBuffers fields are optional unless represented by a required feature
identifier. Readers ignore unknown optional fields. A reader rejects an
unknown required feature, an unsupported canonical encoding version, an
invalid minimum-reader version, an absent required slot, duplicate feature
identifiers, or an unsorted manifest.

Checkpoint schema numbers describe the writer schema; they do not alone force
rejection. Required features carry the actual compatibility decision. Schema
migration, when needed, constructs a new validated state and never mutates the
source bytes in place.

### Loading boundary

Loaders perform these steps in order:

1. enforce total archive, entry count, name length, entry size, and expansion
   ratio limits before allocation;
2. validate ZIP structure and canonical paths;
3. parse the FlatBuffers manifest with bounded access;
4. reject unsupported required features or encoding versions;
5. hash every declared entry and reject missing, duplicate, undeclared, or
   mismatched entries;
6. strictly decode canonical metadata and NPY headers;
7. validate IDs, dimensions, counts, units, and cross-entry references;
8. allocate a new engine state and publish it only after all checks pass.

No C++ pointer, allocator address, unordered-container iteration order, Python
object, callback, or host-endian memory image crosses this boundary.

## Dependency decision

The selected source identities and archive SHA-256 values are frozen in
`native/dependencies.lock.json`:

- nlohmann/json for the C++ JSON parser and emitter;
- FlatBuffers for the manifest;
- zlib for ZIP framing and optional deflate transport;
- PicoSHA2 for the portable SHA-256 implementation;
- cnpy for NPY/NPZ parsing logic, subject to the stricter rules above.

M2 may wrap or patch a dependency but may not silently substitute a different
source. Any update requires a new lock record, regenerated SPDX evidence,
vector execution on all supported platforms, and an ADR amendment.

## Prototype evidence

`tools/m1/checkpoint_prototype.py` builds an actual FlatBuffer with identifier
`MSCP`, canonical payload bytes, SHA-256, required features, and extensions.
The checked artifact records exact bytes, sizes, semantic digest, forward
optional-field compatibility, and corruption outcomes. Its dynamic benchmark
is evidence only and is intentionally excluded from reproducible checked
bytes.

The prototype uses one embedded payload because M1 has no native economic
state. M2 replaces that payload with the manifest of canonical ZIP entries;
the compatibility and validation rules remain unchanged.

## Consequences

The representation is more explicit than dumping C++ state and costs one
manifest plus validation passes. In return, saves are auditable, language
neutral, deterministic, fuzzable, and safe to consume from the desktop client
or Python tooling. Exact floating-point state survives without relying on
decimal formatting, and future optional data can be added without weakening
required-feature checks.
