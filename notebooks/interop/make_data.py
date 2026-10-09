"""Write one dataset in the fleet formats: safetensors (tensors) + Arrow IPC + Parquet (table).

    uv run python notebooks/interop/make_data.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.parquet as pq
from safetensors.numpy import save_file

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

rng = np.random.default_rng(42)
t = np.linspace(0, 4 * np.pi, 256, dtype=np.float32)
tensors = {
    "signal": np.sin(t) + 0.1 * rng.standard_normal(256).astype(np.float32),
    "weights": rng.standard_normal((4, 8)).astype(np.float32),
    "ids": np.arange(256, dtype=np.int64),
}
save_file(tensors, OUT / "tensors.safetensors", metadata={"source": "workbench interop proof"})

table = pa.table({
    "t": t,
    "signal": tensors["signal"],
    "label": pa.array(["a", "b", "c", "d"] * 64),
})
feather.write_feather(table, OUT / "table.arrow", compression="uncompressed")
pq.write_table(table, OUT / "table.parquet")

for f in sorted(OUT.iterdir()):
    print(f"{f.name:<22} {f.stat().st_size:>8} bytes")
