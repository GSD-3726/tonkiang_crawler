#!/usr/bin/env python3
"""
Tonkiang.us IPTV爬虫 - 按卫视频道号搜索并输出对应链接（优化版）
"""

import requests
import re
import os
import time
import random
import hashlib
from datetime import datetime
import concurrent.futures
from threading import Lock

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
        self.all_links = []  # 存储所有找到的链接
        self.lock = Lock()  # 线程安全锁
        
        # 预编译正则表达式提升解析效率
        self.m3u8_pattern = re.compile(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?', re.IGNORECASE)
        self.onclick_pattern = re.compile(r'onclick="glshle\(\s*\'([^\']+?\.m3u8)\'\s*\)"', re.IGNORECASE)
        self.tag_pattern = re.compile(r'<tba[^>]*class="ergl"[^>]*>([^<]+\.m3u8)</tba>', re.IGNORECASE)

    def generate_random_hash(self):
        """生成随机哈希值"""
        random_str = str(random.random())
        return hashlib.md5(random_str.encode()).hexdigest()[:8]

    def search_single_page(self, keyword, page, interval):
        """搜索单页内容并添加间隔"""
        try:
            params = {
                'iptv': keyword,
                'l': self.generate_random_hash(),
                'page': page
            } if page > 1 else {
                'iptv': keyword,
                'l': self.generate_random_hash()
            }
            
            print(f"正在处理: {keyword} 第 {page} 页")
            response = self.session.get(
                self.base_url, 
                params=params, 
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            print(f"成功获取 {keyword} 第 {page} 页，状态码: {response.status_code}")
            return self.parse_links_only(response.text, keyword)
            
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {keyword} 第 {page} 页 - {e}")
        except Exception as e:
            print(f"解析失败: {keyword} 第 {page} 页 - {e}")
        finally:
            # 确保即使出错也执行间隔等待
            if interval > 0 and page > 1:
                print(f"等待 {interval} 秒后继续...")
                time.sleep(interval)
        return []

    def parse_links_only(self, html_content, source):
        """优化后的链接解析（使用预编译正则）"""
        found_links = []
        all_links = set()
        
        # 合并所有找到的链接
        for pattern in [self.m3u8_pattern, self.onclick_pattern, self.tag_pattern]:
            matches = pattern.findall(html_content)
            for link in matches:
                if not link.startswith(('http://', 'https://')):
                    link = 'https:' + link if link.startswith('//') else link
                all_links.add(link)
        
        # 线程安全地添加链接
        with self.lock:
            for link in all_links:
                found_links.append({
                    'url': link,
                    'source': source
                })
        
        return found_links

    def run(self, keywords=None, pages=4, interval=8):
        """优化后的主运行逻辑（并发处理）"""
        if not keywords:
            keywords = ["湖南卫视", "浙江卫视", "江苏卫视", "东方卫视", "北京卫视"]
        
        self.all_links = []
        total_links = 0
        
        # 使用线程池并发处理不同频道
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            for keyword in keywords:
                # 每个频道独立处理所有页面
                for page in range(1, pages + 1):
                    futures.append(executor.submit(
                        self.search_single_page,
                        keyword,
                        page,
                        interval if page > 1 else 0  # 第一页不需要等待
                    ))
            
            # 等待所有任务完成
            for future in concurrent.futures.as_completed(futures):
                links = future.result()
                if links:
                    with self.lock:
                        self.all_links.extend(links)
        
        # 去重处理
        seen_urls = set()
        unique_links = []
        for item in self.all_links:
            if item['url'] not in seen_urls:
                unique_links.append(item)
                seen_urls.add(item['url'])
        
        # 保存结果
        output_file, total_count = self.save_to_m3u(unique_links)
        return output_file, unique_links, total_count

    def save_to_m3u(self, links_data, filename="wstv.m3u", output_dir="output"):
        """保存结果为M3U格式文件"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for item in links_data:
                f.write(f'#EXTINF:-1 tvg-id="" tvg-name="{item["source"]}" tvg-logo="" group-title="卫视",{item["source"]}\n')
                f.write(f'{item["url"]}\n')
        
        print(f"成功保存 {len(links_data)} 个链接到 {filepath}")
        return filepath, len(links_data)

def main():
    """主函数"""
    print("Tonkiang.us IPTV爬虫启动 - 卫视频道优化版")
    print(f"开始时间: {datetime.now().isoformat()}")
    
    crawler = TonkiangCrawler()
    
    # 配置参数 - 卫视频道
    search_keywords = [
        "安徽卫视", "北京卫视", "重庆卫视", "东南卫视", "广东卫视",
        "广西卫视", "贵州卫视", "河北卫视", "河南卫视", "黑龙江卫视",
        "湖北卫视", "湖南卫视", "吉林卫视", "江苏卫视", "江西卫视",
        "辽宁卫视", "内蒙古卫视", "山东卫视", "山西卫视", "陕西卫视",
        "上海东方卫视", "四川卫视", "天津卫视", "西藏卫视", "新疆卫视",
        "云南卫视", "浙江卫视", "深圳卫视"
    ]
    pages_to_crawl = 4
    request_interval = 8
    
    try:
        output_file, all_links, total_count = crawler.run(
            search_keywords, 
            pages_to_crawl, 
            request_interval
        )
        
        if output_file:
            print("\n✅ 爬取完成！")
            print(f"📁 M3U文件: {output_file}")
            print(f"✅ 总链接数: {total_count} 个")
            
            # 统计各频道链接数量
            tv_counts = {}
            for item in all_links:
                tv_counts[item['source']] = tv_counts.get(item['source'], 0) + 1
            
            print("\n各频道链接数量统计:")
            for tv, count in sorted(tv_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"{tv}: {count} 个链接")
            
            # GitHub Actions输出
            if os.getenv('GITHUB_ACTIONS') == 'true':
                with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
                    print(f'output_file={output_file}', file=fh)
                    print(f'total_links={total_count}', file=fh)
        else:
            print("\n❌ 爬取失败，未找到任何链接")
            exit(1)
            
    except Exception as e:
        print(f"\n❌ 爬虫执行出错: {e}")
        exit(1)

if __name__ == "__main__":
    main()
