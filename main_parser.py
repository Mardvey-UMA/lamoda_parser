import os
import json
import time
import random
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


@dataclass
class ProductData:
    url: str
    price: Optional[str] = None
    old_price: Optional[str] = None
    description: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class ParserConfig:
    input_file: str = "product_links.json"
    result_dir: str = "products_result"
    checkpoint_dir: str = "checkpoints"
    start_from: int = 0
    max_products: Optional[int] = None
    request_delay: float = 2.0
    use_selenium: bool = True
    headless: bool = False
    timeout: int = 30


class ProductDetailsParser:
    def __init__(self, config: ParserConfig):
        self.config = config
        self.product_links: List[str] = []
        self.current_index = config.start_from
        self.driver = None

        # Создаём папки для результатов и чекпоинтов
        os.makedirs(self.config.result_dir, exist_ok=True)
        os.makedirs(self.config.checkpoint_dir, exist_ok=True)

        if self.config.use_selenium:
            options = uc.ChromeOptions()
            if self.config.headless:
                options.add_argument('--headless')
            self.driver = uc.Chrome(options=options)

    def __del__(self):
        if self.driver:
            self.driver.quit()

    def load_links(self):
        with open(self.config.input_file, 'r', encoding='utf-8') as f:
            self.product_links = json.load(f)
        if self.config.max_products:
            self.product_links = self.product_links[: self.config.max_products]

    def load_checkpoint(self):
        cp_file = os.path.join(self.config.checkpoint_dir, "checkpoint.json")
        if os.path.exists(cp_file):
            try:
                with open(cp_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    last = data.get("last_index")
                    if isinstance(last, int):
                        self.current_index = last + 1
                        print(f"Resuming from index {self.current_index}")
            except Exception as e:
                print(f"Ошибка чтения чекпоинта: {e}")

    def save_checkpoint(self, index: int):
        cp_file = os.path.join(self.config.checkpoint_dir, "checkpoint.json")
        with open(cp_file, 'w', encoding='utf-8') as f:
            json.dump({"last_index": index}, f)

    def get_page_html(self, url: str) -> Optional[str]:
        time.sleep(self.config.request_delay + random.uniform(0, 2))

        if self.config.use_selenium:
            try:
                _ = self.driver.current_url
            except:
                self.driver.quit()
                options = uc.ChromeOptions()
                if self.config.headless:
                    options.add_argument('--headless')
                self.driver = uc.Chrome(options=options)

            try:
                self.driver.get(url)
                WebDriverWait(self.driver, self.config.timeout).until(
                    EC.presence_of_element_located((By.ID, "reviews-and-questions"))
                )
                return self.driver.page_source
            except Exception as e:
                print(f"Ошибка Selenium при загрузке {url}: {e}")
                return None
        else:
            try:
                resp = requests.get(
                    url,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=self.config.timeout
                )
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                print(f"Error requests при загрузке {url}: {e}")
                return None

    def parse_product_page(self, html: str, url: str) -> ProductData:
        soup = BeautifulSoup(html, 'html.parser')
        pd = ProductData(url=url)

        price_elements = soup.find_all('span', class_='_price_g09b8_11')
        if len(price_elements) >= 2:
            pd.old_price = price_elements[0].get_text(strip=True)
            pd.price = price_elements[1].get_text(strip=True)
        elif price_elements:
            pd.price = price_elements[0].get_text(strip=True)

        info = soup.find('div', id='reviews-and-questions')
        if info:
            desc = info.find('div', class_='_description_795ct_30')
            if desc:
                pd.description = desc.get_text(strip=True)

            for item in info.find_all('p', class_='_item_ajirn_2'):
                name = item.find('span', class_='_attributeName_ajirn_14')
                val = item.find('span', class_='_value_ajirn_27')
                if name and val:
                    pd.attributes[name.get_text(strip=True)] = val.get_text(strip=True)

        return pd

    def extract_image_urls(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, 'html.parser')
        urls: List[str] = []
        for div in soup.find_all('div', class_=lambda c: c and 'ui-product-page-gallery' in c):
            img = div.find('img')
            if img and img.get('src'):
                full = urljoin(base_url, img['src'])
                urls.append(full)
        return urls

    def save_product(self, index: int, pd: ProductData, html: str):
        folder = os.path.join(self.config.result_dir, str(index))
        os.makedirs(folder, exist_ok=True)

        img_urls = self.extract_image_urls(html, pd.url)
        saved = False
        for img_url in img_urls:
            for attempt in range(3):
                try:
                    r = requests.get(img_url, timeout=10)
                    if r.status_code == 200:
                        ext = os.path.splitext(img_url)[1] or '.jpg'
                        path = os.path.join(folder, 'image' + ext)
                        with open(path, 'wb') as f:
                            f.write(r.content)
                        saved = True
                        break
                except Exception as e:
                    print(f"Попытка {attempt+1} неудачна для {img_url}: {e}")
                    time.sleep(1)
            if saved:
                break

        if not saved:
            open(os.path.join(folder, 'no_image.txt'), 'w').close()

        data = asdict(pd)
        with open(os.path.join(folder, 'data.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def run(self):
        self.load_links()
        self.load_checkpoint()
        total = len(self.product_links)
        print(f"Стартуем с индекса {self.current_index} из {total} товаров")

        for idx in range(self.current_index, total):
            url = self.product_links[idx]
            print(f"[{idx+1}/{total}] {url}")

            html = self.get_page_html(url)
            if not html:
                print(f"  → пропускаем товар {idx} из-за ошибки загрузки")
                continue

            try:
                pd = self.parse_product_page(html, url)
                self.save_product(idx, pd, html)
                self.save_checkpoint(idx)
            except Exception as e:
                print(f"  → ошибка обработки товара {idx}: {e}")
                continue

        cp_file = os.path.join(self.config.checkpoint_dir, "checkpoint.json")
        if os.path.exists(cp_file):
            os.remove(cp_file)
        print("Все товары обработаны.")

if __name__ == "__main__":
    config = ParserConfig(
        input_file="lamoda_product_links.json",
        result_dir="products_result",
        checkpoint_dir="checkpoints",
        start_from=0,
        max_products=None,
        request_delay=2.5,
        use_selenium=True,
        headless=False,
        timeout=30
    )
    parser = ProductDetailsParser(config)
    parser.run()
