<#
.SYNOPSIS
    Switches the local git author identity for this repository.

.DESCRIPTION
    Pawprint-Local is developed on a single Windows machine, but by two people.
    Whoever is actually writing the code should be the author of the commit,
    so run this before you start a working session.

.EXAMPLE
    .\scripts\git-as.ps1 elif       # Elif is at the keyboard
    .\scripts\git-as.ps1 burak      # Burak is at the keyboard
    .\scripts\git-as.ps1            # show who is currently configured
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet('elif', 'burak', '')]
    [string]$Who = ''
)

$ErrorActionPreference = 'Stop'

$people = @{
    elif  = @{ Name = 'Elif Berra'; Email = 'elifberraclk@gmail.com' }
    burak = @{ Name = 'burakaymak'; Email = 'burakdenizkaymak@gmail.com' }
}

function Show-Current {
    $name = git config --local user.name
    $mail = git config --local user.email
    if (-not $name) {
        Write-Host "No local identity set for this repo (falling back to global)." -ForegroundColor Yellow
        $name = git config --global user.name
        $mail = git config --global user.email
    }
    Write-Host "Current author: $name <$mail>" -ForegroundColor Cyan
}

if ($Who -eq '') {
    Show-Current
    Write-Host ""
    Write-Host "Usage: .\scripts\git-as.ps1 [elif|burak]"
    exit 0
}

$p = $people[$Who]
git config --local user.name  $p.Name
git config --local user.email $p.Email

Write-Host "Author set to: $($p.Name) <$($p.Email)>" -ForegroundColor Green
Write-Host "This applies to THIS repository only." -ForegroundColor DarkGray
