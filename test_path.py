from backend.core.service import ForensicWorkbenchService
service = ForensicWorkbenchService()
p = service._photo_storage_dir("main", "1999_12_01_y3p21r6")
print(p.absolute())
