<#
.SYNOPSIS
    Open a capture of WiFi App Helper in Wireshark on Windows, live or as a download.

.EXAMPLE
    .\live-capture.ps1 -Server homeassistant.local -Token $env:HELPER_TOKEN                 # list captures
    .\live-capture.ps1 -Server homeassistant.local -Token $env:HELPER_TOKEN -Name x.pcap -Follow
#>
param(
    [Parameter(Mandatory)][string]$Server,
    [Parameter(Mandatory)][string]$Token,
    [string]$Name,
    [int]$Port = 4817,
    [string]$Filter,
    [switch]$Follow,
    [string]$Wireshark = "$env:ProgramFiles\Wireshark\Wireshark.exe"
)

$ErrorActionPreference = 'Stop'
$base = "http://${Server}:$Port/v1/captures"
$headers = @{ Authorization = "Bearer $Token" }

if (-not $Name) {
    (Invoke-RestMethod -Uri $base -Headers $headers).captures | Format-Table name, bytes, modified
    return
}
if ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.pcap(ng)?$') { throw "Invalid capture name: $Name" }
if (-not (Test-Path $Wireshark)) { throw "Wireshark not found at $Wireshark; pass -Wireshark with its path." }

if ($Follow) {
    # Windows PowerShell 5 corrupts binary data in pipelines, so let cmd.exe connect curl to Wireshark.
    $url = "$base/${Name}?follow=1"
    cmd.exe /c "curl.exe -sN -H `"Authorization: Bearer $Token`" `"$url`" | `"$Wireshark`" -k -i -"
    return
}

$query = if ($Filter) { '?filter=' + [uri]::EscapeDataString($Filter) } else { '' }
$target = Join-Path $env:TEMP $Name
Invoke-WebRequest -Uri "$base/$Name$query" -Headers $headers -OutFile $target
& $Wireshark $target
