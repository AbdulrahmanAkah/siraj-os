Write-Host "===== LLMGateway ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "LLMGateway" |
ForEach-Object {
"$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}

Write-Host ""

Write-Host "===== ProviderFactory ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "ProviderFactory" |
ForEach-Object {
"$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}

Write-Host ""

Write-Host "===== FakeGateway ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "FakeGateway" |
ForEach-Object {
"$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}

Write-Host ""

Write-Host "===== FakeLLMClient ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "FakeLLMClient" |
ForEach-Object {
"$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}

Write-Host ""

Write-Host "===== OpenAIGateway ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "OpenAIGateway" |
ForEach-Object {
"$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}

Write-Host ""

Write-Host "===== GeminiGateway ====="

Get-ChildItem src -Recurse -Filter *.py |
Select-String "GeminiGateway" |
ForEach-Object {
"$($_.Path):$($_.LineNumber) -> $($_.Line.Trim())"
}
