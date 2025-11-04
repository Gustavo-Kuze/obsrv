$dirs = @(
    'backend\src\models',
    'backend\src\services',
    'backend\src\api',
    'backend\src\core',
    'backend\tests\unit',
    'backend\tests\integration',
    'backend\tests\contract',
    'tests\fixtures',
    'tests\utils'
)

foreach ($dir in $dirs) {
    $path = 'C:\git\observer-microservices\' + $dir
    New-Item -Path $path -ItemType Directory -Force | Out-Null
}

Write-Output "Directory structure created successfully"
