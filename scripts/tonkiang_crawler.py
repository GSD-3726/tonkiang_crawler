#!/usr/bin/env python3
"""
Tonkiang.us IPTV爬虫 - 优化版（GitHub Actions专用）
"""

import requests
import re
import os
import random
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import threading

class TonkiangCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.base_url = "https://tonkiang.us/"
        self.request_timeout = (5, 15)
        self.all_links = []
        self.lock = threading.Lock()

    @lru_cache(maxsize=100)
    def generate_random_hash(self):
        """带缓存的随机哈希生成"""
        return hashlib.md5(str(random.random()).encode()).hexdigest()[:8]

    def search_iptv_page(self, keyword, page):
        """单页搜索（线程安全版）"""
        try:
            params = {
                'iptv': keyword,
                'l': self.generate_random_hash(),
                'page': page if page > 1 else None
            }
            
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=self.request_timeout
            )
            response.raise_for_status()
            return self.parse_links_only(response.text, keyword)
            
        except Exception as e:
            print(f"⚠️ {keyword} 第{page}页错误: {str(e)}")
            return []

    def parse_links_only(self, html_content, source):
        """带来源标注的链接解析"""
        patterns = [
            r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?',
            r'onclick="glshle\(\s*\'([^\']+?\.m3u8)\'\s*\)"',
            r'<tba[^>]*class="ergl"[^>]*>([^<]+\.m3u8)</tba>'
        ]
        
        links = set()
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for link in matches:
                if not link.startswith(('http://', 'https://')):
                    link = 'https:' + link if link.startswith('//') else None
                if link:
                    links.add((link, source))
        return list(links)

    def verify_m3u8_batch(self, links_batch):
        """批量验证链接有效性"""
        valid_links = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self._verify_single, link): (link, source) 
                      for link, source in links_batch}
            for future in as_completed(futures):
                link, source = futures[future]
                try:
                    if future.result():
                        valid_links.append({'url': link, 'source': source})
                except:
                    pass
        return valid_links

    def _verify_single(self, url):
        """单链接验证（带重试机制）"""
        try:
            with self.session.head(url, timeout=(3, 5), allow_redirects=True) as resp:
                return resp.status_code == 200 and 'mpegurl' in resp.headers.get('content-type', '')
        except:
            return False

    def run_concurrent(self, keywords, pages=2):
        """并发执行主逻辑"""
        with ThreadPoolExecutor(max_workers=3) as executor:
            # 第一阶段：并发爬取
            futures = []
            for keyword in keywords:
                futures.append(executor.submit(
                    self._process_keyword,
                    keyword,
                    pages
                ))
            
            # 第二阶段：收集结果
            for future in as_completed(futures):
                self.all_links.extend(future.result())
            
            # 第三阶段：批量验证
            if self.all_links:
                self.all_links = self.verify_m3u8_batch(self.all_links)

    def _process_keyword(self, keyword, pages):
        """单个关键词处理流程"""
        links = []
        with ThreadPoolExecutor(max_workers=2) as page_executor:
            page_futures = [page_executor.submit(
                self.search_iptv_page,
                keyword,
                page
            ) for page in range(1, pages+1)]
            
            for future in as_completed(page_futures):
                links.extend(future.result())
        return links

    def save_results(self, filename="ysws.m3u"):
        """保存优化后的结果"""
        os.makedirs("output", exist_ok=True)
        filepath = os.path.join("output", filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for item in sorted(self.all_links, key=lambda x: x['source']):
                f.write(f'#EXTINF:-1 tvg-id="" tvg-name="{item["source"]}" tvg-logo="" group-title="CCTV",{item["source"]}\n')
                f.write(f'{item["url"]}\n')
        
        print(f"成功保存 {len(self.all_links)} 个有效链接到 {filepath}")
        return filepath

def main():
    """主函数"""
    print("Tonkiang.us IPTV爬虫启动")
    print(f"开始时间: {datetime.now().isoformat()}")
    
    crawler = TonkiangCrawler()
    
    # 配置参数
    search_keywords = [
        "CCTV1", "CCTV2", "CCTV3", "CCTV4", "CCTV5",
        "CCTV6", "CCTV7", "CCTV8", "CCTV9", "CCTV10",
        "CCTV11", "CCTV12", "CCTV13", "CCTV14", "CCTV15",
        "CCTV16", "CCTV17"
    ]
    pages_to_crawl = 4
    request_interval = 8
    
    try:
        # 并发执行爬取
        crawler.run_concurrent(search_keywords, pages_to_crawl)
        
        # 保存结果
        output_file = crawler.save_results()
        
        print(f"\n✅ 爬取完成！")
        print(f"📁 M3U文件: {output_file}")
        print(f"✅ 有效链接: {len(crawler.all_links)} 个")
        
        # 在GitHub Actions环境中设置输出变量
        if os.getenv('GITHUB_ACTIONS') == 'true':
            with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
                print(f'output_file={output_file}', file=fh)
                print(f'total_links={len(crawler.all_links)}', file=fh)
                print(f'valid_links={len(crawler.all_links)}', file=fh)
                
    except Exception as e:
        print(f"\n❌ 爬虫执行出错: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()

