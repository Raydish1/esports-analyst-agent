# The public demo: the app in live mode, open to anyone through a Cloudflare quick tunnel, with the MCP server at /mcp.
# Run from the repository's folder (or this worktree's):  powershell -ExecutionPolicy Bypass -File app/dev/public.ps1
# Needs: cloudflared (winget install --id Cloudflare.cloudflared), the Ollama server (OLLAMA_BASE_URL in .env), and the
# live build in data/db (data/db/current.json). Stop with Ctrl+C: it stops the tunnel and the app together.
param([int]$Port = 8001)
$env:PYTHONIOENCODING = "utf-8"
$app = Start-Process -FilePath "py" -ArgumentList "-3.14", "app/server/main.py", "--mode", "live", "--public", "--mcp",
    "--port", "$Port" -NoNewWindow -PassThru
try {
    Write-Host "Starting the app on port $Port; the tunnel's address appears below (https://...trycloudflare.com)."
    Write-Host "The page is that address; the MCP server is that address followed by /mcp/."
    cloudflared tunnel --url "http://localhost:$Port"
} finally {
    Stop-Process -Id $app.Id -ErrorAction SilentlyContinue
}
