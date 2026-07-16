import pymupdf
import docx
import os

from config.configs import RAW_PATH

class LoadData:
    """
    Tạo một lớp Load Data:
    - Chứa các phương thức để tải dữ liệu từ các nguồn khác nhau (PDF, DOCX).
    - Đầu vào raw_dir: là các tài liệu đinh dạng pdf, doc được lưu ở RAW_PATH định nghĩa ở config.yaml
    """
    def __init__(self, raw_dir=RAW_PATH) -> None:
        self.raw_dir = raw_dir
    def get_file_from_raw_dir(self):
        """
        Lấy tất cả các file trong thư mục raw_dir
        """
        all_files = [file for file in os.listdir(self.raw_dir) if os.path.isfile(os.path.join(self.raw_dir, file))]
        return all_files
    def load_pdf(self, pdf_path):
        """
        Load theo tung trang cua pdf
        """
        doc = pymupdf.open(pdf_path)
        pages = "\n".join([page.get_text() for page in doc])
        return pages
    def load_docx(self, docx_path):
        """
        Load van ban tu file Word (.docx), chi lay text, ke ca ky tu dac biet
        """
        doc = docx.Document(docx_path)
        texts = '\n'.join([para.text.strip() for para in doc.paragraphs if para.text.strip()])
        return texts

if __name__ == "__main__":
    loader = LoadData()
    #print(len(loader.get_file_from_raw_dir()))
    #print(loader.load_docx(RAW_PATH + "/qd-33-2023.docx"))
    print(loader.load_pdf(RAW_PATH + "/VanBanGoc_02_2026_QD-UBND_08012026-signed_01.pdf"))