#!/usr/bin/env python3
"""
Tonkiang.us IPTV爬虫 - 按CCTV频道号搜索并输出对应链接
优化版本：减少运行时间
"""

import requests
import re
import os
import time
import random
import hashlib
import concurrent.futures
from datetime import datetime
from urllib.parse import urlencode

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
        self.verified_links = set()  # 存储已验证的链接，避免重复验证

    def generate_random_hash(self):
        """生成随机哈希值"""
        random_str = str(random.random())
        return hashlib.md5(random_str.encode()).hexdigest()[:8]

    def search_iptv_page(self, keyword_page):
        """搜索指定页面的IPTV频道"""
        keyword, page = keyword_page
        params = {
            'iptv': keyword,
            'l': self.generate_random_hash()
        }
        
        # 添加分页参数
        if page > 1:
            params['page'] = page
        
        try:
            print(f"正在搜索: {keyword} 第 {page} 页")
            
            response = self.session.get(
                self.base_url, 
                params=params, 
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            print(f"第 {page} 页获取成功，状态码: {response.status_code}")
            return self.parse_links_only(response.text)
            
        except requests.exceptions.Timeout:
            print(f"第 {page} 页请求超时")
            return []
        except requests.exceptions.RequestException as e:
            print(f"第 {page} 页请求错误: {e}")
            return []
        except Exception as e:
            print(f"第 {page} 页解析错误: {e}")
            return []

    def parse_links_only(self, html_content):
        """只解析M3U8链接，不尝试匹配频道名称"""
        found_links = []
        
        # 查找所有M3U8链接
        m3u8_pattern = r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?'
        m3u8_links = re.findall(m3u8_pattern, html_content, re.IGNORECASE)
        
        # 查找onclick事件中的M3U8链接
        onclick_pattern = r'onclick="glshle\(\s*\'([^\']+?\.m3u8)\'\s*\)"'
        onclick_links = re.findall(onclick_pattern, html_content, re.IGNORECASE)
        
        # 查找特定标签中的M3U8链接
        tag_pattern = r'<tba[^>]*class="ergl"[^>]*>([^<]+\.m3u8)</tba>'
        tag_links = re.findall(tag_pattern, html_content, re.IGNORECASE)
        
        # 合并所有找到的链接
        all_links = list(set(m3u8_links + onclick_links + tag_links))
        
        # 处理链接
        for link in all_links:
            # 确保链接是完整的URL
            if not link.startswith(('http://', 'https://')):
                if link.startswith('//'):
                    link = 'https:' + link
                else:
                    continue
            
            found_links.append(link)
            print(f"找到链接: {link}")
        
        return found_links

    def verify_m3u8(self, m3u8_url):
        """验证M3U8链接有效性"""
        if m3u8_url in self.verified_links:
            return True
            
        try:
            # 只请求头部信息，不下载完整内容
            response = self.session.head(m3u8_url, timeout=(3, 5), allow_redirects=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                # 检查是否为M3U8内容类型
                if 'mpegurl' in content_type or 'application/vnd.apple.mpegurl' in content_type:
                    self.verified_links.add(m3u8_url)
                    return True
                    
            # 如果HEAD请求失败，尝试GET请求但只获取部分内容
            response = self.session.get(m3u8_url, timeout=(3, 5), stream=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                content = response.text[:500]  # 只读取前500个字符
                
                # 检查M3U8特征
                if ('mpegurl' in content_type or 
                    content.startswith('#EXTM3U') or 
                    '#EXTINF' in content):
                    self.verified_links.add(m3u8_url)
                    return True
                    
            return False
        except Exception as e:
            print(f"验证链接失败: {e}")
            return False

    def search_keyword_pages(self, keyword, pages=3):
        """搜索单个关键词的多页内容"""
        keyword_links = []
        
        # 创建任务列表
        tasks = [(keyword, page) for page in range(1, pages + 1)]
        
        # 使用线程池并发执行
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(self.search_iptv_page, tasks))
            
            for links in results:
                if links:
                    keyword_links.extend(links)
        
        return keyword_links

    def save_to_m3u(self, links_data, filename="ysws3366.m3u", output_dir="github"):
        """保存结果为M3U格式文件"""
        # 创建输出目录
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"创建目录: {output_dir}")
        
        filepath = os.path.join(output_dir, filename)
        
        # 使用线程池并发验证链接
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # 准备验证任务
            verification_tasks = {item['url']: item for item in links_data}
            
            # 并发验证
            verified_urls = {}
            for url, item in verification_tasks.items():
                if self.verify_m3u8(url):
                    verified_urls[url] = item
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                # 写入M3U文件头
                f.write('#EXTM3U\n')
                
                # 写入每个有效链接
                for url, item in verified_urls.items():
                    source = item['source']
                    f.write(f'#EXTINF:-1 tvg-id="" tvg-name="{source}" tvg-logo="" group-title="CCTV",{source}\n')
                    f.write(f'{url}\n')
                    print(f"✓ 已添加有效链接: {source} -> {url}")
        
        valid_count = len(verified_urls)
        print(f"成功保存 {valid_count} 个有效链接到 {filepath}")
        return filepath, valid_count

    def run(self, keywords=None, pages=3):
        """运行爬虫"""
        if not keywords:
            keywords = ["CCTV1", "CCTV2", "CCTV3", "CCTV4", "CCTV5", "CCTV6", "CCTV7", "CCTV8", "CCTV9", "CCTV10"]
        
        # 清空之前的链接列表
        self.all_links = []
        self.verified_links = set()
        
        start_time = time.time()
        
        # 使用线程池并发处理多个关键词
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # 提交所有关键词搜索任务
            future_to_keyword = {
                executor.submit(self.search_keyword_pages, keyword, pages): keyword 
                for keyword in keywords
            }
            
            # 处理完成的任务
            for future in concurrent.futures.as_completed(future_to_keyword):
                keyword = future_to_keyword[future]
                try:
                    links = future.result()
                    if links:
                        print(f"为关键词 '{keyword}' 找到 {len(links)} 个链接")
                        for link in links:
                            if not any(item['url'] == link for item in self.all_links):
                                self.all_links.append({
                                    'url': link,
                                    'source': keyword
                                })
                    else:
                        print(f"关键词 '{keyword}' 未找到链接")
                except Exception as e:
                    print(f"处理关键词 '{keyword}' 时出错: {e}")
        
        if self.all_links:
            print(f"\n总共找到 {len(self.all_links)} 个唯一链接")
            
            # 保存结果为M3U格式
            output_file, valid_count = self.save_to_m3u(
                self.all_links, 
                "ysws.m3u", 
                "github"
            )
            
            end_time = time.time()
            print(f"总运行时间: {end_time - start_time:.2f} 秒")
            print(f"其中 {valid_count} 个链接验证有效")
            
            return output_file, self.all_links, valid_count
        else:
            print("未找到任何链接")
            return None, [], []

def main():
    """主函数"""
    print("Tonkiang.us IPTV爬虫启动")
    print(f"开始时间: {datetime.now().isoformat()}")
    
    crawler = TonkiangCrawler()
    
    # 配置参数 - 减少搜索范围以节省时间
    search_keywords = [
      "CCTV1"   # 综合频道
   
    ]
    pages_to_crawl = 2  # 减少爬取页数
    
    try:
        output_file, all_links, valid_links = crawler.run(
            search_keywords, 
            pages_to_crawl
        )
        
        if output_file:
            print(f"\n✅ 爬取完成！")
            print(f"📁 M3U文件: {output_file}")
            print(f"✅ 有效链接: {valid_links} 个")
            
            # 显示统计信息
            cctv_counts = {}
            for item in all_links:
                source = item['source']
                cctv_counts[source] = cctv_counts.get(source, 0) + 1
            
            print("\n各频道链接数量统计:")
            for cctv, count in sorted(cctv_counts.items()):
                print(f"{cctv}: {count} 个链接")
            
            # 在GitHub Actions环境中设置输出变量
            if os.getenv('GITHUB_ACTIONS') == 'true':
                with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
                    print(f'output_file={output_file}', file=fh)
                    print(f'total_links={len(all_links)}', file=fh)
                    print(f'valid_links={valid_links}', file=fh)
        else:
            print("\n❌ 爬取失败，未找到任何链接")
            exit(1)
            
    except Exception as e:
        print(f"\n❌ 爬虫执行出错: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
