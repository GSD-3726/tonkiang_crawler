#!/usr/bin/env python3
"""
Tonkiang.us IPTV爬虫 - 按卫视频道号搜索并输出对应链接
"""

import requests
import re
import os
import time
import random
import hashlib
from datetime import datetime
from urllib.parse import urlencode
import concurrent.futures

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
        self.verified_links = []  # 存储已验证的链接

    def generate_random_hash(self):
        """生成随机哈希值"""
        random_str = str(random.random())
        return hashlib.md5(random_str.encode()).hexdigest()[:8]

    def search_iptv_page(self, keyword="湖南卫视", page=1):
        """搜索指定页面的IPTV频道"""
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
        try:
            response = self.session.get(m3u8_url, timeout=(2, 3), stream=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                content = response.text[:500]  # 只检查前500个字符
                
                # 检查M3U8特征
                if ('mpegurl' in content_type or 
                    content.startswith('#EXTM3U') or 
                    '#EXTINF' in content):
                    return True
                    
            return False
        except Exception as e:
            print(f"验证链接失败: {e}")
            return False

    def verify_links_parallel(self, links):
        """并行验证链接有效性"""
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # 提交所有验证任务
            future_to_link = {executor.submit(self.verify_m3u8, link): link for link in links}
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_link):
                link = future_to_link[future]
                try:
                    is_valid = future.result()
                    if is_valid:
                        self.verified_links.append(link)
                        print(f"✓ 验证通过: {link}")
                    else:
                        print(f"✗ 验证失败: {link}")
                except Exception as e:
                    print(f"验证链接时出错 {link}: {e}")

    def search_multiple_pages(self, keyword="湖南卫视", pages=2, interval=8):
        """搜索多页内容"""
        all_links = []
        
        for page in range(1, pages + 1):
            print(f"\n{'='*50}")
            print(f"开始处理第 {page} 页")
            print(f"{'='*50}")
            
            links = self.search_iptv_page(keyword, page)
            
            if links:
                print(f"第 {page} 页找到 {len(links)} 个链接")
                all_links.extend(links)
                
                # 添加链接到总列表
                for link in links:
                    if link not in self.all_links:
                        self.all_links.append({
                            'url': link,
                            'source': keyword
                        })
                
                # 如果不是最后一页，等待指定的间隔时间
                if page < pages:
                    print(f"等待 {interval} 秒后继续下一页...")
                    time.sleep(interval)
            else:
                print(f"第 {page} 页未找到链接")
                break  # 如果某一页没找到内容，停止爬取
        
        return all_links

    def save_to_m3u(self, links_data, filename="wstv.m3u", output_dir="output"):
        """保存结果为M3U格式文件"""
        # 创建输出目录
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"创建目录: {output_dir}")
        
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            # 写入M3U文件头
            f.write('#EXTM3U\n')
            
            # 写入每个链接
            valid_count = 0
            for item in links_data:
                link = item['url']
                source = item['source']
                
                # 只保存已验证的链接
                if link in self.verified_links:
                    # 使用搜索关键词作为频道名称
                    f.write(f'#EXTINF:-1 tvg-id="" tvg-name="{source}" tvg-logo="" group-title="卫视",{source}\n')
                    f.write(f'{link}\n')
                    print(f"✓ 已添加有效链接: {source} -> {link}")
                    valid_count += 1
                else:
                    print(f"✗ 跳过无效链接: {link}")
        
        print(f"成功保存 {valid_count} 个有效链接到 {filepath}")
        return filepath, valid_count

    def run(self, keywords=None, pages=2, interval=8):
        """运行爬虫"""
        if not keywords:
            keywords = ["湖南卫视", "浙江卫视", "江苏卫视", "东方卫视", "北京卫视"]
        
        # 清空之前的链接列表
        self.all_links = []
        self.verified_links = []
        
        # 第一步：收集所有链接
        for keyword in keywords:
            print(f"\n{'='*50}")
            print(f"开始处理关键词: {keyword}")
            print(f"{'='*50}")
            
            links = self.search_multiple_pages(keyword, pages, interval)
            
            if links:
                print(f"为关键词 '{keyword}' 找到 {len(links)} 个链接")
            else:
                print(f"关键词 '{keyword}' 未找到链接")
        
        if not self.all_links:
            print("未找到任何链接")
            return None, [], 0
            
        print(f"\n总共找到 {len(self.all_links)} 个唯一链接")
        
        # 第二步：并行验证所有链接
        print(f"\n开始并行验证 {len(self.all_links)} 个链接...")
        all_urls = [item['url'] for item in self.all_links]
        self.verify_links_parallel(all_urls)
        
        print(f"\n验证完成，有效链接: {len(self.verified_links)} 个")
        
        # 第三步：保存结果为M3U格式
        output_file, valid_count = self.save_to_m3u(
            self.all_links, 
            "wstv.m3u", 
            "output"
        )
        
        return output_file, self.all_links, valid_count

def main():
    """主函数"""
    print("Tonkiang.us IPTV爬虫启动 - 卫视频道")
    print(f"开始时间: {datetime.now().isoformat()}")
    
    crawler = TonkiangCrawler()
    
    # 配置参数 - 卫视频道
    search_keywords = [
        "湖南卫视", "浙江卫视", "江苏卫视", "东方卫视", "北京卫视",
        "广东卫视", "深圳卫视", "天津卫视", "山东卫视", "安徽卫视"
    ]
    pages_to_crawl = 2  # 爬取2页
    request_interval = 8  # 8秒间隔
    
    try:
        output_file, all_links, valid_count = crawler.run(
            search_keywords, 
            pages_to_crawl, 
            request_interval
        )
        
        if output_file:
            print(f"\n✅ 爬取完成！")
            print(f"📁 M3U文件: {output_file}")
            print(f"✅ 有效链接: {valid_count} 个")
            
            # 显示统计信息
            tv_counts = {}
            for item in all_links:
                source = item['source']
                tv_counts[source] = tv_counts.get(source, 0) + 1
            
            print("\n各频道链接数量统计:")
            for tv, count in sorted(tv_counts.items()):
                print(f"{tv}: {count} 个链接")
            
            # 在GitHub Actions环境中设置输出变量
            if os.getenv('GITHUB_ACTIONS') == 'true':
                with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
                    print(f'output_file={output_file}', file=fh)
                    print(f'total_links={len(all_links)}', file=fh)
                    print(f'valid_links={valid_count}', file=fh)
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
