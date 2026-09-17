# Принудительно включаем UTF-8 и TLS 1.2 для работы с Vercel
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ============================================================
# CONFIG
# ============================================================

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = Get-Location }
$ApiUrl = "https://dance-content-engine-v1.vercel.app/api/ai"
$ContentDir = Join-Path $ProjectRoot "04_CONTENT\content"

New-Item -ItemType Directory -Force -Path $ContentDir | Out-Null

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " DANCE CONTENT ENGINE — СИТУАТИВНЫЙ / AD-HOC ПОСТ" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# INTERACTIVE INPUT
# ============================================================

$Topic = Read-Host "1. Тема поста/события (напр., 'Итоги соревнований')"
if ([string]::IsNullOrWhiteSpace($Topic)) { 
    Write-Host "Ошибка: тема не может быть пустой" -ForegroundColor Red
    exit 1 
}

$Channel = Read-Host "2. Канал (по умолчанию VK)"
if ([string]::IsNullOrWhiteSpace($Channel)) { $Channel = "VK" }

$Audience = Read-Host "3. Целевая аудитория (по умолчанию Родители DanceKids)"
if ([string]::IsNullOrWhiteSpace($Audience)) { $Audience = "Родители детей DanceKids" }

Write-Host ""
Write-Host "4. Введите ключевые факты события (жмите Enter после каждой строки, для завершения — нажмите Enter на пустой строке):" -ForegroundColor Yellow
$RawFacts = @()
while ($true) {
    $line = Read-Host "  >"
    if ([string]::IsNullOrWhiteSpace($line)) { break }
    $RawFacts += $line
}
$EventFacts = $RawFacts -join "`n"

# ============================================================
# TASK BUILDER
# ============================================================

$task = @"
ВЫПОЛНИ СОЗДАНИЕ СИТУАТИВНОГО КОНТЕНТА ПО ФАКТАМ СОБЫТИЯ.

Канал: $Channel
Тема: $Topic
Аудитория: $Audience

ФАКТИЧЕСКИЕ ВВОДНЫЕ СОБЫТИЯ:
$EventFacts

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА:
1. Опирайся строго на предоставленные факты события и проектный контекст (01_KNOWLEDGE, 03_AUDIENCE).
2. Не выдумывай факты, цены или расписание, если их нет в вводных.
3. Подготовь готовый пост для канала $Channel.
4. Язык — русский.
"@

# ============================================================
# API REQUEST
# ============================================================

$bodyObject = @{
    mode         = "CONTENT"
    task         = $task
    profile      = "CONTENT"
    channel      = $Channel
    channels     = @($Channel)
    includeRadar = $true
}

$bodyJson = $bodyObject | ConvertTo-Json -Depth 30
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($bodyJson)

Write-Host ""
Write-Host "Отправка запроса на Vercel..." -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest `
        -Uri $ApiUrl `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body $bodyBytes `
        -UseBasicParsing `
        -TimeoutSec 120

    $jsonText = [System.Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray())
    $data = $jsonText | ConvertFrom-Json
}
catch {
    Write-Host ""
    Write-Host "ОШИБКА API: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

if ($data.ok -ne $true -or -not $data.result) {
    Write-Host "Ошибка генерации:" -ForegroundColor Red
    $data | ConvertTo-Json -Depth 10
    exit 1
}

# ============================================================
# SAVE CONTENT
# ============================================================

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$safeChannel = $Channel -replace '[\/:*?"<>|]', '-'
$contentFilePath = Join-Path $ContentDir "adhoc-$safeChannel-$timestamp.md"

[System.IO.File]::WriteAllText(
    $contentFilePath,
    [string]$data.result,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " ГОТОВО! Файл сохранен:" -ForegroundColor Green
Write-Host " $contentFilePath"
Write-Host "============================================================" -ForegroundColor Green

Start-Process explorer.exe $ContentDir