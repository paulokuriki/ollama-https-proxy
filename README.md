# ollama-https-proxy

A simple HTTPS proxy for Ollama that provides secure access to your local Ollama instance.

## What it does

- Provides HTTPS access to Ollama (which only runs on HTTP)
- Logs all requests to `api_usage.log`
- Zero authentication - just a secure tunnel
- Self-signed SSL certificates for development

## Quick Start

1. **Clone and run:**
   ```bash
   git clone https://github.com/paulokuriki/ollama-https-proxy.git
   cd ollama-https-proxy
   chmod +x run.sh
   ./run.sh
   ```

2. **Make sure Ollama is running:**
   ```bash
   ollama serve
   ```

3. **Access Ollama securely:**
   - Instead of: `http://localhost:11434`
   - Use: `https://localhost:11443`

## Usage Examples

**Chat with a model:**
```bash
curl -k -X POST https://localhost:11443/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama2",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

**List models:**
```bash
curl -k https://localhost:11443/api/tags
```

**Pull a model:**
```bash
curl -k -X POST https://localhost:11443/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "llama2"}'
```

## What gets created

- `venv/` - Python virtual environment
- `certificates/` - Self-signed SSL certificates
- `api_usage.log` - Request logs

## Configuration

The proxy forwards requests from `https://localhost:11443` to `http://localhost:11434` (Ollama default).

To change the Ollama port, edit `proxy.py` and update the target URL.

## Requirements

- Python 3.7+
- OpenSSL (for certificate generation)
- Ollama running locally

## Notes

- Uses self-signed certificates (browser will show security warning)
- For production, replace with proper SSL certificates
- No rate limiting or authentication
- Logs include timestamps, methods, paths, and response times

## Troubleshooting

**"Connection refused":**
- Make sure Ollama is running: `ollama serve`

**"SSL certificate error":**
- Use `-k` flag with curl, or accept browser security warning

**"Module not found":**
- The script will try to load Python modules automatically
- If it fails, ensure Python 3.7+ is available
