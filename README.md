# 🕷️ wordlister

**Wordlister** is a Python tool that extracts target-specific keywords from web pages, HTML fields, URLs, and inline JavaScript.
It can process one target page or a file of pre-crawled URLs (for example, output from GoSpider) and produce a clean, filtered wordlist for authorized penetration testing, recon, and fuzzing.

---

## 🔍 Where Does the Wordlist Come From?

Wordlister does **not** use a built-in dictionary and does not download a wordlist from a third-party source. It creates a new wordlist directly from the target URLs and the HTML returned by those URLs.

For every URL it processes, Wordlister sends an HTTP request and extracts words from:

- **Visible page text** — headings, labels, buttons, messages, and other text contained in the HTML.
- **HTML field attributes** — attribute values from `meta`, `input`, `select`, and `textarea` elements. These can reveal names such as `username`, `csrf_token`, or `redirect`.
- **URL paths** — words found in paths such as `/account/reset-password`.
- **Query-string names and values** — words from a URL such as `?action=reset&user=admin`.
- **Linked resource URLs** — paths and query strings found in the `href` and `src` attributes of links, stylesheets, scripts, and images.
- **Inline JavaScript variables** — variable names and values from simple `var`, `let`, and `const` assignments inside the page.

The collected words are then:

1. Deduplicated.
2. Filtered by `--min-length` and `--max-length`.
3. Optionally limited to ASCII with `--filter ascii`.
4. Optionally stripped of hex-like values with `--drop-obfuscated`.
5. Sorted before being printed as a Python-style list or one word per line.

### URL input modes

- With `--url`, the current version downloads and analyzes that single page.
- With `--input-file`, each valid HTTP/HTTPS URL in the file is downloaded and analyzed. This is how results from GoSpider, Burp Suite, or another crawler can be converted into one target-specific wordlist.

> **Current limitation:** `--mode` and `--depth` are accepted as command-line options, but recursive crawling is not implemented yet. External JavaScript files referenced through `src` are not downloaded for JavaScript parsing; only words in their URLs and inline JavaScript are processed.

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
| `--mode`                 | Reserved crawl mode option; currently does not change behavior              |
| `--depth`                | Reserved crawl depth option; recursive crawling is not implemented yet      |
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
python3 wordlister.py --url https://example.com --mode single --min-length 5 --max-length 12 --filter ascii --drop-obfuscated --output-format list
```

### 2. Process a prepared list of URLs

```bash
python3 wordlister.py --input-file url.txt --threads 5 --output-format lines
```

### 3. Use GoSpider results to generate a wordlist

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
