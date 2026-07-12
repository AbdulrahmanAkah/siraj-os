Write-Host "================ DIRECTORY TREE ================"

tree src /F

Write-Host "`n================ PYTHON FILES ================"

Get-ChildItem src -Recurse -Filter *.py |
ForEach-Object {
    $_.FullName.Replace((Get-Location).Path + "\", "")
}

Write-Host "`n================ IMPORT GRAPH ================"

Get-ChildItem src -Recurse -Filter *.py |
ForEach-Object {

    $file = $_.FullName.Replace((Get-Location).Path + "\", "")

    Select-String -Path $_.FullName `
        -Pattern '^\s*(from|import)\s+' |
    ForEach-Object {
        "$file :: $($_.Line.Trim())"
    }

}

Write-Host "`n================ EMPTY DIRECTORIES ================"

Get-ChildItem src -Recurse -Directory |
Where-Object {
    (Get-ChildItem $_.FullName -Force | Measure-Object).Count -eq 0
}

Write-Host "`n================ LARGE FILES ================"

Get-ChildItem src -Recurse -Filter *.py |
Sort-Object Length -Descending |
Select-Object -First 40 FullName,Length

