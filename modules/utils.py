import os
import shutil
import uuid

def make_temp_dir(base: str = "temp") -> str:
    """Tạo thư mục tạm với tên ngẫu nhiên."""
    path = os.path.join(base, str(uuid.uuid4())[:8])
    os.makedirs(path, exist_ok=True)
    return path

def clean_temp(path: str):
    """Xóa thư mục tạm sau khi xong."""
    shutil.rmtree(path, ignore_errors=True)

def ensure_dirs():
    """Tạo các thư mục cần thiết nếu chưa có."""
    for d in ["temp", "output", "assets"]:
        os.makedirs(d, exist_ok=True)