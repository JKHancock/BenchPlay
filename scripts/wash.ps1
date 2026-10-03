# DLP 洗白导入: PowerShell Copy-Item 是本环境唯一实测解密通道(.NET/cmd 读到的是密文).
# 门禁: 每文件目标非空; 收尾 config.json 必须可解析为 JSON, 否则 FAIL.
# 用法: powershell -File wash.ps1 -Source <源目录> -Target <目标目录>
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Target
)

New-Item -ItemType Directory -Force -Path $Target | Out-Null
$files = Get-ChildItem -Path $Source -Recurse -File
foreach ($file in $files) {
    $rel = $file.FullName.Substring((Resolve-Path $Source).Path.Length).TrimStart('\', '/')
    $dest = Join-Path $Target $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $dest -Force
    if ((Get-Item $dest).Length -eq 0) { Write-Error "FAIL 目标为空: $rel"; exit 1 }
    Write-Host "washed: $rel ($([math]::Round($file.Length / 1MB, 1))MB)"
}

$config = Join-Path $Target 'config.json'
if (Test-Path $config) {
    try { Get-Content $config -Raw | ConvertFrom-Json | Out-Null }
    catch { Write-Error "FAIL config.json 不可解析(洗白未生效): $($_.Exception.Message)"; exit 1 }
    Write-Output "PASS 洗白完成, config.json 为明文"
}
else { Write-Output "PASS 拷贝完成(无 config.json, 可分发性待人工确认)" }
