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
    def download_document(self):
        """
        Download tất cả tài liệu trong trang hiện tại
        """
        pass
    def next_page(self):
        """
        Sang trang tiếp theo
        """
if __name__ == "__main__":
    log()
    driver = chrome_webdriver()
    crawl = Crawl(driver, KEY_WORD, output_path)
    crawl.open_page("https://vbpl.vn/")
    crawl.search_keyword()
    crawl.search_extra()