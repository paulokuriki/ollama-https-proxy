# ollama-https-proxy

A simple HTTPS proxy for Ollama that provides secure access to your local Ollama instance.

## What it does

* Provides HTTPS access to Ollama (which only runs on HTTP by default)
* Logs all requests to `api_usage.log`
* No authentication — just a secure tunnel for development
* Uses self-signed SSL certificates for testing

⚠️ **Warning**: This proxy is for **local testing and development only**.
For production, you must add authentication and replace the self-signed certs with real ones (e.g. Let’s Encrypt).

---

## Quick Start

1. **Clone:**

   ```bash
   git clone https://github.com/paulokuriki/ollama-https-proxy.git
   cd ollama-https-proxy
   chmod +x start_proxy.sh run_ollama.sh
   ```

2. **Start Ollama (if not already running):**

   ```bash
   ./run_ollama.sh
   ```

3. **Start Proxy:**

   ```bash
   ./start_proxy.sh
   ```


5. **Access Ollama securely:**

   * Instead of: `http://localhost:11434`
   * Use: `https://localhost:11434`

---

## Usage Examples

**Chat with a model:**

```bash
curl -k -X POST https://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama2",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

**List models:**

```bash
curl -k https://localhost:11434/api/tags
```

**Pull a model:**

```bash
curl -k -X POST https://localhost:11434/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "llama2"}'
```

---

## What gets created

* `venv/` — Python virtual environment
* `certificates/` — Self-signed SSL certificates (auto-generated)
* `api_usage.log` — Request logs

---

## Configuration

The proxy forwards requests from `https://localhost:11434` → `http://localhost:11434` (Ollama default).
To change ports or host, edit **`proxy.py`**.

---

## Requirements

* Python 3.7+
* OpenSSL (for certificate generation)
* Ollama running locally

---

## Notes

* Self-signed certs will trigger browser warnings (`-k` needed for curl).
* No authentication, rate limiting, or access controls included.
* Logs include timestamps, methods, paths, status codes, and response times.

---

## Troubleshooting

**"Connection refused"**

* Make sure Ollama is running: `./run_ollama.sh`

**"SSL certificate error"**

* Use `-k` flag with curl, or accept browser warning.

**"Module not found"**

* The script tries to load Python automatically. Ensure Python 3.7+ is available.
