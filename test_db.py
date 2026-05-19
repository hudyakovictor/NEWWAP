from backend.core.service import ForensicWorkbenchService
service = ForensicWorkbenchService()
records = service.list_dataset("main")
for r in records:
    if "01.12.1999" in r["date"] or "1999_12_01" in r["filename"]:
        print(f"File 1: {r['filename']}, Bucket: {r['bucket']}, Pose: {r.get('pose')}, Status: {r.get('status')}")
    if "03.04.2010" in r["date"] or "2010_04_03" in r["filename"]:
        print(f"File 2: {r['filename']}, Bucket: {r['bucket']}, Pose: {r.get('pose')}, Status: {r.get('status')}")
