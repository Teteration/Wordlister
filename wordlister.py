import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote, parse_qs
import re
import json
import threading
import queue
import tldextract

visited_urls = set()
lock = threading.Lock()

def is_ascii_word(word):
    try:
        word.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False

def is_obfuscated_hex(word):
    if len(word) < 6:
        return False
    hex_chars = set('0123456789ABCDEF')
    word_upper = word.upper()
    non_hex_count = sum(1 for c in word_upper if c not in hex_chars)
    return (len(word) - non_hex_count) / len(word) > 0.8

def word_filter(words, min_len, max_len, filter_type, drop_obfuscated):
    filtered = set()
    for w in words:
        if w.isdigit():
            continue
        if drop_obfuscated and is_obfuscated_hex(w):
            continue
        if min_len <= len(w) <= max_len:
            if filter_type == 'ascii' and not is_ascii_word(w):
                continue
            filtered.add(w)
    return filtered

def extract_words_from_url(url):
    words = set()
    parsed = urlparse(url)
    for seg in parsed.path.split('/'):
        if seg:
            decoded = unquote(seg)
            words.update(re.findall(r'\b\w+\b', decoded))
    query_params = parse_qs(parsed.query)
    for k, vals in query_params.items():
        words.update(re.findall(r'\b\w+\b', k))
        for v in vals:
            words.update(re.findall(r'\b\w+\b', v))
    return words

def extract_words_from_js(js):
    words = set()
    pattern_var = re.compile(r'(?:var|let|const)\s+(\w+)\s*=\s*([^;]+);')
    for match in pattern_var.finditer(js):
        words.add(match.group(1))
        val = match.group(2).strip(' "\'')
        words.update(re.findall(r'\b\w+\b', val))
    return words

def extract_words_from_html(html, base_url):
    words = set()
    soup = BeautifulSoup(html, 'html.parser')
    words.update(re.findall(r'\b\w+\b', soup.get_text()))
    for tag in soup.find_all(['meta', 'input', 'select', 'textarea']):
        for attr in tag.attrs.values():
            words.update(re.findall(r'\b\w+\b', str(attr)))
    for tag in soup.find_all(['a', 'link', 'script', 'img']):
        for attr in ['href', 'src']:
            if tag.has_attr(attr):
                full_url = urljoin(base_url, tag[attr])
                words.update(extract_words_from_url(full_url))
    for script in soup.find_all('script'):
        if script.string:
            words.update(extract_words_from_js(script.string))
    return words, get_links(soup, base_url)

def get_links(soup, base_url):
    links = set()
    for tag in soup.find_all('a', href=True):
        full_url = urljoin(base_url, tag['href'])
        parsed = urlparse(full_url)
        if parsed.scheme.startswith("http"):
            links.add(full_url.split('#')[0])
    return links

def should_visit(url, mode, base_domain, include_subdomains):
    parsed = tldextract.extract(url)
    domain = f"{parsed.domain}.{parsed.suffix}"
    if mode == 'domain':
        return domain == base_domain and parsed.subdomain == ''
    elif mode == 'subdomain':
        return domain == base_domain
    return False

def worker(q, words_set, args, base_domain):
    while True:
        try:
            url, depth = q.get(timeout=3)
        except queue.Empty:
            return
        with lock:
            if (url in visited_urls) or (depth > args.depth):
                q.task_done()
                continue
            visited_urls.add(url)
        try:
            resp = requests.get(url, timeout=10)
            html = resp.text
            words, links = extract_words_from_html(html, url)
            filtered = word_filter(words, args.min_length, args.max_length, args.filter, args.drop_obfuscated)
            with lock:
                words_set.update(filtered)
            for link in links:
                if should_visit(link, args.mode, base_domain, args.mode == 'subdomain'):
                    q.put((link, depth + 1))
        except Exception:
            pass
        q.task_done()

def start_crawling(start_url, args):
    parsed = tldextract.extract(start_url)
    base_domain = f"{parsed.domain}.{parsed.suffix}"
    q_urls = queue.Queue()
    q_urls.put((start_url, 0))
    words_set = set()
    threads = []

    for _ in range(args.threads):
        t = threading.Thread(target=worker, args=(q_urls, words_set, args, base_domain))
        t.daemon = True
        t.start()
        threads.append(t)

    q_urls.join()

    return sorted(words_set)

def single_page_mode(url, args):
    try:
        resp = requests.get(url, timeout=10)
        html = resp.text
        words, _ = extract_words_from_html(html, url)
        return sorted(word_filter(words, args.min_length, args.max_length, args.filter, args.drop_obfuscated))
    except Exception as e:
        print(f"Error: {e}")
        return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract wordlist from a webpage or recursively crawl a domain.")
    parser.add_argument("url", help="Target URL")
    parser.add_argument("--mode", choices=["single", "domain", "subdomain"], default="single", help="Crawl mode")
    parser.add_argument("--depth", type=int, default=2, help="Recursion depth for crawling")
    parser.add_argument("--threads", type=int, default=5, help="Number of concurrent threads")
    parser.add_argument("--min-length", type=int, default=1, help="Minimum word length")
    parser.add_argument("--max-length", type=int, default=100, help="Maximum word length")
    parser.add_argument("--filter", choices=["ascii", "unicode"], default="unicode", help="Character filter")
    parser.add_argument("--drop-obfuscated", action="store_true", help="Drop hex-like words")
    parser.add_argument("--output-format", choices=["list", "lines"], default="list", help="Output format")

    args = parser.parse_args()

    if args.mode == "single":
        result = single_page_mode(args.url, args)
    else:
        result = start_crawling(args.url, args)

    print(f"\n[+] Extracted {len(result)} words:\n")
    if args.output_format == "list":
        print(result)
    else:
        for word in result:
            print(word)

