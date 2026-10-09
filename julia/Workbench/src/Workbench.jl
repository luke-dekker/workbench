"""
    Workbench

The workbench catalog from Julia (Pluto, IJulia, scripts), via PythonCall.

    using Workbench
    Workbench.show()                      # every artifact, as a Vector of NamedTuples (Pluto renders it)
    Workbench.show("fieldrec")
    a    = Workbench.latest("fieldrec"; kind="mcap", group="sessions")
    sess = Workbench.load(a)              # Dict{String, Arrow.Table}  (one per topic)
    t    = Workbench.load(Workbench.latest("node-tool"; kind="safetensors"))   # Dict{String, Array}
    Workbench.snippet(a)                  # Julia code that loads `a`

Needs the env vars the `wb` launcher sets: JULIA_PYTHONCALL_EXE (the workbench venv python)
and JULIA_CONDAPKG_BACKEND=Null. Outside the launcher, set them before `using Workbench`.
"""
module Workbench

using Arrow
using PythonCall

const _catalog = Ref{Py}()

"""The Python `wb.catalog` module (lazy)."""
function catalog()
    if !isassigned(_catalog)
        _catalog[] = pyimport("wb.catalog")
    end
    return _catalog[]
end

_kw(; kw...) = (; (k => (v === nothing ? pybuiltins.None : v) for (k, v) in kw)...)

"Names of registered projects."
projects() = pyconvert(Vector{String}, catalog().projects())

"Python `Artifact` objects, oldest first. Filter by project / kind / group."
artifacts(project=nothing; kind=nothing, group=nothing) =
    collect(catalog().artifacts(project === nothing ? pybuiltins.None : project; _kw(kind=kind, group=group)...))

"Newest artifact of a project (optionally of one kind / group)."
latest(project; kind=nothing, group=nothing) = catalog().latest(project; _kw(kind=kind, group=group)...)

"Artifact whose name contains `name` (newest if several)."
find(name, project=nothing) = catalog().find(name, project === nothing ? pybuiltins.None : project)

"Rows describing artifacts: project, group, kind, name, modified, MB, path."
function show(project=nothing; kind=nothing, newest_first=true)
    arts = artifacts(project; kind=kind)
    newest_first && (arts = reverse(arts))
    return [(project = pyconvert(String, a.project), group = pyconvert(String, a.group),
             kind = pyconvert(String, a.kind), name = pyconvert(String, a.name),
             modified = pyconvert(String, a.mtime.strftime("%Y-%m-%d %H:%M")),
             MB = pyis(a.size, pybuiltins.None) ? missing : round(pyconvert(Float64, a.size) / 1e6; digits=2),
             path = pyconvert(String, pystr(a.path))) for a in arts]
end

"pyarrow.Table -> Arrow.Table, through Arrow IPC bytes (no element-wise conversion)."
function _arrow(tbl::Py)
    pa = pyimport("pyarrow")
    sink = pa.BufferOutputStream()
    w = pa.ipc.new_stream(sink, tbl.schema)
    w.write_table(tbl)
    w.close()
    bytes = pyconvert(Vector{UInt8}, sink.getvalue().to_pybytes())
    return Arrow.Table(bytes)
end

"Convert whatever a Python loader returned into Julia values."
function _convert(obj::Py)
    pa = pyimport("pyarrow")
    np = pyimport("numpy")
    if pyisinstance(obj, pa.Table)
        return _arrow(obj)
    elseif pyisinstance(obj, pybuiltins.dict)
        return Dict{String,Any}(pyconvert(String, k) => _convert(v) for (k, v) in obj.items())
    elseif pyisinstance(obj, np.ndarray)
        return pyconvert(Array, obj)
    elseif pyisinstance(obj, pyimport("pathlib").Path)
        return pyconvert(String, pystr(obj))
    else
        return pyconvert(Any, obj)
    end
end

"Load an artifact (or a path + kind) and convert the result to Julia types."
load(a::Py; kw...) = _convert(catalog().load(a; kw...))
load(path::AbstractString, kind::AbstractString; kw...) = _convert(catalog().load_path(path, kind; kw...))

"Julia code that loads this artifact."
function snippet(a::Py)
    name, project, kind = (pyconvert(String, a.name), pyconvert(String, a.project), pyconvert(String, a.kind))
    same = count(b -> pyconvert(String, b.name) == name, artifacts(project; kind=kind))
    if same > 1
        path = pyconvert(String, pystr(a.path))
        return "using Workbench\nobj = Workbench.load($(repr(path)), $(repr(kind)))   # $(repr(name)) is not unique in $project"
    end
    return "using Workbench\nobj = Workbench.load(Workbench.find($(repr(name)), $(repr(project))))"
end

export projects, artifacts, latest, find, load, snippet

end # module
