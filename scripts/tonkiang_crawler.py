#!/usr/bin/env python3
"""
Tonkiang.us IPTV爬虫 - 优化版（GitHub Actions专用）
"""

import requests
import re
import os
import random
import hashlib
import time
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
        self.print_lock = threading.Lock()

    def print_with_lock(self, message):
        with self.print_lock:
            print(message)

    @lru_cache(maxsize=100)
    def generate_random_hash(self):
        return hashlib.md5(str(random.random()).encode()).hexdigest()[:8]

    def search_iptv_page(self, keyword, page):
        try:
            wait_time = random.uniform(1, 3)
            self.print_with_lock(f"等待 {wait_time:.2f} 秒后开始搜索: {keyword} 第 {page} 页")
            time.sleep(wait_time)
            
            params = {
                'iptv': keyword,
                'l': self.generate_random_hash(),
                'page': page if page > 1 else None
            }
            
            self.print_with_lock(f"正在搜索: {keyword} 第 {page} 页")
            
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            self.print_with_lock(f"第 {page} 页获取成功，状态码: {response.status_code}")
            parsed_links = self.parse_links_only(response.text, keyword)
            
            # 将元组列表转换为字典列表
            return [{'url': link, 'source': source} for link, source in parsed_links]
            
        except Exception as e:
            self.print_with_lock(f"⚠️ {keyword} 第{page}页错误: {str(e)}")
            return []

    def parse_links_only(self, html_content, source):
        self.print_with_lock(f"开始解析 {source} 的页面内容")
        
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
                    self.print_with_lock(f"找到链接: {link}")
        
        self.print_with_lock(f"为 {source} 找到 {len(links)} 个链接")
        return list(links)

    def verify_m3u8_batch(self, links_batch):
        """批量验证字典列表中的链接"""
        self.print_with_lock(f"开始批量验证 {len(links_batch)} 个链接")
        valid_links = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 直接使用字典中的url字段
            futures = {executor.submit(self._verify_single, item['url']): item for item in links_batch}
            for future in as_completed(futures):
                original_item = futures[future]
                try:
                    if future.result():
                        valid_links.append(original_item)
                        self.print_with_lock(f"✓ 验证通过: {original_item['url']}")
                    else:
                        self.print_with_lock(f"✗ 验证失败: {original_item['url']}")
                except Exception as e:
                    self.print_with_lock(f"验证链接时出错 {original_item['url']}: {e}")
        
        self.print_with_lock(f"批量验证完成，有效链接: {len(valid_links)} 个")
        return valid_links

    def _verify_single(self, url):
        try:
            wait_time = random.uniform(0.5, 1.5)
            time.sleep(wait_time)
            
            # 使用GET而不是HEAD，因为有些服务器可能不支持HEAD或返回不同的内容类型
            with self.session.get(url, timeout=(3, 5), stream=True) as resp:
                if resp.status_code != 200:
                    return False
                
                # 检查内容类型或内容本身
                content_type = resp.headers.get('content-type', '').lower()
                if 'mpegurl' in content_type or 'application/vnd.apple.mpegurl' in content_type:
                    return True
                
                # 如果不是预期的内容类型，检查内容前几个字符
                content_start = resp.raw.read(10).decode('utf-8', errors='ignore')
                return content_start.startswith('#EXTM3U')
        except:
            return False

    def run_concurrent(self, keywords, pages=2):
        self.print_with_lock(f"\n{'='*50}")
        self.print_with_lock("开始并发爬取")
        self.print_with_lock(f"{'='*50}")
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for keyword in keywords:
                if len(futures) > 0:
                    delay = random.uniform(2, 5)
                    self.print_with_lock(f"等待 {delay:.2f} 秒后处理下一个关键词")
                    time.sleep(delay)
                    
                futures.append(executor.submit(
                    self._process_keyword,
                    keyword,
                    pages
                ))
            
            for future in as_completed(futures):
                result = future.result()
                self.all_links.extend(result)
                self.print_with_lock(f"完成一个关键词的处理，找到 {len(result)} 个链接")
            
            if self.all_links:
                self.print_with_lock(f"\n开始验证所有找到的 {len(self.all_links)} 个链接")
                # 直接传递字典列表进行验证
                self.all_links = self.verify_m3u8_batch(self.all_links)
            else:
                self.print_with_lock("未找到任何链接，跳过验证阶段")

    def _process_keyword(self, keyword, pages):
        self.print_with_lock(f"\n开始处理关键词: {keyword}")
        links = []
        with ThreadPoolExecutor(max_workers=2) as page_executor:
            page_futures = [page_executor.submit(
                self.search_iptv_page,
                keyword,
                page
            ) for page in range(1, pages+1)]
            
            for future in as_completed(page_futures):
                links.extend(future.result())
        
        self.print_with_lock(f"关键词 {keyword} 处理完成，共找到 {len(links)} 个链接")
        return links

    def save_results(self, filename="ysws.m3u"):
        self.print_with_lock(f"\n开始保存结果到文件: {filename}")
        os.makedirs("output", exist_ok=True)
        filepath = os.path.join("output", filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for item in sorted(self.all_links, key=lambda x: x['source']):
                f.write(f'#EXTINF:-1 tvg-id="" tvg-name="{item["source"]}" tvg-logo="" group-title="CCTV",{item["source"]}\n')
                f.write(f'{item["url"]}\n')
        
        self.print_with_lock(f"成功保存 {len(self.all_links)} 个有效链接到 {filepath}")
        return filepath

def main():
    print("Tonkiang.us IPTV爬虫启动")
    print(f"开始时间: {datetime.now().isoformat()}")
    
    crawler = TonkiangCrawler()
    
    search_keywords = [
        "CCTV1", "CCTV2", "CCTV3", "CCTV4", "CCTV5",
        "CCTV6", "CCTV7", "CCTV8", "CCTV9", "CCTV10",
        "CCTV11", "CCTV12", "CCTV13", "CCTV14", "CCTV15",
        "CCTV16", "CCTV17", "CETV1", "CETV2", "CETV3", 
        "CETV4"
    ]
    pages_to_crawl = 6
    
    try:
        crawler.run_concurrent(search_keywords, pages_to_crawl)
        output_file = crawler.save_results()
        
        print(f"\n✅ 爬取完成！")
        print(f"📁 M3U文件: {output_file}")
        print(f"✅ 有效链接: {len(crawler.all_links)} 个")
        
        tv_counts = {}
        for item in crawler.all_links:
            source = item['source']
            tv_counts[source] = tv_counts.get(source, 0) + 1
        
        print("\n各频道链接数量统计:")
        for tv, count in sorted(tv_counts.items()):
            print(f"{tv}: {count} 个链接")
        
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



