"""Local CSV/JSON fallback (used when Feishu credentials are not configured)."""
import csv
import json
from pathlib import Path
from typing import List


class LocalStorage:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_json(self, data: List[dict], filename: str) -> str:
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Local] Saved {len(data)} records to {path}")
        return str(path)

    def save_csv(self, data: List[dict], filename: str) -> str:
        if not data:
            print(f"[Local] No data to save for {filename}")
            return ""
        path = self.output_dir / filename
        keys = list(data[0].keys())
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in data:
                clean = {
                    k: (v.get("link", "") if isinstance(v, dict) else v)
                    for k, v in row.items()
                }
                writer.writerow(clean)
        print(f"[Local] Saved {len(data)} records to {path}")
        return str(path)
