import json
import os
import time
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests
from dataclasses import dataclass, asdict
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


@dataclass
class ParserConfig:
    base_url: str = "https://www.lamoda.ru/c/369/clothes-platiya/"
    start_page: int = 1
    end_page: Optional[int] = None
    min_links: int = 50
    max_links: int = 1000
    output_file: str = "product_links.json"
    checkpoint_file: str = "checkpoint_links.json"
    request_delay: float = 2.0
    use_selenium: bool = True
    headless: bool = True
    timeout: int = 30


class ProductLinksParser:
    def __init__(self, config: ParserConfig):
        self.config = config
        self.collected_links = []
        self.current_page = config.start_page
        self.driver = None
        
        if config.use_selenium:
            options = uc.ChromeOptions()
            if config.headless:
                options.add_argument('--headless')
            self.driver = uc.Chrome(options=options)
    
    def __del__(self):
        if self.driver:
            self.driver.quit()
    
    def load_checkpoint(self) -> bool:
        if os.path.exists(self.config.checkpoint_file):
            with open(self.config.checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.collected_links = data.get('links', [])
                self.current_page = data.get('current_page', self.config.start_page)
                print(f"Loaded checkpoint: {len(self.collected_links)} links, current page: {self.current_page}")
                return True
        return False
    
    def save_checkpoint(self):
        data = {
            'links': self.collected_links,
            'current_page': self.current_page
        }
        with open(self.config.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def save_results(self):
        with open(self.config.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.collected_links, f, ensure_ascii=False, indent=2)
    
    def get_page_html(self, url: str) -> Optional[str]:
        time.sleep(self.config.request_delay)
        
        if self.config.use_selenium:
            self.driver.get(url)
            try:
                WebDriverWait(self.driver, self.config.timeout).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "grid__catalog"))
                )
                return self.driver.page_source
            except Exception as e:
                print(f"Error loading page {url}: {str(e)}")
                return None
        else:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(url, headers=headers, timeout=self.config.timeout)
                response.raise_for_status()
                return response.text
            except Exception as e:
                print(f"Error fetching page {url}: {str(e)}")
                return None
    
    def parse_links_from_html(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, 'html.parser')
        product_links = []

        grid = soup.find('div', class_='grid__catalog')
        if not grid:
            return []

        product_cards = grid.find_all('a', class_='x-product-card__pic')
        for card in product_cards:
            href = card.get('href')
            if href and href.startswith('/p/'):
                full_url = f"https://www.lamoda.ru{href}"
                if full_url not in product_links and full_url not in self.collected_links:
                    product_links.append(full_url)
        
        return product_links
    
    def run(self):
        self.load_checkpoint()
        
        print(f"Starting parser from page {self.current_page}")
        
        while True:
            if len(self.collected_links) >= self.config.max_links:
                print(f"Reached maximum links limit ({self.config.max_links})")
                break

            if self.current_page == 1:
                url = self.config.base_url
            else:
                url = f"{self.config.base_url}?page={self.current_page}"
            
            print(f"Processing page {self.current_page}: {url}")

            html = self.get_page_html(url)
            if not html:
                print(f"Failed to get page {self.current_page}, stopping")
                break

            new_links = self.parse_links_from_html(html)
            if not new_links:
                print(f"No new links found on page {self.current_page}, stopping")
                break

            self.collected_links.extend(new_links)
            print(f"Found {len(new_links)} new links (total: {len(self.collected_links)})")

            self.save_checkpoint()

            if len(self.collected_links) >= self.config.min_links and self.config.end_page and self.current_page >= self.config.end_page:
                print(f"Reached target page {self.config.end_page} with enough links")
                break

            self.current_page += 1

        self.save_results()
        print(f"Finished parsing. Total links collected: {len(self.collected_links)}")


if __name__ == "__main__":
    config = ParserConfig(
        start_page=0,
        end_page=1000,
        min_links=50,
        max_links=20000000,
        output_file="lamoda_product_links.json",
        checkpoint_file="checkpoint_links.json",
        request_delay=2.5,
        use_selenium=True,
        headless=True
    )
    
    parser = ProductLinksParser(config)
    parser.run()