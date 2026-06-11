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

def cleanup_old_outputs(output_dir: str = "output", keep_days: int = 7):
    """Xóa file output cũ hơn keep_days ngày."""
    import time
    now = time.time()
    if not os.path.exists(output_dir):
        return
    for fname in os.listdir(output_dir):
        fpath = os.path.join(output_dir, fname)
        if os.path.isfile(fpath):
            age_days = (now - os.path.getmtime(fpath)) / 86400
            if age_days > keep_days:
                os.remove(fpath)
                print(f"[CLEANUP] Xóa file cũ: {fname}")

def cleanup_old_temps(temp_dir: str = "temp", max_age_hours: int = 2):
    """Xóa thư mục temp cũ hơn 2 tiếng."""
    import time
    if not os.path.exists(temp_dir):
        return
    now = time.time()
    for name in os.listdir(temp_dir):
        path = os.path.join(temp_dir, name)
        if os.path.isdir(path):
            age_h = (now - os.path.getmtime(path)) / 3600
            if age_h > max_age_hours:
                shutil.rmtree(path, ignore_errors=True)