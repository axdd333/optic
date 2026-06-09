import json
data = json.load(open("/tmp/optic_audit_v2.json"))

print("=== KEY METRICS ===")
print(f"parsed_files: {data['parsed_files']}")
print(f"artifact_count: {data['artifact_count']}")
print(f"signal_count: {data['signal_count']}")
print(f"signal_detections: {data['signal_detections']}")
print(f"signal_detector_available: {data['signal_detector_available']}")
print(f"claim_count: {data['claim_count']}")
print(f"contradiction_count: {data['contradiction_count']}")
print(f"parse_errors count: {len(data['parse_errors'])}")

# Find all detector-based signals
cats = {}
for s in data.get("signals_summary", []):
    cat = s["category"]
    cats[cat] = cats.get(cat, 0) + 1

print("\n=== SIGNAL CATEGORIES ===")
for cat, count in sorted(cats.items()):
    print(f"  {cat}: {count}")

# Find non-basic signals
det_sigs = [s for s in data.get("signals_summary", [])
            if s["category"] not in ("frequent_topic", "project_velocity", "workstream_fragmentation")]
print(f"\n=== DETECTOR-BASED SIGNALS: {len(det_sigs)} ===")
for s in det_sigs:
    print(f"  [{s['category']}] {s['description'][:120]}")
    print(f"    artifacts: {s['artifact_refs']}")
