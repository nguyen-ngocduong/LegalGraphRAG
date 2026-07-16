from config.configs import RAW_PATH, PROCESSED_PATH
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time

KEY_WORD = "an ninh mạng"
output_path = RAW_PATH

from time import sleep
def log():
    logging.basicConfig(
        #filename = "logs/app.log",
        level=logging.INFO,
        format="%(asctime)s - [%(levelname)s] - %(message)s",
    )
    logging.info("="*20 + " START LOGGING " + "="*20)

def chrome_webdriver():
    options = webdriver.ChromeOptions()
    #options.add_argument("--headless")  # Chạy Chrome không hiển thị giao diện
    options.add_argument("--disable-gpu")  # Tắt GPU tăng hiệu suất
    options.add_argument("--no-sandbox")  # Tránh lỗi sandbox trong môi trường Linux

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def wait():
    time.sleep(5)

class Crawl:
    """
    Class này dùng để crawl dữ liệu từ các trang web: https://vbpl.vn/.
    - Các dữ liệu được crawl sẽ được lưu vào thư mục RAW_PATH (được định nghĩa trong config.yaml).
    - 
    """
    def __init__(self, driver, keyword, output_path) -> None:
        """
        Khởi tạo đối tượng Crawl
        - driver: đối tượng WebDriver của Selenium
        - keyword: từ khóa để tìm kiếm
        - output_path: đường dẫn để lưu dữ liệu crawl được
        """
        self.driver = driver
        self.keyword = keyword
        self.output_path = output_path
        self.wait = WebDriverWait(self.driver, 15)  # Thời gian chờ tối đa là 10 giây

    def _safe_click(self, by, value):
        element = self.wait.until(EC.presence_of_element_located((by, value)))
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
        try:
            self.wait.until(EC.element_to_be_clickable((by, value))).click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)
    
    def open_page(self, url):
        """
        Mở trang web với URL được cung cấp
        - url: URL của trang web cần mở
        """
        self.driver.get(url)
        logging.info(f"Đang mở trang web: {url}")
        try:
            # Chờ cho đến khi phần tử có class "search-form" xuất hiện
            self.wait.until(EC.presence_of_element_located((By.ID, "keyword")))
            logging.info("Trang web đã tải xong.")
        except Exception as e:
            logging.error(f"Không thể tải trang web: {e}")
            self.driver.quit()
    def search_keyword(self):
        """
        Tìm kiếm từ khóa trên trang web
        """
        try:
            search_input = self.driver.find_element(By.ID, "keyword")
            search_input.clear()
            search_input.send_keys(self.keyword)
            search_input.send_keys(Keys.ENTER)
            logging.info(f"Đang tìm kiếm từ khóa: {self.keyword}")
            # Chờ cho đến khi kết quả tìm kiếm xuất hiện
            #self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "search-results")))
            wait()
            logging.info("Kết quả tìm kiếm đã tải xong.")
        except Exception as e:
            logging.error(f"Không thể tìm kiếm từ khóa: {e}")
            self.driver.quit()
    def search_extra(self):
        """
        Tìm kiếm nâng cao
        - Chon tieu chi "chính xác cụm từ trên"
        - Click vao nút "Tìm kiếm nâng cao" để mở form tìm kiếm nâng cao
        - Chon tieu chi "Tinh trang hieu luc" là "Còn hiệu lực"
        - Click vao "Tìm kiếm" => Lấy kết quả tìm kiếm
        """
        # Chinh xac cum tu tren
        try:
            self._safe_click(By.XPATH, "//label[contains(.,'Chính xác cụm từ trên')] | //span[contains(.,'Chính xác cụm từ trên')]/ancestor::label[1]")
            logging.info("Đã chọn tiêu chí 'Chính xác cụm từ trên'.")
            # Click vao nút "Tìm kiếm nâng cao"
            self._safe_click(By.XPATH, "//button[contains(.,'Tìm kiếm nâng cao')] | //span[contains(.,'Tìm kiếm nâng cao')]/ancestor::button[1]")
            logging.info("Đã click vào nút 'Tìm kiếm nâng cao'.")
            # Chon tieu chi "Tinh trang hieu luc" là "Còn hiệu lực"
            self._safe_click(By.XPATH, "//*[contains(text(),'Tình trạng hiệu lực') and (self::button or self::div or self::span or self::label)]")
            logging.info("Đã click vào dropdown 'Tình trạng hiệu lực'.")
            # Chọn "Còn hiệu lực"
            self._safe_click(By.XPATH, "//*[contains(text(),'Còn hiệu lực') and (self::button or self::div or self::span or self::label)]")
            logging.info("Đã chọn 'Còn hiệu lực' trong dropdown 'Tình trạng hiệu lực'.")
            # Click vao "Tìm kiếm"
            self._safe_click(By.XPATH, "//button[contains(.,'Tìm kiếm')] | //span[contains(.,'Tìm kiếm')]/ancestor::button[1]")
            logging.info("Đã click vào nút 'Tìm kiếm' trong tìm kiếm nâng cao.")
            # Chờ cho đến khi kết quả tìm kiếm xuất hiện
            wait()
        except Exception as e:
            logging.error(f"Không thể tìm kiếm nâng cao: {e}")
            self.driver.quit()
    def next_page(self):
        """
        Sang trang tiếp theo
        """
        try:
            self._safe_click(
                By.XPATH, "//li[contains(@class,'ant-pagination-next')]//button"
            )
            logging.info("Đã sang trang tiếp theo!")
        except Exception as e:
            logging.error(f"Không thể sang trang tiếp theo: {e}")
            self.driver.quit()

    def _get_active_page(self):
        try:
            return self.driver.find_element(By.CSS_SELECTOR, ".ant-pagination-item-active").text.strip()
        except Exception:
            return None

    def _has_next_page(self):
        try:
            next_item = self.driver.find_element(By.CSS_SELECTOR, ".ant-pagination-next")
            classes = next_item.get_attribute("class") or ""
            if "disabled" in classes:
                return False

            next_button = next_item.find_element(By.CSS_SELECTOR, "button")
            return next_button.is_enabled()
        except Exception:
            return False

    def _get_document_links_on_page(self) -> list:
        """
        Lấy danh sách (title, pdf_url) từ các tài liệu trên trang hiện tại.
        Xử lý ngay trên trang để tránh StaleElementReferenceException khi chuyển trang.
        """
        results = []
        documents = self.driver.find_elements(
            By.CSS_SELECTOR, ".ant-list-item.DocumentListSearchView_listItem__Oggvt"
        )
        logging.info(f"Số lượng tài liệu trên trang hiện tại: {len(documents)}")
        for doc in documents:
            try:
                title = doc.find_element(
                    By.CSS_SELECTOR, ".DocumentCard_documentTitle__aE_F_"
                ).text.strip()
                results.append({"title": title, "element": doc})
            except Exception as e:
                logging.warning(f"Không lấy được title tài liệu: {e}")
        return results

    def get_document(self) -> list:
        """
        Lấy danh sách tài liệu trên trang hiện tại.
        Trả về list dict {title, element}.
        """
        page_docs = self._get_document_links_on_page()
        logging.info(f"Tổng số tài liệu tìm thấy trên trang hiện tại: {len(page_docs)}")
        return page_docs
    def download_document(self, doc_info):
        """
        doc_info: dict chứa title và element của một <li> document
        """

        document = doc_info.get("element") if isinstance(doc_info, dict) else doc_info
        if document is None:
            logging.error("Không có element tài liệu hợp lệ để tải xuống.")
            return

        title = doc_info.get("title") if isinstance(doc_info, dict) else None
        original_window = self.driver.current_window_handle

        # ======================================================
        # 1. Lấy title_element
        # ======================================================
        try:
            title_element = document.find_element(By.XPATH, ".//div[contains(@class,'DocumentCard_documentTitle')]")
        except Exception as e:
            logging.error(f"Không thể lấy title_element: {e}")
            return 
        # ======================================================
        # 2. Lấy title
        # ======================================================
        title = title or title_element.text.strip()
        logging.info(f"Đang tải xuống tài liệu: {title}")
        # ======================================================
        # 3. Click nút PDF
        # ======================================================
        try:
            pdf_button = document.find_element(
                By.XPATH,
                ".//button[.//span[normalize-space()='PDF']]"
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                pdf_button,
            )
            try:
                pdf_button.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", pdf_button)
        except Exception as e:
            logging.error(f"Không thể click nút PDF cho tài liệu '{title}': {e}")
            return
        # ======================================================
        # 4. Lấy link
        # ======================================================
        link = None
        try: 
            self.wait.until(
                lambda d: len(d.window_handles) > 1
            )
            self.driver.switch_to.window(
                self.driver.window_handles[-1]
            )
            link = self.driver.current_url
            logging.info(f"Link tài liệu: {link}")
        except Exception as e:
            logging.error(f"Không thể lấy link tài liệu '{title}': {e}")
            return
        # ======================================================
        # 5. Click tab "Tải về"
        # ======================================================
        try:
            try: 
                self._safe_click(
                    By.CSS_SELECTOR,
                    "div[data-node-key='tai-ve']"
                )
            except Exception as e:
                logging.error(f"Không thể click tab 'Tải về' cho tài liệu '{title}': {e}")
                return
            # ======================================================
            # 6. Click icon download DOC
            # ======================================================
            try: 
                download_btn = self.wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.CSS_SELECTOR,
                            "button.ant-btn-icon-only"
                        )
                    )
                )
                download_btn.click()
            except Exception as e:
                logging.error(f"Không thể click nút download cho tài liệu '{title}': {e}")
                return
            # ======================================================
            # 7. Chờ tải xong
            # ======================================================
            wait()

            return {
                "title_element": title_element,
                "title": title,
                "link": link
            }
        finally:
            try:
                if self.driver.current_window_handle != original_window:
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
            except Exception as e:
                logging.warning(f"Không thể quay lại trang kết quả cho tài liệu '{title}': {e}")
    def run(self):
        """
        Chạy quá trình crawl dữ liệu
        """
        self.open_page("https://vbpl.vn/")
        self.search_keyword()
        self.search_extra()
        while True:
            document_infos = self.get_document()
            for doc_info in document_infos:
                self.download_document(doc_info)

            if not self._has_next_page():
                break

            active_page_before = self._get_active_page()
            self.next_page()
            self.wait.until(lambda driver: self._get_active_page() != active_page_before)
            wait()
            
if __name__ == "__main__":
    log()
    crawl = Crawl(chrome_webdriver(), KEY_WORD, output_path)
    crawl.run()