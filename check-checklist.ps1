$content = Get-Content 'C:\git\observer-microservices\specs\001-obsrv-api-mvp\checklists\requirements.md' -Raw
$total = ([regex]::Matches($content, '- \[(x|X| )\]')).Count
$completed = ([regex]::Matches($content, '- \[(x|X)\]')).Count
$incomplete = ([regex]::Matches($content, '- \[ \]')).Count
Write-Output "Total: $total, Completed: $completed, Incomplete: $incomplete"
