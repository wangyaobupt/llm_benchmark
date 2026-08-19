from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

rows = pq.read_table(
    Path("data/derived/investigation_timepoint/corpus_1000/mining/mined_rules.parquet")
).to_pylist()
print("n", len(rows))
print("family", Counter(r["family"] for r in rows))
print("conditions", Counter(r["condition_name"] for r in rows))
print("candidates", Counter(r["candidate_name"] for r in rows))
print()
for row in sorted(rows, key=lambda item: -float(item.get("lift") or 0)):
    print(
        f"{row['condition_name']!r:22} -> {row['candidate_name']!r:22} "
        f"{row['family']:28} lift={row['lift']:.2f} p={row['n_x_subjects']}->"
        f"{row['n_xy_subjects']}/{row['n_y_subjects']} q={row['q_value']:.3g} "
        f"stab={row['bootstrap_direction_stability']:.2f}"
    )
