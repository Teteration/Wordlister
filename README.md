# 🕷️ wordlister

**Wordlister** is a powerful Python tool that extracts useful keywords from web pages, HTML forms, URLs, JavaScript variables, and more.  
It can recursively crawl a target domain or subdomains, or process pre-crawled URLs (like from GoSpider), and output a clean, filtered wordlist—ideal for penetration testing, recon, and fuzzing.

---

## 📦 Installation

Install required dependencies:

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install requests beautifulsoup4 tldextract
```

---

## 🛠 Usage

```bash
python3 wordlister.py [--url URL | --input-file PATH] [OPTIONS]
```

### 🔧 Arguments

| Option                   | Description                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| `--url`                  | Target URL to extract words from                                            |
| `--input-file`           | Path to file containing list of URLs (e.g. from GoSpider)                   |
| `--mode`                 | Crawl mode: `single`, `domain`, `subdomain` (default: `single`)             |
| `--depth`                | Crawl recursion depth (used only with `--url`, default: `2`)                |
| `--threads`              | Number of concurrent threads (default: `5`)                                 |
| `--min-length`           | Minimum word length (default: `1`)                                          |
| `--max-length`           | Maximum word length (default: `100`)                                        |
| `--filter`               | Character filter: `ascii` or `unicode` (default: `unicode`)                 |
| `--drop-obfuscated`      | Drop hex-like, meaningless values (e.g. `A1B2C3D4`)                          |
| `--output-format`        | Output format: `list` (Python-style list) or `lines` (line-by-line)         |

---

## 🧚 Examples

### 1. Extract from a single page

```bash
python3 wordlister.py --url https://example.com --mode single --min-length 5 --max-length 12 --filter ascii --drop-obfuscated --output-format list```
```

### 2. Crawl only same-domain URLs (not subdomains)

```bash
python3 wordlister.py --url https://example.com --mode domain --depth 2 --threads 5
```

### 3. Crawl all subdomains

```bash
python3 wordlister.py --url https://example.com --mode subdomain --depth 2 --threads 5
```

### 4. Use GoSpider results to generate wordlist

```bash
# Run GoSpider first

gospider --site "https://example.com" --concurrent 5 --depth 5 | cut -d "-" -f 2|  grep sadadpsp | sort -u > url.txt

# Then extract wordlist from url.txt

python3 wordlister.py \
  --input-file url.txt \
  --threads 10 \
  --min-length 5 \
  --max-length 12 \
  --filter ascii \
  --drop-obfuscated \
  --output-format list
```

---

## 📂 Output Examples

### Output as Python List (`--output-format list`)

```python
['Submit', 'Payment', 'Account', 'Password', 'Reset']
```

### Output Line-by-Line (`--output-format lines`)

```
Submit
Payment
Account
Password
Reset
```

---

## 🔐 Use Cases

- Build wordlists for directory/file fuzzing (e.g. with `ffuf`, `dirsearch`)
- Discover hidden parameters, forms, JS variables
- Recon for bug bounty / red teaming
- Use external crawlers like GoSpider and process their URL results

---

## ⚠️ Legal Notice

Use this tool only on systems and domains you are authorized to test.

---

## 🧠 Credits

Developed by a security researcher focused on automation, recon, and red teaming.

---

## 📜 License

MIT License – use freely, modify, and contribute.
