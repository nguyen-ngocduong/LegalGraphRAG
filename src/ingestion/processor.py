import logging
import os
import unicodedata
import re
from pathlib import Path
from config.configs import PROCESSED_PATH, CLEAN_PATH
from crawl.crawl import log
from tqdm import tqdm

class ProcessData:
    """
    Tiền xử lý dữ liệu trước khi đưa vào chunk:
    Work flow:
    - đọc file txt được lưu ở process_dir - định nghĩa ở config
    - clean tex
    - save vào clean_dir được định nghĩa ở config
    """
    def __init__(self, process_dir: PROCESSED_PATH, clean_dir: CLEAN_PATH) -> None:
        self.process_dir = Path(process_dir)
        self.clean_dir = Path(clean_dir)
        self.clean_dir.mkdir(parents=True, exist_ok=True)
    def read(self, txt_path: str|Path) -> str:
        """
        Đọc file text từ txt_path
        """
        with open(txt_path, "r", encoding="utf-8") as f:
            return f.read()
    def clean(self, text: str) -> str:
        """
        Clean text file
        - Số trang nằm riêng một dòng => Loại bỏ các dòng chỉ chứa chữ số 
        - Khoảng trắng dư thừa => Gộp nhiều khoảng trắng hoặc dòng trống thành một 
        - Phần "Nơi nhận" => Cắt bỏ phần cuối văn bản từ mục này 
        - Lỗi ký tự đặc biệt => Chuẩn hóa Unicode 
        - Mã hóa không đồng nhất => Chuẩn hóa về UTF-8
        """
        # Unicode normalization
        text = unicodedata.normalize("NFC", text)
        # Normalize newline
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Remove page number
        text = re.sub(r"(?m)^\s*\d+\s*$", "", text)
        # Normalize spaces
        text = re.sub(r"[ \t]+", " ", text)
        # Collapse blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove "Nơi nhận"
        match = re.search(r"(?im)^Nơi nhận\s*:", text)
        if match:
            text = text[:match.start()]
        return text.strip()
    def save_file(self,text: str, txt_path: str | Path):
        """
        Save cleaned text.
        Args:
            filename: Original filename.
            text: Cleaned text.
        """
        txt_path = Path(txt_path)
        output_path = self.clean_dir / f"{txt_path.stem}_clean.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
    def run(self):
        """
        Thực thi workflow
        """
        try:
            txt_files = sorted(self.process_dir.glob("*.txt"))
            logging.info(f"Tìm thấy {len(txt_files)} files từ {self.process_dir}!")
        except Exception as e:
            logging.error(f"Lỗi {e} => không tìm thấy file txt")
            return
        try: 
            for txt_file in tqdm(txt_files):
                logging.info(f"processing {txt_file.name} ...")
                text = self.read(txt_file)
                clean_text = self.clean(text)
                self.save_file(clean_text, txt_file)
                logging.info(f"Đã lưu xong file {txt_file} vào {self.clean_dir}!")
        except Exception as e:
            logging.exception(f"Lỗi khi đang thự hiện lưu file: {e}")
            return
if __name__ == "__main__":
    log()
    os.makedirs(CLEAN_PATH, exist_ok = True)
    processer = ProcessData(PROCESSED_PATH, CLEAN_PATH)
    processer.run()