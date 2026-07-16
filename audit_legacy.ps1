Write-Host "===== application.ports ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "application\.ports" |
ForEach-Object {
    "$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}

Write-Host ""

Write-Host "===== GenerationService ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "GenerationService" |
ForEach-Object {
    "$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}

Write-Host ""

Write-Host "===== MockLLMProvider ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "MockLLMProvider" |
ForEach-Object {
    "$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}
