import pymupdf
import docx
from docx.oxml.ns import qn
import os
import logging
import subprocess
import tempfile
from config.configs import RAW_PATH, PROCESSED_PATH
from crawl.crawl import log
from pathlib import Path
class LoadData:
    """
    Tạo một lớp Load Data:
    - Chứa các phương thức để tải dữ liệu từ các nguồn khác nhau (PDF, DOCX).
    - Đầu vào raw_dir: là các tài liệu đinh dạng pdf, doc được lưu ở RAW_PATH định nghĩa ở config.yaml
    """
    def __init__(self, raw_dir=RAW_PATH, processed_dir = PROCESSED_PATH) -> None:
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
    def get_file_from_raw_dir(self) -> list:
        """
        Lấy tất cả các file trong thư mục raw_dir
        """
        try:
            all_files = [file for file in os.listdir(self.raw_dir) if os.path.isfile(os.path.join(self.raw_dir, file))]
            logging.info(f"Đã lấy tất cả các file từ {self.raw_dir} - có {len(all_files)} file tất cả!!")
            return all_files
        except Exception as e:
            logging.info(f"Lỗi khi đọc file từ {self.raw_dir}")
            return
    def load_pdf(self, pdf_path: str | Path) -> str:
        """
        Load theo tung trang cua pdf
        """
        try:
            doc = pymupdf.open(pdf_path)
            pages = "\n".join([page.get_text() for page in doc])
            logging.info(f"Đã đọc xong file {pdf_path}")
            return pages
        except Exception as e:
            logging.error(f"Lỗi {e} khi đọc file {pdf_path}!")
            return
    @staticmethod
    def _read_table_as_text(table) -> str:
        """
        Chuyển nội dung một bảng Word thành text thuần,
        mỗi hàng là một dòng, các ô cách nhau bằng ' | '.
        Bỏ qua các ô trùng lặp do merged cells.
        """
        rows_text = []
        for row in table.rows:
            seen = set()
            cells_text = []
            for cell in row.cells:
                cell_val = cell.text.strip()
                # python-docx trả về ô merged nhiều lần → lọc trùng
                if id(cell._tc) not in seen:
                    seen.add(id(cell._tc))
                    cells_text.append(cell_val)
            row_line = " | ".join(cells_text)
            if row_line.strip(" |"):
                rows_text.append(row_line)
        return "\n".join(rows_text)

    def load_docx(self, docx_path: str | Path) -> str:
        """
        Load văn bản từ file Word (.docx).
        Đọc đúng thứ tự xuất hiện trong tài liệu:
        paragraph và table xen kẽ nhau (không đọc tất cả paragraph trước rồi mới đọc table).
        """
        try:
            doc = docx.Document(docx_path)
            texts = []

            # Duyệt qua các block-level element theo đúng thứ tự trong body
            for block in doc.element.body:
                # Paragraph
                if block.tag == qn("w:p"):
                    para = docx.text.paragraph.Paragraph(block, doc)
                    text = para.text.strip()
                    if text:
                        texts.append(text)
                # Table
                elif block.tag == qn("w:tbl"):
                    table = docx.table.Table(block, doc)
                    table_text = self._read_table_as_text(table)
                    if table_text:
                        texts.append(table_text)

            logging.info(f"Đã đọc xong file {docx_path}")
            return "\n".join(texts)
        except Exception as e:
            logging.error(f"Lỗi {e} khi đọc file {docx_path}!")
            return
    def load_doc(self, doc_path: str | Path) -> str:
        """
        Load file Word cu (.doc) bang cach chuyen tam sang .docx roi doc lai noi dung.
        """
        try:
            doc_path = Path(doc_path)
            with tempfile.TemporaryDirectory() as temp_dir:
                convert_result = subprocess.run(
                    [
                        "soffice",
                        "--headless",
                        "--convert-to",
                        "docx",
                        "--outdir",
                        temp_dir,
                        str(doc_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if convert_result.returncode != 0:
                    logging.error(
                        f"Khong the chuyen file {doc_path} sang docx: {convert_result.stderr.strip()}"
                    )
                    return

                converted_path = Path(temp_dir) / f"{doc_path.stem}.docx"
                if not converted_path.exists():
                    logging.error(f"Khong tim thay file sau khi chuyen doi: {converted_path}")
                    return

                return self.load_docx(converted_path)
        except Exception as e:
            logging.error(f"Lỗi {e} khi đọc file {doc_path}!")
            return
    def save_to_process_path(self):
        """
        Lưu các file sau khi đọc được (pdf, docx) thành file txt
        - Output_Dir: PROCESSED_PATH - được định nghĩa ở file config
        """
        try:
            os.makedirs(self.processed_dir, exist_ok=True)

            processed_count = 0
            for file_name in self.get_file_from_raw_dir():
                source_path = Path(self.raw_dir) / file_name
                file_suffix = source_path.suffix.lower()

                if file_suffix == ".pdf":
                    content = self.load_pdf(source_path)
                elif file_suffix == ".doc":
                    content = self.load_doc(source_path)
                elif file_suffix == ".docx":
                    content = self.load_docx(source_path)
                else:
                    logging.warning(f"Bỏ qua file không hỗ trợ: {source_path}")
                    continue

                if not content:
                    logging.warning(f"Không có nội dung để lưu cho file: {source_path}")
                    continue

                output_path = Path(self.processed_dir) / f"{source_path.stem}.txt"
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)

                processed_count += 1
                logging.info(f"Đã lưu file: {output_path}")

            logging.info(f"DONE! Đã xử lý {processed_count} file.")
            return processed_count
        except Exception as e:
            logging.error(f"Lỗi {e} khi đang cố gắng lưu vào {self.processed_dir}")
    def run(self):
        """
        - Chạy quá trình load data từ RAW_PATH và lưu vào PROCESSED_PATH
        """
        self.save_to_process_path()


if __name__ == "__main__":
    log()
    loader = LoadData()
    # print(len(loader.get_file_from_raw_dir()))
    # print("="*100)
    # print(loader.load_doc(RAW_PATH + "/179_2025_ND-CP_663165.doc"))
    # print("="*100)
    # print(loader.load_docx(RAW_PATH + "/24. NQ_hỗ trợ người làm công tác chuyển đổi số (trình ký).docx"))
    #print(loader.load_pdf(RAW_PATH + "/VanBanGoc_02_2026_QD-UBND_08012026-signed_01.pdf"))
    loader.run()