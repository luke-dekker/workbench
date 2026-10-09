# Read the shared dataset from Julia: safetensors (pure Julia) + Arrow IPC (Arrow.jl).
#
#   julia --project=@notebooks notebooks/interop/read_data.jl
#
# Paste the safetensors block into a Pluto cell to use it there.

using Arrow, JSON3, Statistics

const DATA = joinpath(@__DIR__, "data")

const ST_DTYPES = Dict("F32" => Float32, "F64" => Float64, "F16" => Float16,
                       "I64" => Int64, "I32" => Int32, "I16" => Int16, "I8" => Int8,
                       "U8" => UInt8, "BOOL" => Bool, "BF16" => UInt16)

"""Minimal safetensors reader: returns Dict{String,Array} plus the metadata dict."""
function read_safetensors(path::AbstractString)
    bytes = read(path)
    n = Int(reinterpret(UInt64, bytes[1:8])[1])
    header = JSON3.read(String(bytes[9:8+n]))
    base = 8 + n
    out = Dict{String,Array}()
    meta = Dict{String,String}()
    for (k, v) in pairs(header)
        key = String(k)
        if key == "__metadata__"
            meta = Dict(String(a) => String(b) for (a, b) in pairs(v))
            continue
        end
        T = ST_DTYPES[String(v.dtype)]
        shape = Tuple(Int.(v.shape))
        s, e = Int.(v.data_offsets)
        raw = reinterpret(T, @view bytes[base+s+1:base+e])
        # safetensors is row-major; Julia is column-major, so reverse dims then permute
        arr = length(shape) <= 1 ? collect(raw) :
              permutedims(reshape(collect(raw), reverse(shape)...), reverse(1:length(shape)))
        out[key] = arr
    end
    return out, meta
end

tensors, meta = read_safetensors(joinpath(DATA, "tensors.safetensors"))
println("safetensors  meta=", meta)
for (k, v) in sort(collect(tensors); by=first)
    println("  ", rpad(k, 8), " ", eltype(v), " ", size(v), "  mean=", round(mean(v); digits=4))
end

tbl = Arrow.Table(joinpath(DATA, "table.arrow"))
println("arrow        cols=", keys(tbl), "  rows=", length(tbl.t))
println("  signal mean=", round(mean(tbl.signal); digits=4),
        "  matches safetensors: ", isapprox(mean(tbl.signal), mean(tensors["signal"])))

# Optional: the same file through Python's safetensors via PythonCall (shares node-tool's env).
# Set JULIA_PYTHONCALL_EXE to a venv python that has safetensors, and JULIA_CONDAPKG_BACKEND=Null.
if haskey(ENV, "JULIA_PYTHONCALL_EXE")
    using PythonCall
    st = pyimport("safetensors.numpy")
    py = st.load_file(joinpath(DATA, "tensors.safetensors"))
    w = pyconvert(Array, py["weights"])
    println("pythoncall   weights via Python == pure Julia: ", w == tensors["weights"])
end
println("JULIA_READ_OK")
